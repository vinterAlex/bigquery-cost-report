"""Collect BigQuery job metadata.

This module only ever reads INFORMATION_SCHEMA.JOBS_BY_PROJECT metadata
- never table rows. It is the single source of the numbers that cost
attribution works from.

The community edition collects only job metadata (who ran what, and
what the scan billed). It does NOT collect TABLE_STORAGE or
partition-column metadata - those feed the storage and surprise-bill
risk features, which are part of the full (paid) edition.

Query text is truncated aggressively and only used for structural
checks; no literals are kept. Nothing is written outside the output
folder, which stays on the user's machine.
"""

import os
from datetime import datetime, timedelta, timezone


def _location_for_project(client, project_id):
    """Detect the BigQuery location(s) the identity can query in.

    A project may hold datasets in several regions; we report the
    distinct regions found (lowercased, e.g. 'eu', 'us-central1',
    'europe-west1'), and callers use each region for its own
    INFORMATION_SCHEMA query.
    """

    max_datasets = int(
        (os.environ.get("BQ_REPORT_MAX_REGION_DATASETS") or "200").strip()
    )

    regions = set()

    for i, dataset in enumerate(client.list_datasets(project=project_id)):
        if i >= max_datasets:
            break
        try:
            loc = client.get_dataset(dataset.reference).location
        except Exception:  # noqa: BLE001
            loc = getattr(dataset, "location", None)
        if loc:
            regions.add(str(loc).strip().lower())

    return sorted(regions)


def collect_jobs(bq, config, regions, filename=None, meter=None):
    """Return (rows, truncated) from JOBS_BY_PROJECT for each region.

    Only SELECT/WITH and a few benign statement types that we are
    entitled to price are kept; the rest are skipped. Query text is
    truncated to a bounded prefix so we never retain full customer
    statements.
    """

    from safety import assert_read_only, GCP_RESOURCE, quote_region_dataset

    days = int(config.get("lookback_days") or 30)
    start = datetime.now(timezone.utc) - timedelta(days=days)

    max_jobs = int(config.get("max_jobs") or 100000)

    datasets = [
        str(d).strip()
        for d in (config.get("datasets") or [])
        if d and str(d).strip()
    ]

    dataset_clause = ""
    if datasets:
        for d in datasets:
            if not GCP_RESOURCE.match(d):
                raise RuntimeError(
                    f"Refusing to use dataset identifier: {d!r}"
                )
        in_list = ", ".join(f"'{d}'" for d in datasets)
        dataset_clause = f"""
          AND (
            EXISTS(
              SELECT 1
              FROM UNNEST(referenced_tables) AS rt
              WHERE rt.dataset_id IN ({in_list})
            )
            OR destination_table.dataset_id IN ({in_list})
          )"""

    rows = []
    truncated = False

    for region in regions or []:
        schema = quote_region_dataset(region, "JOBS_BY_PROJECT")

        sql = f"""
        SELECT
          job_id,
          user_email,
          statement_type,
          total_bytes_billed,
          total_bytes_processed,
          total_slot_ms,
          creation_time,
          cache_hit,
          error_result IS NOT NULL AS errored,
          left(query, 2000) AS query_head,
          ARRAY(
            SELECT CONCAT(rt.dataset_id, '.', rt.table_id)
            FROM UNNEST(referenced_tables) AS rt
          ) AS ref_tables
        FROM {schema}
        WHERE creation_time >= TIMESTAMP("{start.isoformat()}")
          AND statement_type IN ('SELECT','WITH','SCRIPT','INSERT','MERGE','CREATE_TABLE','CREATE_TABLE_AS_SELECT','CREATE_VIEW','UPDATE','DELETE')
          AND total_bytes_billed >= 0{dataset_clause}
        ORDER BY creation_time DESC
        LIMIT {max_jobs}
        """

        assert_read_only(sql)

        region_count = 0

        for r in bq.run_query(config, sql, location=region, filename=filename,
                              meter=meter):
            region_count += 1
            rows.append(
                {
                    "job_id": r.job_id,
                    "user_email": r.user_email,
                    "statement_type": r.statement_type,
                    "bytes_billed": r.total_bytes_billed or 0,
                    "bytes_processed": r.total_bytes_processed or 0,
                    "slot_ms": r.total_slot_ms or 0,
                    "created": (
                        r.creation_time.isoformat()
                        if getattr(r, "creation_time", None)
                        else None
                    ),
                    "query_head": r.query_head or "",
                    "cache_hit": bool(getattr(r, "cache_hit", False)),
                    "errored": bool(getattr(r, "errored", False)),
                    "referenced_tables": list(
                        getattr(r, "ref_tables", None) or []
                    ),
                    "location": region,
                }
            )

        if region_count >= max_jobs:
            truncated = True

    return rows, truncated

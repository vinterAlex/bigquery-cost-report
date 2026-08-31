"""Cost attribution: who and what is driving the bill.

Turns raw job rows into spend buckets:

  * by human user (excludes service accounts unless asked),
  * by service account,
  * by dataset/table, from the referenced-table column of
    INFORMATION_SCHEMA.JOBS (parsed out of the query head).

No cost figure is invented here - everything is arithmetic on
total_bytes_billed times the resolved price per TiB.

The community edition reports these core buckets. dbt model
attribution, storage cost, daily trends and an Editions (capacity)
comparison are part of the full edition and deliberately not included
here.
"""

import re

from pricing import query_cost_usd
from safety import strip_noise


def _is_service_account(email):
    return bool(email and email.endswith(".gserviceaccount.com") or (
        email and "iam.gserviceaccount.com" in email
    ))


def _tables_referenced(query_head):
    """Best-effort list of table references in a query head.

    Handles backticked (`proj.dataset.table`) and bare (proj.dataset.
    table) table names after FROM/JOIN. Used only for attribution of
    the most-referenced tables; not used for decisions with money.
    """

    if not query_head:
        return []

    found = []

    # Backticked full path
    for m in re.finditer(
        r"\b(?:FROM|JOIN)\s+`([^`]+)`", query_head, re.IGNORECASE
    ):
        found.append(m.group(1))

    # Bare dotted name (may be preceded by a comma for multi-table FROM)
    for m in re.finditer(
        r"\b(?:FROM|JOIN|,)\s+([A-Za-z_][\w\-]*(?:\.[A-Za-z_][\w\-]*){1,3})",
        query_head,
        re.IGNORECASE,
    ):
        name = m.group(1)
        if not name.lower().startswith(("unnest", "(")):
            found.append(name)

    return found


def attribute(config, jobs, human_only=False):
    """Return a dict of cost attribution buckets + the pricing note."""

    per_tib, origin = None, None

    from pricing import resolve_per_tib
    per_tib, origin = resolve_per_tib(config)

    buckets = {
        "humans": {},
        "service_accounts": {},
        "datasets": {},
        "top_queries": [],
    }

    totals = {
        "bytes_billed": 0,
        "cost_usd": 0.0,
        "jobs": len(jobs),
        "cache_hit_jobs": 0,
        "errored_jobs": 0,
        "errored_bytes": 0,
        "errored_cost_usd": 0.0,
    }

    query_totals = {}

    for job in jobs:
        email = job.get("user_email") or "unknown"
        bytes_billed = job.get("bytes_billed") or 0
        cost = query_cost_usd(config, bytes_billed, job.get("location"))

        is_sa = _is_service_account(email)
        human_only_excluded = bool(human_only and is_sa)

        if not human_only_excluded:
            totals["bytes_billed"] += bytes_billed
            if cost is not None:
                totals["cost_usd"] += cost
            if job.get("cache_hit"):
                totals["cache_hit_jobs"] += 1
            if job.get("errored"):
                totals["errored_jobs"] += 1
                totals["errored_bytes"] += bytes_billed
                if cost is not None:
                    totals["errored_cost_usd"] += cost

        bucket = "service_accounts" if is_sa else "humans"

        if human_only and is_sa:
            bucket = None

        if bucket:
            entry = buckets[bucket].setdefault(
                email, {"jobs": 0, "bytes_billed": 0, "cost_usd": 0.0}
            )
            entry["jobs"] += 1
            entry["bytes_billed"] += bytes_billed
            if cost is not None:
                entry["cost_usd"] += cost

        # Dataset / table attribution. Prefer the exact list BigQuery
        # recorded for the job (referenced_tables from the JOBS view);
        # fall back to best-effort parsing of the query head only for
        # jobs collected before that column existed.
        refs = job.get("referenced_tables") or _tables_referenced(
            job.get("query_head") or ""
        )
        for ref in refs:
            parts = ref.split(".")
            last = parts[-1].lower()
            lowered = ref.lower()
            if (
                "information_schema" in lowered
                or lowered.startswith("__")
                or lowered.startswith("unescape")
                or lowered.startswith("region-")
                or last in (
                    "table_id", "dataset_id", "project_id",
                    "schema_name", "column_id",
                )
            ):
                continue
            key = ".".join(parts[-2:]) if len(parts) >= 2 else ref
            entry = buckets["datasets"].setdefault(
                key,
                {"jobs": 0, "bytes_billed": 0, "cost_usd": 0.0, "_users": {}},
            )
            entry["jobs"] += 1
            entry["bytes_billed"] += bytes_billed
            if cost is not None:
                entry["cost_usd"] += cost
            entry["_users"][email] = entry["_users"].get(email, 0) + bytes_billed

        # Query totals, keyed on a readable, structural form so re-runs
        # group together (comments and literals removed).
        qkey = " ".join(
            strip_noise(job.get("query_head") or "").split()
        )[:100]
        if qkey:
            q = query_totals.setdefault(
                qkey,
                {"jobs": 0, "bytes_billed": 0, "cost_usd": 0.0, "query": qkey},
            )
            q["jobs"] += 1
            q["bytes_billed"] += bytes_billed
            if cost is not None:
                q["cost_usd"] += cost

    def _rank(bucket, limit):
        items = []
        for k, v in buckets[bucket].items():
            item = {"name": k, **v}
            users = item.pop("_users", None)
            if users:
                top_email, top_bytes = max(users.items(), key=lambda u: u[1])
                total = sum(users.values()) or 1
                item["top_consumer"] = top_email
                item["top_consumer_bytes"] = top_bytes
                item["top_consumer_share"] = round(top_bytes / total, 4)
            items.append(item)
        items.sort(key=lambda x: x["cost_usd"], reverse=True)
        return items[:limit]

    limits = (config.get("report") or {}).get("limits") or {}

    return {
        "per_tib": per_tib,
        "pricing_origin": origin,
        "pricing_note": (
            "Estimated query cost is before the 1 TiB/month free tier "
            "and excludes storage."
            if per_tib is not None
            else "Capacity/Editions pricing is by slot-hours, not per TiB; "
                 "no query $/TiB figure is reported."
        ),
        "totals": totals,
        "humans": _rank("humans", limits.get("top_users", 10)),
        "service_accounts": _rank(
            "service_accounts", limits.get("top_users", 10)
        ),
        "datasets": _rank("datasets", limits.get("top_datasets", 10)),
        "top_queries": _rank_top_queries(query_totals, limits),
    }


def _rank_top_queries(query_totals, limits):
    items = sorted(
        query_totals.values(),
        key=lambda x: x["cost_usd"],
        reverse=True,
    )
    return items[: limits.get("top_queries", 10)]

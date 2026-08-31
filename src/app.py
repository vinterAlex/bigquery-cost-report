"""BigQuery Cost Report - community edition entry point and orchestrator.

Command-line interface:

    python app.py --project PROJECT [--key FILE] [--days N] [--dry-run]

This community edition is CLI-only and writes a PDF report plus a JSON
summary to the output folder. No web app, no risk analysis, no storage
analysis - those are part of the full edition.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def _config_dir():
    parent = os.path.dirname(PROJECT_DIR)
    candidate = os.path.join(parent, "config.yaml")
    if os.path.exists(candidate):
        return parent
    return PROJECT_DIR


def load_runtime_config(overrides=None):
    import config
    config_file = os.path.join(_config_dir(), "config.yaml")
    return config.load_config(
        config_file if os.path.exists(config_file) else None,
        overrides=overrides,
        require_project=False,
    )


def run_scan(config, filename=None, dry_run=False):
    """Execute one full scan and return a result dict.

    In dry_run mode nothing is queried beyond the plan; the result is
    a plan listing what the scan WOULD do.
    """

    import bq
    import collector
    import attribution
    from pricing import query_cost_usd

    project_id = config.get("project_id")

    if dry_run:
        projects = bq.list_projects(config, filename)
        return {
            "dry_run": True,
            "project_id": project_id,
            "projects_found": projects,
            "message": (
                "Dry run: would analyse the selected project. "
                "Nothing was billed and no data was read."
            ),
        }

    client = bq.get_client(config, filename)

    wanted = [
        str(d).strip()
        for d in (config.get("datasets") or [])
        if d and str(d).strip()
    ]
    if wanted:
        visible = {
            str(d.get("dataset_id"))
            for d in bq.list_datasets(config, project_id, filename=filename)
        }
        missing = [d for d in wanted if d not in visible]
        if missing:
            raise RuntimeError(
                "Dataset(s) not found or not visible to this service "
                f"account: {', '.join(missing)}.\n"
                "Wrong dataset or project? Check the name and that the "
                "account can read the project as a metadataViewer, then "
                "re-run the script with the correct values."
            )

    meter = {"bytes_billed": 0, "queries": 0}

    configured = (config.get("region") or "").strip().lower()
    if configured:
        regions = [configured]
    else:
        regions = collector._location_for_project(client, project_id)

    if not regions:
        raise RuntimeError(
            "Could not detect a BigQuery region for this project. "
            "Set the region in config.yaml (e.g. eu, us, us-central1) "
            "and run again."
        )

    warnings = []

    jobs, jobs_truncated = collector.collect_jobs(
        bq, config, regions, filename, meter=meter
    )

    max_jobs = int(config.get("max_jobs") or 100000)
    if jobs_truncated:
        warnings.append(
            f"The lookback window contains more than {max_jobs:,} jobs; "
            f"only the {max_jobs:,} most recent per region were analysed, "
            "so totals UNDERCOUNT the true spend. Raise `max_jobs` in "
            "config.yaml to cover everything (this does not increase "
            "BigQuery cost - only the tool's memory and runtime)."
        )

    attr = attribution.attribute(config, jobs, human_only=config.get("human_only"))

    scan_bytes = meter["bytes_billed"]
    scan_cost = (
        query_cost_usd(config, scan_bytes) if scan_bytes else 0.0
    )

    result = {
        "dry_run": False,
        "project_id": project_id,
        "regions": regions,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pricing_origin": attr["pricing_origin"],
        "per_tib": attr["per_tib"],
        "scan_cost_usd": scan_cost,
        "scan_queries": meter["queries"],
        "jobs_truncated": jobs_truncated,
        "max_jobs": max_jobs,
        "warnings": warnings,
        "scan_cost_note": (
            "This number is what this metadata-only scan itself billed "
            "(INFORMATION_SCHEMA reads), separate from the warehouse's "
            "normal query spend; it is typically fractions of a cent "
            "or within the 1 TiB/month free tier."
            if attr["per_tib"] is not None
            else "Analysing by slot-hours; scan's own cost not shown in $."
        ),
        "totals": attr["totals"],
        "humans": attr["humans"],
        "service_accounts": attr["service_accounts"],
        "datasets": attr["datasets"],
        "top_queries": attr["top_queries"],
        # The community edition marks itself so consumers can tell it
        # apart from the full (paid) report.
        "_edition": "community",
    }

    return result


def cmd_cli(argv):
    import config as config_mod

    parser = argparse.ArgumentParser(
        prog="bq-cost-report",
        description="BigQuery cost attribution report (community edition).",
    )
    parser.add_argument("--project", help="BigQuery project id")
    parser.add_argument("--key", help="service account JSON key file")
    parser.add_argument("--days", type=int, help="lookback window in days")
    parser.add_argument("--datasets", help="comma-separated dataset filter")
    parser.add_argument("--human-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)

    overrides = {}
    if args.project:
        overrides["project_id"] = args.project
    if args.days:
        overrides["lookback_days"] = args.days
    if args.human_only:
        overrides["human_only"] = True
    if args.datasets:
        overrides["datasets"] = [
            d.strip() for d in args.datasets.split(",") if d.strip()
        ]

    config = load_runtime_config(overrides)

    if not config.get("project_id"):
        print("No project. Pass --project PROJECT_ID.")
        return 1

    if not args.dry_run:
        datasets = list(config.get("datasets") or [])
        if len(datasets) != 1:
            print(
                "This community edition analyses ONE dataset per run.\n"
                "Pass exactly one with --datasets YOUR_DATASET.\n"
                "Whole-project (or multi-dataset) scanning is a feature of "
                "the full edition - email alex.vinter24@gmail.com."
            )
            return 1

    if args.dry_run:
        result = run_scan(config, filename=args.key, dry_run=True)
        print(json.dumps(result, indent=2, default=str))
        return 0

    result = run_scan(config, filename=args.key)

    report_dir = config_mod.output_paths(config)
    import report
    report.write_json(report_dir, result)
    path = report.build_report(report_dir, result)

    print(f"Report written to: {path}")
    return 0


def main():
    argv = sys.argv[1:]

    if argv and argv[0] in ("--help", "-h", "help"):
        print(__doc__)
        return 0

    return cmd_cli(argv)


if __name__ == "__main__":
    sys.exit(main())

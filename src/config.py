"""Configuration loading.

Every scan reads its settings from config.yaml through this module, so
project, scope, pricing and report options are defined in exactly one
place.

Defaults are embedded here so the tool runs even without a config
file. The community edition omits the risk-check and storage pricing
keys that belong to the full edition.
"""

import copy
import os

import yaml

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(PROJECT_DIR, "config.yaml")

DEFAULTS = {
    # This build is the free community (trial) edition. Its defining
    # restriction is one-dataset-per-run scope; see app.py.
    "edition": "community",
    "project_id": None,
    "datasets": [],
    "location": "",
    "lookback_days": 30,
    # Max jobs analysed per region in the lookback window. Raising it
    # does not increase BigQuery cost (the metadata view bills on bytes
    # scanned, not rows returned) - only tool memory/runtime.
    "max_jobs": 100000,
    "human_only": False,
    "output_dir": "output",
    "auth": {
        "credentials_file": "",
    },
    "pricing": {
        "model": "on_demand",
        "currency": "USD",
        # Flat on-demand price per TiB scanned. $6.25/TiB is Google's
        # published on-demand rate and is the same in the US and the EU
        # and every region. Override with a negotiated rate in
        # config.pricing.per_tib_scanned.
        "per_tib_scanned": 6.25,
    },
    "safety": {
        "max_bytes_billed_gb": 200,
    },
    "report": {
        "organisation": "",
        "prepared_by": "",
        "limits": {
            "top_users": 10,
            "top_datasets": 10,
            "top_queries": 10,
        },
    },
}


def _merge(base, override):
    """Recursively overlay `override` on top of `base`."""

    result = copy.deepcopy(base)

    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value

    return result


def load_config(path=CONFIG_FILE, overrides=None, require_project=False):
    """Load configuration from file and command line.

    File beats defaults; overrides (command-line choices) beat the file.
    """

    user_config = {}

    full_path = path

    if path and os.path.exists(path):
        full_path = os.path.abspath(path)
        with open(full_path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
    elif path is None:
        full_path = CONFIG_FILE

    config = _merge(DEFAULTS, user_config)

    config["_config_dir"] = os.path.dirname(full_path)

    if overrides:
        config = _merge(config, overrides)

    if require_project and not config.get("project_id"):
        raise ValueError(
            "No project selected. Choose a project to continue."
        )

    return config


def output_paths(config):
    """Where this project's results are written."""

    project_id = config["project_id"]

    directory = config.get("output_dir") or "output"

    if not os.path.isabs(directory):
        base = config.get("_config_dir") or PROJECT_DIR
        directory = os.path.join(base, directory)

    directory = os.path.join(directory, project_id)

    os.makedirs(directory, exist_ok=True)

    return {
        "directory": directory,
        "findings": os.path.join(directory, "findings.json"),
        "cost": os.path.join(directory, "cost-attribution.json"),
        "report": os.path.join(directory, f"{project_id}-cost-report.pdf"),
    }

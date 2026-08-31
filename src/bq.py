"""Shared BigQuery client and authentication.

One way to authenticate: a service account key file. Drop the JSON
key into secrets/ and it is found; point `auth.credentials_file` at
one to pin it.

There is deliberately no other path - no Application Default
Credentials, no gcloud login, no GOOGLE_APPLICATION_CREDENTIALS.
A scan has to run as the identity the client granted and handed
over, so that it behaves the same on every machine and can never
quietly borrow whoever happens to be logged in locally.
"""

import os

from google.cloud import bigquery
from google.oauth2 import service_account

from safety import assert_read_only, max_bytes_billed, quote_region_dataset

TOOL_LABEL = "bq-cost-report"
TOOL_MARKER = f"-- {TOOL_LABEL}"

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_DIR = os.path.dirname(PROJECT_DIR)

# Where credentials can live. In the container/Dockerfile the user's
# keys are mounted at /app/secrets (the package root, beside
# config.yaml), while in a bare source checkout they may sit beside
# the code in src/secrets. Both are searched.
SECRETS_DIRS = [
    os.path.join(PACKAGE_DIR, "secrets"),
    os.path.join(PROJECT_DIR, "secrets"),
]

_clients = {}


class MissingCredentials(Exception):
    """No service account key file was configured."""


def _auth_settings(config):
    return config.get("auth") or {}


def _key_file_candidates(path, config):
    """Where a configured key file could be, most likely first."""

    path = os.path.expanduser(os.path.expandvars(path))

    if os.path.isabs(path):
        return [path]

    bases = []

    for base in (config.get("_config_dir"), PROJECT_DIR, PACKAGE_DIR):
        if base and base not in bases:
            bases.append(base)

    return [os.path.join(base, path) for base in bases]


def discover_key_files(config):
    """Every JSON key in the secrets/ folder, or the pinned file.

    Returns a list of (filename, absolute_path). If a key is pinned
    in auth.credentials_file it is returned on its own (even if it
    also lives in secrets/).
    """

    pinned = (_auth_settings(config).get("credentials_file") or "").strip()

    results = []

    if pinned:
        for candidate in _key_file_candidates(pinned, config):
            if os.path.exists(candidate):
                return [(os.path.basename(candidate), candidate)]
        return []

    seen = set()

    for secrets_dir in SECRETS_DIRS:
        if not os.path.isdir(secrets_dir):
            continue
        for name in sorted(os.listdir(secrets_dir)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(secrets_dir, name)
            if path not in seen:
                seen.add(path)
                results.append((name, path))

    return results


def key_file_path(config, filename=None):
    """Resolve the key file to use, raising on absence."""

    pinned = (_auth_settings(config).get("credentials_file") or "").strip()

    if filename:
        candidates = _key_file_candidates(filename, config)
    elif pinned:
        candidates = _key_file_candidates(pinned, config)
    else:
        found = discover_key_files(config)
        if len(found) == 1:
            candidates = [found[0][1]]
        else:
            raise MissingCredentials(
                "No service account key file. Put the JSON key in "
                f"into the secrets/ folder and it will be found automatically."
            )

    path = next((c for c in candidates if os.path.exists(c)), None)

    if path is None:
        raise FileNotFoundError(
            "Service account key file not found. Looked for "
            f"{filename or pinned!r} in: " + ", ".join(candidates)
        )

    return path


def load_credentials(config, filename=None):
    """Return credentials for the chosen service account key file."""

    path = key_file_path(config, filename)

    credentials = service_account.Credentials.from_service_account_file(
        path,
        scopes=SCOPES,
    )

    return credentials, (
        f"service account key: {credentials.service_account_email}"
    )


def get_client(config, filename=None):
    """Return a cached BigQuery client for the configured project."""

    project_id = config["project_id"]

    if not project_id:
        # As late as possible, fall back to the key's own project.
        credentials, _ = load_credentials(config, filename)
        project_id = credentials.project_id or ""
        config["project_id"] = project_id

    auth = _auth_settings(config)
    key = (project_id, filename or auth.get("credentials_file"))

    if key not in _clients:
        credentials, _ = load_credentials(config, filename)
        _clients[key] = bigquery.Client(
            project=project_id,
            credentials=credentials,
        )

    return _clients[key]


def run_query(config, sql, location=None, filename=None, meter=None):
    """Run a read-only query and return the rows as a list.

    If `meter` is a dict it is updated with the bytes this run's own
    query processed and a query count. The scan records this so the
    report can show -- transparently to the buyer -- what the metadata
    scan itself cost, which is separate from (and much smaller than)
    the warehouse's normal query spend.
    """

    assert_read_only(sql)

    client = get_client(config, filename)

    job_config = bigquery.QueryJobConfig(
        labels={"tool": TOOL_LABEL},
        maximum_bytes_billed=max_bytes_billed(config),
    )

    job = client.query(
        f"{TOOL_MARKER}\n{sql}",
        location=location,
        job_config=job_config,
    )

    rows = list(job.result())

    if meter is not None:
        meter["bytes_billed"] += job.total_bytes_billed or 0
        meter["queries"] += 1

    return rows


def list_projects(config, filename=None):
    """Projects this identity can access (metadata only).

    Used by the web app's discovery step so the user never has to
    type a project id.
    """

    client = get_client(config, filename)
    projects = []

    for project in client.list_projects():
        projects.append(
            {
                "project_id": project.project_id,
                "numeric_id": getattr(project, "number", None),
            }
        )

    return projects


def list_datasets(config, project_id, filename=None):
    """Datasets in a project this identity can see (metadata only)."""

    client = get_client(config, filename)

    datasets = []

    # list_datasets() returns light-weight DatasetListItem objects that
    # do NOT expose a .location attribute in this client version, so read
    # it defensively. Location is cosmetic in the UI only; region for the
    # actual scan comes from project metadata, not per-dataset.
    for dataset in client.list_datasets(project=project_id):
        datasets.append(
            {
                "dataset_id": dataset.dataset_id,
                "location": getattr(dataset, "location", None),
            }
        )

    return datasets


def list_tables(config, project_id, dataset_id, filename=None):
    """Tables in a dataset (metadata only, just names + sizes-signal)."""

    client = get_client(config, filename)

    tables = []

    for table in client.list_tables(f"{project_id}.{dataset_id}"):
        tables.append(
            {
                "table_id": table.table_id,
                "table_type": table.table_type,
            }
        )

    return tables

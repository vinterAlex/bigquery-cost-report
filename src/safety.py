"""Read-only enforcement.

The cost report only ever needs to read. This module makes that a
property of the code rather than a promise in the documentation:
every statement is checked before it reaches BigQuery, and a byte
ceiling stops a mistake from becoming an invoice.

A client can be shown this file as the answer to "prove it cannot
touch our data".
"""

import re


class UnsafeQuery(Exception):
    """Raised when a statement is not a plain read."""


LINE_COMMENT = re.compile(r"--[^\n]*")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

# Anything that creates, changes or removes something. Checked as
# whole words so a column called "update_time" is not a false alarm.
FORBIDDEN = (
    "insert", "update", "delete", "merge", "truncate", "drop",
    "create", "alter", "grant", "revoke", "replace", "load",
    "export", "call", "execute",
)

FORBIDDEN_PATTERN = re.compile(
    r"\b(" + "|".join(FORBIDDEN) + r")\b",
    re.IGNORECASE,
)

STRING_LITERAL = re.compile(r"'[^']*'|\"[^\"]*\"")


def strip_noise(sql):
    """Remove comments and string literals, leaving structure."""

    sql = LINE_COMMENT.sub(" ", sql or "")
    sql = STRING_LITERAL.sub("''", sql)
    sql = BLOCK_COMMENT.sub(" ", sql)

    return sql


def assert_read_only(sql):
    """Raise UnsafeQuery unless this is a single read statement."""

    if not sql or not sql.strip():
        raise UnsafeQuery("Empty statement")

    cleaned = strip_noise(sql).strip()

    if ";" in cleaned.rstrip().rstrip(";"):
        raise UnsafeQuery("Multiple statements are not allowed")

    first = cleaned.lstrip("( \t\r\n").split(None, 1)

    if not first:
        raise UnsafeQuery("Empty statement")

    keyword = first[0].lower()

    if keyword not in ("select", "with"):
        raise UnsafeQuery(
            f"Only SELECT and WITH are allowed, this starts with "
            f"'{first[0]}'"
        )

    match = FORBIDDEN_PATTERN.search(cleaned)

    if match:
        raise UnsafeQuery(
            f"Statement contains the keyword '{match.group(1)}', which "
            "the cost report is not permitted to run"
        )

    return True


def max_bytes_billed(config):
    """Ceiling for a single query, in bytes, or None for no limit."""

    limit_gb = (config.get("safety") or {}).get("max_bytes_billed_gb")

    if not limit_gb:
        return None

    return int(float(limit_gb) * 1024 ** 3)


# ---------------------------------------------------------
# Identifiers
# ---------------------------------------------------------

VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-]*$")

# INFORMATION_SCHEMA names may contain a hyphen in the region, e.g.
# `project`.`region-eu`.INFORMATION_SCHEMA.JOBS_BY_PROJECT, so a
# looser pattern is used where such names flow through.
GCP_RESOURCE = re.compile(r"^[A-Za-z0-9_\-\.:]+$")


def quote_region_dataset(region, schema):
    """Back-tick-quote a `<region>.INFORMATION_SCHEMA.<schema>` name.

    BigQuery requires the region to be present and lowercase (e.g.
    `region-eu`) for the per-location metadata views. An empty region
    produces an invalid, unqualified name ("invalid empty identifier"),
    so we refuse rather than emit a broken query.
    """

    if not region:
        raise UnsafeQuery(
            "Missing region: BigQuery metadata views need a location "
            "(e.g. eu, us, us-central1). Set the region or let discovery "
            "detect it."
        )

    region = str(region).strip().lower()

    if not GCP_RESOURCE.match(region):
        raise UnsafeQuery(f"Refusing to use identifier: {region!r}")

    if not GCP_RESOURCE.match(str(schema)):
        raise UnsafeQuery(f"Refusing to use identifier: {schema!r}")

    return f"`region-{region}`.INFORMATION_SCHEMA.{schema}"

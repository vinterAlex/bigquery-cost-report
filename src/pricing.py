"""BigQuery pricing (on-demand analysis).

BigQuery on-demand analysis is billed per TiB of data scanned. As of
Google's current published pricing the on-demand analysis rate is the
same in every region - $6.25/TiB for the US multi-region, the EU
multi-region, and every single region (us-central1, europe-west1, ...).
There is no regional variation any more, so we use one flat default.

The default is correct and it is always visible/changeable:

  * if the buyer has a negotiated or different rate they set it in
    config `pricing.per_tib_scanned` (or the web app's "Price per TiB"
    field), and that value is used - for the US and EU alike;
  * otherwise we fall back to the flat $6.25/TiB default.

We deliberately DO NOT try to read the price live from the Cloud
Billing Catalog API: the BigQuery service SKUs mix on-demand analysis
with capacity/Editions slot-hour SKUs (and Omni's separate $9.125/TiB),
so a naive lookup can return a *wrong* number and silently replace the
correct $6.25. A correct, predictable, changeable default beats an
unreliable live scrape. `location`/`region` is accepted for API
compatibility but no longer changes the price.

Capacity (Editions / slots) is a different meter entirely; under
`pricing.model: capacity` we report no per-TiB query price (None) and
the report says "n/a (capacity pricing)" rather than pretending to be
on-demand.
"""

# Flat on-demand analysis price per TiB scanned. Same for the US and
# the EU and every region (Google's current published pricing). This is
# the default; a buyer's own negotiated rate overrides it.
DEFAULT_PER_TIB = 6.25

# Backwards-compatible name: callers may import FALLBACK_PER_TIB.
FALLBACK_PER_TIB = DEFAULT_PER_TIB

DEFAULT_ORIGIN = (
    f"default on-demand price (${DEFAULT_PER_TIB}/TiB, "
    "same for the US and the EU and all regions)"
)


class PricingError(Exception):
    """Pricing could not be resolved."""


def resolve_per_tib(config, location=None):
    """The on-demand price per TiB to use.

    Precedence:
      1. A value the buyer explicitly set in config/pricing
         (`per_tib_scanned`) or the web app's "Price per TiB" field,
      2. The flat $6.25/TiB default (US and EU and every region).

    `location` is accepted for API compatibility but does not affect
    the price, because on-demand analysis is region-independent.

    Returns (amount, origin) where origin is a short explanation of
    which source was used.
    """

    # Under capacity/Editions pricing the meter is slot-hours, not
    # $/TiB. Report no per-TiB price so nothing claims to be on-demand.
    if not is_on_demand(config):
        return None, "capacity pricing (slot-hours, not on-demand)"

    configured = (config.get("pricing") or {}).get("per_tib_scanned")

    if configured is not None and configured != "":
        return float(configured), "configured value (buyer's rate)"

    return DEFAULT_PER_TIB, DEFAULT_ORIGIN


def currency(config):
    return (config.get("pricing") or {}).get("currency", "USD")


def is_on_demand(config):
    return (config.get("pricing") or {}).get("model", "on_demand") == "on_demand"


def query_cost_usd(config, bytes_billed, location=None):
    """Dollar cost of scanning this many bytes, or None under capacity."""

    if not is_on_demand(config):
        return None

    per_tib, _ = resolve_per_tib(config, location)

    return (bytes_billed or 0) / (1024 ** 4) * per_tib


def storage_cost_per_month(config, active_bytes, long_term_bytes=0, location=None):
    """Monthly storage cost for a table."""

    pricing = config.get("pricing") or {}

    active_rate = pricing.get("active_storage_per_gib_month", 0.02)
    long_rate = pricing.get("long_term_storage_per_gib_month", 0.01)

    gib = 1024 ** 3

    return (
        (active_bytes or 0) / gib * active_rate
        + (long_term_bytes or 0) / gib * long_rate
    )

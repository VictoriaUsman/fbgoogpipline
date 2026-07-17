"""Pure-function validation for bronze-zone records, consumed by
`glue_jobs/bronze_to_silver.py`.

Two separate concerns, deliberately not conflated:

- `validate_record()` answers "is this record well-formed enough to load" -- a hard
  gate. Returns a reason string on failure, `None` on success. No exceptions, no side
  effects: this makes it trivial to unit test and safe to call from a tight loop over
  tens of thousands of lines without try/except overhead.
- `detect_new_fields()` answers "does this record contain a key we don't recognize" --
  a schema-drift *signal*, not a gate. An unrecognized field never fails a record; it is
  surfaced as a CloudWatch metric so a human notices a platform silently added a column
  before it becomes a silent gap in the warehouse schema.

Field sets are keyed by platform since Google Ads and Meta Ads report shapes are not
the same (see connectors/google_ads_connector.py and connectors/meta_ads_connector.py's
`_flatten_row` for where these names originate).
"""

from __future__ import annotations

from datetime import date

_COMMON_REQUIRED_FIELDS = (
    "date",
    "platform",
    "account_id",
    "account_name",
    "currency",
    "campaign_id",
    "campaign_name",
    "impressions",
    "clicks",
    "cost",
    "conversions",
)

REQUIRED_FIELDS_BY_PLATFORM: dict[str, tuple[str, ...]] = {
    "google_ads": _COMMON_REQUIRED_FIELDS,
    "meta_ads": _COMMON_REQUIRED_FIELDS,
}

_COMMON_KNOWN_FIELDS = set(_COMMON_REQUIRED_FIELDS) | {"conversions_value"}

KNOWN_FIELDS_BY_PLATFORM: dict[str, set[str]] = {
    "google_ads": _COMMON_KNOWN_FIELDS | {"channel_type"},
    "meta_ads": _COMMON_KNOWN_FIELDS,
}

NUMERIC_FIELD_CHECKS = ("impressions", "clicks", "cost", "conversions")


def validate_record(record: dict, platform: str) -> str | None:
    """Return a short reason string if `record` is invalid, else `None`.

    Checks, in order: platform recognized, required fields present and non-empty,
    `date` is ISO-8601, every field in NUMERIC_FIELD_CHECKS is a non-negative number.
    """
    required_fields = REQUIRED_FIELDS_BY_PLATFORM.get(platform)
    if required_fields is None:
        return f"unknown platform: {platform!r}"

    for field in required_fields:
        value = record.get(field)
        if value is None or value == "":
            return f"missing required field: {field}"

    date_value = record.get("date")
    try:
        date.fromisoformat(str(date_value))
    except ValueError:
        return f"date not ISO-8601: {date_value!r}"

    for field in NUMERIC_FIELD_CHECKS:
        value = record.get(field)
        if value is None:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return f"field {field} is not numeric: {value!r}"
        if value < 0:
            return f"field {field} is negative: {value!r}"

    return None


def detect_new_fields(record: dict, platform: str) -> set[str]:
    """Return the set of keys in `record` that fall outside the known schema for `platform`.

    Empty set means no drift. Never used as a rejection reason -- callers only ever
    emit this as a metric/log signal.
    """
    known_fields = KNOWN_FIELDS_BY_PLATFORM.get(platform, set())
    return set(record.keys()) - known_fields

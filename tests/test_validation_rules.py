from validation.rules import detect_new_fields, validate_record

VALID_GOOGLE_RECORD = {
    "date": "2026-07-03",
    "platform": "google_ads",
    "account_id": "111-222-3333",
    "account_name": "Acme Retail",
    "currency": "USD",
    "campaign_id": "7001001",
    "campaign_name": "Search - Brand",
    "impressions": 1000,
    "clicks": 50,
    "cost": 123.45,
    "conversions": 4.0,
    "conversions_value": 200.0,
    "channel_type": "SEARCH",
}

VALID_META_RECORD = {
    "date": "2026-07-03",
    "platform": "meta_ads",
    "account_id": "act_10150123456789",
    "account_name": "Acme Retail",
    "currency": "USD",
    "campaign_id": "23860222000001",
    "campaign_name": "Lead Gen - Decision Makers",
    "impressions": 2000,
    "clicks": 80,
    "cost": 55.5,
    "conversions": 2.0,
    "conversions_value": 100.0,
}


def test_valid_google_ads_record_passes():
    assert validate_record(VALID_GOOGLE_RECORD, "google_ads") is None


def test_valid_meta_ads_record_passes():
    assert validate_record(VALID_META_RECORD, "meta_ads") is None


def test_unknown_platform_is_rejected():
    reason = validate_record(VALID_GOOGLE_RECORD, "tiktok_ads")
    assert reason == "unknown platform: 'tiktok_ads'"


def test_missing_required_field_is_rejected():
    record = {**VALID_GOOGLE_RECORD}
    del record["campaign_name"]
    assert validate_record(record, "google_ads") == "missing required field: campaign_name"


def test_empty_string_required_field_is_rejected():
    record = {**VALID_GOOGLE_RECORD, "account_name": ""}
    assert validate_record(record, "google_ads") == "missing required field: account_name"


def test_none_required_field_is_rejected():
    record = {**VALID_GOOGLE_RECORD, "campaign_id": None}
    assert validate_record(record, "google_ads") == "missing required field: campaign_id"


def test_non_iso8601_date_is_rejected():
    record = {**VALID_GOOGLE_RECORD, "date": "07/03/2026"}
    assert validate_record(record, "google_ads") == "date not ISO-8601: '07/03/2026'"


def test_negative_cost_is_rejected():
    record = {**VALID_GOOGLE_RECORD, "cost": -698.42}
    assert validate_record(record, "google_ads") == "field cost is negative: -698.42"


def test_negative_impressions_is_rejected():
    record = {**VALID_GOOGLE_RECORD, "impressions": -1}
    assert validate_record(record, "google_ads") == "field impressions is negative: -1"


def test_non_numeric_clicks_is_rejected():
    record = {**VALID_GOOGLE_RECORD, "clicks": "fifty"}
    assert validate_record(record, "google_ads") == "field clicks is not numeric: 'fifty'"


def test_boolean_is_rejected_as_non_numeric():
    # bool is an int subclass in Python; validate_record must not silently accept it.
    record = {**VALID_GOOGLE_RECORD, "conversions": True}
    assert validate_record(record, "google_ads") == "field conversions is not numeric: True"


def test_numeric_field_check_skips_none_since_required_check_already_caught_it():
    # conversions_value is not in the required set, so a None there is fine.
    record = {**VALID_GOOGLE_RECORD, "conversions_value": None}
    assert validate_record(record, "google_ads") is None


def test_detect_new_fields_empty_for_known_schema():
    assert detect_new_fields(VALID_GOOGLE_RECORD, "google_ads") == set()
    assert detect_new_fields(VALID_META_RECORD, "meta_ads") == set()


def test_detect_new_fields_flags_unrecognized_key():
    record = {**VALID_META_RECORD, "audience_segment": "lookalike-1pct"}
    assert detect_new_fields(record, "meta_ads") == {"audience_segment"}


def test_detect_new_fields_is_platform_specific():
    # channel_type is known for google_ads but not for meta_ads.
    record = {**VALID_META_RECORD, "channel_type": "SEARCH"}
    assert detect_new_fields(record, "meta_ads") == {"channel_type"}
    assert detect_new_fields(VALID_GOOGLE_RECORD, "google_ads") == set()


def test_detect_new_fields_never_used_as_a_rejection_reason():
    # A record with drift still validates cleanly -- drift is a signal, not a gate.
    record = {**VALID_META_RECORD, "audience_segment": "lookalike-1pct"}
    assert validate_record(record, "meta_ads") is None

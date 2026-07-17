-- SQLite stand-in for redshift/create_tables.sql, used only by local_runner/run_pipeline.py
-- since this project has no live Redshift Serverless workgroup to run the real DDL
-- against (matching the Amazon Ads reference pipeline's own "boilerplate, nothing
-- deployed" status). Same tables, same columns, same keys -- Redshift-only syntax
-- (DISTSTYLE, SORTKEY, IDENTITY) is dropped since SQLite has no equivalent, but the
-- logical schema and every constraint that matters for correctness (PKs, the SCD2
-- valid_from/valid_to/is_current shape) is preserved exactly.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dim_platform (
    platform            TEXT NOT NULL PRIMARY KEY,
    display_name        TEXT NOT NULL
);

INSERT OR IGNORE INTO dim_platform (platform, display_name) VALUES
    ('google_ads', 'Google Ads'),
    ('meta_ads', 'Meta Ads');

CREATE TABLE IF NOT EXISTS dim_date (
    date_key            TEXT NOT NULL PRIMARY KEY,
    year                INTEGER NOT NULL,
    month               INTEGER NOT NULL,
    day                 INTEGER NOT NULL,
    day_of_week         INTEGER NOT NULL,
    is_weekend          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_account (
    dim_account_key     INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id          TEXT NOT NULL,
    platform            TEXT NOT NULL,
    account_name        TEXT NOT NULL,
    currency            TEXT NOT NULL,
    valid_from          TEXT NOT NULL,
    valid_to            TEXT,
    is_current          INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS staging_account (
    account_id          TEXT,
    platform            TEXT,
    account_name        TEXT,
    currency            TEXT
);

CREATE TABLE IF NOT EXISTS dim_campaign (
    dim_campaign_key    INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id         TEXT NOT NULL,
    account_id          TEXT NOT NULL,
    platform            TEXT NOT NULL,
    campaign_name       TEXT NOT NULL,
    channel_type        TEXT,
    valid_from          TEXT NOT NULL,
    valid_to            TEXT,
    is_current          INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS staging_campaign (
    campaign_id         TEXT,
    account_id          TEXT,
    platform            TEXT,
    campaign_name       TEXT,
    channel_type        TEXT
);

CREATE TABLE IF NOT EXISTS staging_campaign_performance (
    platform            TEXT,
    account_id          TEXT,
    account_name        TEXT,
    currency             TEXT,
    campaign_id         TEXT,
    campaign_name       TEXT,
    channel_type        TEXT,
    report_date         TEXT,
    impressions         INTEGER,
    clicks              INTEGER,
    cost                REAL,
    conversions         REAL,
    conversions_value   REAL
);

CREATE TABLE IF NOT EXISTS fct_campaign_performance (
    platform            TEXT NOT NULL REFERENCES dim_platform (platform),
    account_id          TEXT NOT NULL,
    campaign_id         TEXT NOT NULL,
    report_date         TEXT NOT NULL REFERENCES dim_date (date_key),
    campaign_name       TEXT NOT NULL,
    impressions         INTEGER NOT NULL,
    clicks              INTEGER NOT NULL,
    cost                REAL NOT NULL,
    conversions         REAL NOT NULL,
    conversions_value   REAL NOT NULL,
    updated_at          TEXT NOT NULL,
    PRIMARY KEY (platform, account_id, campaign_id, report_date)
);

CREATE TABLE IF NOT EXISTS fct_campaign_performance_history (
    platform            TEXT NOT NULL,
    account_id          TEXT NOT NULL,
    campaign_id         TEXT NOT NULL,
    report_date         TEXT NOT NULL,
    impressions         INTEGER NOT NULL,
    clicks              INTEGER NOT NULL,
    cost                REAL NOT NULL,
    conversions         REAL NOT NULL,
    conversions_value   REAL NOT NULL,
    valid_from          TEXT NOT NULL,
    valid_to            TEXT,
    is_current          INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (platform, account_id, campaign_id, report_date, valid_from)
);

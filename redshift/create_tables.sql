-- Target Redshift Serverless schema for the Google Ads + Meta Ads pipeline.
--
-- Star-schema-ish, SCD2-heavy, mirroring the Amazon Ads reference pipeline's design:
--   * dim_account / dim_campaign are SCD Type 2 (account/campaign metadata changes --
--     renames, currency changes -- over time; fct_campaign_performance rows must stay
--     attributable to the metadata that was true on that report_date).
--   * fct_campaign_performance is a plain upsert-by-natural-key fact (staging is fully
--     reloaded from the complete silver/ zone every run, so an unconditional MERGE is
--     correct -- see merge_fct_campaign_performance.sql).
--   * fct_campaign_performance_history is a companion change-detected history table,
--     SCD2-shaped the same way the dimensions are, so a metric revision (e.g. a
--     late-arriving conversion changing `conversions` for a day already loaded) is
--     preserved rather than silently overwritten.
--
-- fct_campaign_performance's foreign keys point only at dim_platform/dim_date, not at
-- dim_account/dim_campaign -- once those are SCD2, `account_id`/`campaign_id` are no
-- longer unique keys on their own (same reasoning as the Amazon Ads reference schema).

CREATE TABLE IF NOT EXISTS dim_platform (
    platform            VARCHAR(32)  NOT NULL PRIMARY KEY,
    display_name        VARCHAR(64)  NOT NULL
) DISTSTYLE ALL;

INSERT INTO dim_platform (platform, display_name) VALUES
    ('google_ads', 'Google Ads'),
    ('meta_ads', 'Meta Ads')
ON CONFLICT (platform) DO NOTHING;

CREATE TABLE IF NOT EXISTS dim_date (
    date_key            DATE         NOT NULL PRIMARY KEY,
    year                SMALLINT     NOT NULL,
    month               SMALLINT     NOT NULL,
    day                 SMALLINT     NOT NULL,
    day_of_week         SMALLINT     NOT NULL,
    is_weekend          BOOLEAN      NOT NULL
) DISTSTYLE ALL;

-- SCD2 dimension: account/advertiser metadata (see scd2_dim_account_close.sql / _insert.sql)
CREATE TABLE IF NOT EXISTS dim_account (
    dim_account_key     BIGINT IDENTITY(1, 1) PRIMARY KEY,
    account_id          VARCHAR(64)  NOT NULL,
    platform            VARCHAR(32)  NOT NULL,
    account_name        VARCHAR(256) NOT NULL,
    currency            VARCHAR(8)   NOT NULL,
    valid_from          DATE         NOT NULL,
    valid_to            DATE,
    is_current          BOOLEAN      NOT NULL DEFAULT TRUE
) DISTSTYLE ALL SORTKEY (account_id, platform, valid_from);

CREATE TABLE IF NOT EXISTS staging_account (
    account_id          VARCHAR(64),
    platform            VARCHAR(32),
    account_name        VARCHAR(256),
    currency            VARCHAR(8)
);

CREATE VIEW dim_account_current AS
    SELECT * FROM dim_account WHERE is_current = TRUE;

-- SCD2 dimension: campaign metadata (see scd2_dim_campaign_close.sql / _insert.sql)
CREATE TABLE IF NOT EXISTS dim_campaign (
    dim_campaign_key    BIGINT IDENTITY(1, 1) PRIMARY KEY,
    campaign_id         VARCHAR(64)  NOT NULL,
    account_id          VARCHAR(64)  NOT NULL,
    platform            VARCHAR(32)  NOT NULL,
    campaign_name        VARCHAR(512) NOT NULL,
    channel_type        VARCHAR(64), -- Google Ads only (e.g. SEARCH, SHOPPING); NULL for Meta
    valid_from          DATE         NOT NULL,
    valid_to            DATE,
    is_current          BOOLEAN      NOT NULL DEFAULT TRUE
) DISTSTYLE ALL SORTKEY (campaign_id, platform, valid_from);

CREATE TABLE IF NOT EXISTS staging_campaign (
    campaign_id         VARCHAR(64),
    account_id          VARCHAR(64),
    platform            VARCHAR(32),
    campaign_name        VARCHAR(512),
    channel_type        VARCHAR(64)
);

CREATE VIEW dim_campaign_current AS
    SELECT * FROM dim_campaign WHERE is_current = TRUE;

-- TRUNCATE + COPY scratch table for the full silver/ zone every run (see copy_into_staging.sql)
CREATE TABLE IF NOT EXISTS staging_campaign_performance (
    platform            VARCHAR(32),
    account_id          VARCHAR(64),
    account_name        VARCHAR(256),
    currency            VARCHAR(8),
    campaign_id         VARCHAR(64),
    campaign_name        VARCHAR(512),
    channel_type        VARCHAR(64),
    report_date         DATE,
    impressions         BIGINT,
    clicks              BIGINT,
    cost                NUMERIC(18, 4),
    conversions         NUMERIC(18, 4),
    conversions_value   NUMERIC(18, 4)
);

CREATE TABLE IF NOT EXISTS fct_campaign_performance (
    platform            VARCHAR(32)     NOT NULL REFERENCES dim_platform (platform),
    account_id          VARCHAR(64)     NOT NULL,
    campaign_id         VARCHAR(64)     NOT NULL,
    report_date         DATE            NOT NULL REFERENCES dim_date (date_key),
    campaign_name        VARCHAR(512)    NOT NULL,
    impressions         BIGINT          NOT NULL,
    clicks              BIGINT          NOT NULL,
    cost                NUMERIC(18, 4)  NOT NULL,
    conversions         NUMERIC(18, 4)  NOT NULL,
    conversions_value   NUMERIC(18, 4)  NOT NULL,
    updated_at          TIMESTAMP       NOT NULL DEFAULT GETDATE(),
    PRIMARY KEY (platform, account_id, campaign_id, report_date)
) DISTKEY (account_id) SORTKEY (report_date, platform, account_id);

CREATE TABLE IF NOT EXISTS fct_campaign_performance_history (
    platform            VARCHAR(32)     NOT NULL,
    account_id          VARCHAR(64)     NOT NULL,
    campaign_id         VARCHAR(64)     NOT NULL,
    report_date         DATE            NOT NULL,
    impressions         BIGINT          NOT NULL,
    clicks              BIGINT          NOT NULL,
    cost                NUMERIC(18, 4)  NOT NULL,
    conversions         NUMERIC(18, 4)  NOT NULL,
    conversions_value   NUMERIC(18, 4)  NOT NULL,
    valid_from          TIMESTAMP       NOT NULL,
    valid_to            TIMESTAMP,
    is_current          BOOLEAN         NOT NULL DEFAULT TRUE,
    PRIMARY KEY (platform, account_id, campaign_id, report_date, valid_from)
) DISTKEY (account_id) SORTKEY (report_date, platform, account_id);

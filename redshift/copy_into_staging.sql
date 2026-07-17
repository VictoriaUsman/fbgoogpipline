-- Run by redshift_load.asl.json's CopyIntoStaging state (token: ${CopyIntoStagingSql}).
-- Staging is fully truncated and reloaded from the complete silver/ zone every run --
-- not append-only -- which is what makes the unconditional MERGE in
-- merge_fct_campaign_performance.sql correct (no stale rows can survive a truncate).

TRUNCATE staging_campaign_performance;

COPY staging_campaign_performance
FROM '${SilverS3Prefix}'
IAM_ROLE '${RedshiftIamRoleArn}'
FORMAT AS JSON 'auto'
DATEFORMAT 'auto';

-- Refresh the two SCD2 staging tables from the same load for dim_account/dim_campaign
-- to upsert against (see scd2_dim_account_*.sql / scd2_dim_campaign_*.sql).
TRUNCATE staging_account;
INSERT INTO staging_account (account_id, platform, account_name, currency)
SELECT DISTINCT account_id, platform, account_name, currency
FROM staging_campaign_performance;

TRUNCATE staging_campaign;
INSERT INTO staging_campaign (campaign_id, account_id, platform, campaign_name, channel_type)
SELECT DISTINCT campaign_id, account_id, platform, campaign_name, channel_type
FROM staging_campaign_performance;

-- Backfill dim_date for any report_date not already present.
INSERT INTO dim_date (date_key, year, month, day, day_of_week, is_weekend)
SELECT DISTINCT
    report_date,
    EXTRACT(year FROM report_date),
    EXTRACT(month FROM report_date),
    EXTRACT(day FROM report_date),
    EXTRACT(dow FROM report_date),
    EXTRACT(dow FROM report_date) IN (0, 6)
FROM staging_campaign_performance s
WHERE NOT EXISTS (SELECT 1 FROM dim_date d WHERE d.date_key = s.report_date);

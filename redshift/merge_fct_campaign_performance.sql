-- Native Redshift MERGE, unconditional update on match. Correct here (unlike a
-- recency-gated upsert) because staging_campaign_performance is fully truncated and
-- reloaded from the complete silver/ zone every run (see copy_into_staging.sql) -- there
-- is never a stale staging row to accidentally clobber a newer fact row with.

MERGE INTO fct_campaign_performance
USING staging_campaign_performance AS source
ON fct_campaign_performance.platform = source.platform
   AND fct_campaign_performance.account_id = source.account_id
   AND fct_campaign_performance.campaign_id = source.campaign_id
   AND fct_campaign_performance.report_date = source.report_date
WHEN MATCHED THEN UPDATE SET
    campaign_name = source.campaign_name,
    impressions = source.impressions,
    clicks = source.clicks,
    cost = source.cost,
    conversions = source.conversions,
    conversions_value = source.conversions_value,
    updated_at = GETDATE()
WHEN NOT MATCHED THEN INSERT (
    platform, account_id, campaign_id, report_date, campaign_name,
    impressions, clicks, cost, conversions, conversions_value, updated_at
) VALUES (
    source.platform, source.account_id, source.campaign_id, source.report_date, source.campaign_name,
    source.impressions, source.clicks, source.cost, source.conversions, source.conversions_value, GETDATE()
);

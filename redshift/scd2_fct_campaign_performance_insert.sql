-- SCD2 fct_campaign_performance_history, step 2 of 2 (run after
-- scd2_fct_campaign_performance_close.sql). Opens a fresh current row for every staging
-- row with no matching unchanged current history row.

INSERT INTO fct_campaign_performance_history (
    platform, account_id, campaign_id, report_date,
    impressions, clicks, cost, conversions, conversions_value,
    valid_from, valid_to, is_current
)
SELECT
    s.platform, s.account_id, s.campaign_id, s.report_date,
    s.impressions, s.clicks, s.cost, s.conversions, s.conversions_value,
    GETDATE(), NULL, TRUE
FROM staging_campaign_performance s
LEFT JOIN fct_campaign_performance_history h
  ON h.platform = s.platform
 AND h.account_id = s.account_id
 AND h.campaign_id = s.campaign_id
 AND h.report_date = s.report_date
 AND h.is_current = TRUE
WHERE h.platform IS NULL;

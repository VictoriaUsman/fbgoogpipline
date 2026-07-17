-- SCD2 fct_campaign_performance_history, step 1 of 2. Change-detected on every measure
-- (not just any staging row, unlike the dimension tables above) -- a day's numbers only
-- get a new history row if a metric actually changed since the last load, e.g. a
-- late-arriving conversion revising `conversions`/`conversions_value` for a date already
-- loaded in an earlier run.

UPDATE fct_campaign_performance_history
SET valid_to = GETDATE(), is_current = FALSE
FROM staging_campaign_performance s
WHERE fct_campaign_performance_history.platform = s.platform
  AND fct_campaign_performance_history.account_id = s.account_id
  AND fct_campaign_performance_history.campaign_id = s.campaign_id
  AND fct_campaign_performance_history.report_date = s.report_date
  AND fct_campaign_performance_history.is_current = TRUE
  AND (
        fct_campaign_performance_history.impressions IS DISTINCT FROM s.impressions
     OR fct_campaign_performance_history.clicks IS DISTINCT FROM s.clicks
     OR fct_campaign_performance_history.cost IS DISTINCT FROM s.cost
     OR fct_campaign_performance_history.conversions IS DISTINCT FROM s.conversions
     OR fct_campaign_performance_history.conversions_value IS DISTINCT FROM s.conversions_value
  );

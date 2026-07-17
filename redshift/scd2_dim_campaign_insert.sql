-- SCD2 dim_campaign, step 2 of 2 (run after scd2_dim_campaign_close.sql).

INSERT INTO dim_campaign (campaign_id, account_id, platform, campaign_name, channel_type, valid_from, valid_to, is_current)
SELECT DISTINCT s.campaign_id, s.account_id, s.platform, s.campaign_name, s.channel_type, CURRENT_DATE, NULL, TRUE
FROM staging_campaign s
LEFT JOIN dim_campaign d
  ON d.campaign_id = s.campaign_id
 AND d.platform = s.platform
 AND d.is_current = TRUE
WHERE d.dim_campaign_key IS NULL;

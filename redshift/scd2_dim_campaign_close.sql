-- SCD2 dim_campaign, step 1 of 2 (run before scd2_dim_campaign_insert.sql). Campaign
-- renames are the common real-world case this exists for (a manager renames a campaign
-- for clarity; historical fct_campaign_performance rows should still show the name that
-- was true on that report_date -- see dim_campaign_current for "what is it called now").

UPDATE dim_campaign
SET valid_to = CURRENT_DATE, is_current = FALSE
FROM staging_campaign s
WHERE dim_campaign.campaign_id = s.campaign_id
  AND dim_campaign.platform = s.platform
  AND dim_campaign.is_current = TRUE
  AND (
        dim_campaign.campaign_name IS DISTINCT FROM s.campaign_name
     OR dim_campaign.channel_type IS DISTINCT FROM s.channel_type
  );

-- SCD2 dim_account, step 1 of 2 (run before scd2_dim_account_insert.sql). Closes any
-- current row whose tracked attributes have drifted from staging. Redshift's MERGE
-- cannot express "close old + open new" in one statement, so this is always two files,
-- never a single MERGE -- same discipline as scd2_dim_campaign_*.sql below.

UPDATE dim_account
SET valid_to = CURRENT_DATE, is_current = FALSE
FROM staging_account s
WHERE dim_account.account_id = s.account_id
  AND dim_account.platform = s.platform
  AND dim_account.is_current = TRUE
  AND (
        dim_account.account_name IS DISTINCT FROM s.account_name
     OR dim_account.currency IS DISTINCT FROM s.currency
  );

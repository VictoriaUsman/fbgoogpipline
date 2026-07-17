-- SCD2 dim_account, step 2 of 2 (run after scd2_dim_account_close.sql). Opens a fresh
-- current row for every account in staging that has no matching current row -- either
-- brand new, or just closed by the previous statement because an attribute changed.

INSERT INTO dim_account (account_id, platform, account_name, currency, valid_from, valid_to, is_current)
SELECT DISTINCT s.account_id, s.platform, s.account_name, s.currency, CURRENT_DATE, NULL, TRUE
FROM staging_account s
LEFT JOIN dim_account d
  ON d.account_id = s.account_id
 AND d.platform = s.platform
 AND d.is_current = TRUE
WHERE d.dim_account_key IS NULL;

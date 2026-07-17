-- Run by lambda_handlers/reconciliation_check.py after every redshift_load execution.
-- Compares what was loaded into staging against what actually landed in the fact table
-- for the run's date range. Columns are parsed by name in the Lambda, not position.

SELECT
    (SELECT COUNT(*) FROM staging_campaign_performance
      WHERE report_date BETWEEN '{start_date}' AND '{end_date}') AS staging_rows,
    (SELECT COUNT(*) FROM fct_campaign_performance
      WHERE report_date BETWEEN '{start_date}' AND '{end_date}') AS fact_rows,
    (SELECT COALESCE(SUM(cost), 0) FROM staging_campaign_performance
      WHERE report_date BETWEEN '{start_date}' AND '{end_date}') AS staging_cost,
    (SELECT COALESCE(SUM(cost), 0) FROM fct_campaign_performance
      WHERE report_date BETWEEN '{start_date}' AND '{end_date}') AS fact_cost;

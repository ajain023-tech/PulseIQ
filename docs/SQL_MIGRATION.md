# Legacy BigQuery SQL → dbt on DuckDB

The v1 SQL (`legacy/sql/`) queried BigQuery tables that were never in the repo.
Every file is either mapped to a dbt model or superseded as listed below. BigQuery
idioms were translated as follows: `SAFE_DIVIDE(a, b)` → `a / nullif(b, 0)`;
`DATE_DIFF(a, b, DAY)` → `date_diff('day', b, a)`; `QUALIFY` is unchanged;
`COUNTIF(x)` → `count(*) filter (where x)`; `TIMESTAMP_ADD` → `ts + interval n day`.

| Legacy file | v2 model(s) | Notes |
|---|---|---|
| `01_data_quality.sql` | `stg_events`, `stg_*` + dbt tests | Dedupe, orphan and key checks became `unique` / `not_null` / `relationships` tests. Anonymous-id recovery is not needed because every generated event carries a `user_id`. |
| `02_funnel.sql` | `fct_funnel_user`, `agg_funnel_daily` | Same ordered-stage rule: a later stage counts only after the previous one. |
| `03_segmentation.sql` | `agg_funnel_by_segment` | Region became `country_tier`. Primary goal is not simulated. |
| `04_retention.sql` | `int_user_day_n_activity`, `agg_retention_cohorts` | Exact-day retention now uses 24 h blocks after signup and eligibility-aware denominators. |
| `05_monetization.sql` | `stg_invoices`, `int_subscription_periods`, `fct_revenue_daily`, `dim_users.lifetime_net_revenue_usd` | Adds MRR, ARPDAU and ARPPU. Trial → paid is in the funnel marts. |
| `06_ab_test_dataset.sql` | `fct_experiment_exposures` | Generalised from one experiment to all three, with pre-period covariates and in-test metrics. |
| `07_product_kpis.sql` | `agg_kpis_daily` | DAU / WAU / MAU / stickiness plus daily conversions. |
| `08_funnel_segment_analysis.sql` | `agg_funnel_by_segment` | Merged with 03. |
| `09_user_activity_analysis.sql` | `int_user_daily_activity`, `dim_users.lifetime_sessions` | Activity tiers can be derived from `lifetime_sessions`. |
| `10_funnel_summary.sql` | `agg_funnel_daily` (sum over dates) | Superseded: the overall summary is a single aggregate query on the mart. |
| `11_cohort_retention.sql` | `agg_retention_cohorts` | Monthly cohorts became weekly; the D3 and D14 columns are new. |

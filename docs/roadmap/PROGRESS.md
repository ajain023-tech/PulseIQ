# PulseIQ — progress log

## Phase 1 — Foundation (2026-11-14) ✅

**Branch:** `phase-1-foundation`, merged into `main` after the acceptance checks passed.

### What was built
- Installable package `pulseiq` (src layout), the `pulseiq` CLI (Typer), Makefile,
  ruff config, `.env.example`, and GitHub Actions CI (`.github/workflows/ci.yml`).
- Seeded event generator (`src/pulseiq/generator/`). It produces 7 raw tables plus
  `ground_truth.json`, plants three experiments (including an SRM bug) and the true
  retention drivers, and injects realistic dirt (duplicates, clock skew, null
  platform).
- dbt project on DuckDB (`warehouse/`) with 7 staging, 6 intermediate and 9 mart
  models, and 70 data tests (generic + 5 singular + a `unique_combination` macro).
- `pulseiq compare-legacy` → `artifacts/reports/legacy_vs_generated.md`.
- Tests: `test_generator.py` (determinism of frames *and* parquet bytes, schema,
  orphans, dirt rates, allocation/SRM, ground-truth contents), `test_warehouse.py`,
  and `test_calibration.py` (slow, full size).
- Docs: `EVENT_SCHEMA.md`, `DATA_GENERATION.md`, `WAREHOUSE.md`, `SQL_MIGRATION.md`,
  `legacy/README.md`.
- Repo cleanup: the v1 code was moved to `legacy/` with `git mv`, and the legacy CSV
  to `data/legacy/`. The foreign Tableau link was removed (`Tableau: TBD`). Garbled
  `?` characters were fixed in `legacy/README_v1.md` and 4 legacy docs. Empty v1
  files are listed in `legacy/README.md` and were not carried forward.

### Decisions and deviations
- **Python 3.11 was installed with `uv`.** The machine only had the system Python
  3.9.6 and no Homebrew. `uv` was installed with `pip --user` and used to install
  CPython 3.11 and create `.venv`; pip was bootstrapped into the venv with
  `ensurepip` so that `make install` works.
- Pins reflect the versions that actually installed: duckdb 2.0.0,
  dbt-core 1.12.7, dbt-duckdb 1.11.1, pandas 3.1.1, numpy 2.4.6. **dbt-duckdb worked,
  so no fallback runner was needed.**
- **dbt runs in a subprocess.** In-process dbt keeps a DuckDB handle open, and DuckDB
  then refuses a second read-only connection in the same process.
- **Retention definition:** day N is the 24 h block after `signup_ts` and
  `dN_retained` means a session started in that block (exact-day, as in v1).
  Eligibility requires `signup_ts + (N+1) d ≤ data_end`.
- **Simulation design:** the planted effects act on per-user *probabilities*
  (onboarding additive +3 pp; paid scaled by a solved factor; streak hazard
  multiplier found by root-finding). The ground truth is therefore the *exact* average
  treatment effect over the population, not a nominal parameter.
- **SRM bug:** "~6 % of treatment users on Android" is implemented as 6 % of *all*
  treatment users dropped, all of them Android (≈13 % of Android treatment). A 6 %
  loss within Android alone (~270 rows) would not reach p < 0.001 at full size.
- **Experiment windows** are scaled to the dataset length (small = 60 days →
  windows ×0.5). In small mode the samples are too small for the SRM to reach
  p < 0.001 reliably; truth validation runs on the full size.
- **paywall_redesign population:** ≥ 14 days tenure, no earlier trial, and ≥ 1
  session in the 28 days before the start. Trial probability is linear in
  `pre_sessions_14d` (R² ≈ 0.57 with the outcome), so CUPED should narrow the CI by
  ~30 %.
- The signup session carries the onboarding prefix events, so it can exceed 15
  events. Every other session has 2–15 (plus up to 3 inserted paywall/trial events).
- `int_user_day_n_activity` and `int_data_window` were added beyond the spec list:
  exact-day retention needs a user × day-N grain, and `data_end` has to come from
  the data, not the ground truth.
- Nothing was added to the parent repo. **To do for Anushka:** add
  `ProductAnalytics/` to `~/Desktop/.gitignore` (the Desktop folder is itself a git
  repo pointing at another project).

### Acceptance checks (output)
```text
$ make install
Successfully installed pulseiq-0.2.0   (after bootstrapping pip; first attempt failed: "No module named pip")
$ make lint
All checks passed!
ruff format --check src tests
18 files already formatted
$ pulseiq generate --small && pulseiq build
Generated size=small seed=42 in 0.4s -> /Users/anushkajain/Desktop/ProductAnalytics/data/raw
dbt build: 22 models, 70 tests in 2.2s
All models built and all tests passed.
$ time (pulseiq generate && pulseiq build)
Generated size=full seed=42 in 10.4s -> /Users/anushkajain/Desktop/ProductAnalytics/data/raw
dbt build: 22 models, 70 tests in 3.9s
All models built and all tests passed.
real 14.72
user 29.26
sys 2.16
$ pulseiq profile (headline)
{
 "row_counts": {
  "dim_users": 60000,
  "fct_events": 7068334,
  "fct_funnel_user": 60000,
  "agg_funnel_daily": 120,
  "agg_funnel_by_segment": 14,
  "agg_retention_cohorts": 90,
  "fct_revenue_daily": 120,
  "agg_kpis_daily": 120,
  "fct_experiment_exposures": 53292
 },
 "headline": {
  "users": 60000,
  "onboarding_rate": 0.5517,
  "trial_rate_ordered": 0.19956666666666667,
  "paid_rate_ordered": 0.11526666666666667,
  "d1_retention": 0.40436889913232105,
  "d3_retention": 0.2757641470466749,
  "d7_retention": 0.20474533939880474,
  "d14_retention": 0.1760224386915817,
  "d30_retention": 0.1436522896108216,
  "gross_revenue_usd": 150876.98999999987,
  "refunds_usd": 4261.759999999998,
  "net_revenue_usd": 146615.22999999992,
  "last_day_dau": 8481,
  "last_day_mau": 24546,
  "last_day_stickiness": 0.3455145441212418,
  "last_day": "2025-05-05"
 }
}
$ pulseiq compare-legacy
                                               metric  legacy_v1  generated_v2  target  diff_pp_vs_legacy
              Onboarding completed (share of signups)   0.548857      0.552800    0.55           0.394291
Trial started within 14 d (share of eligible signups)   0.163846      0.161794    0.16          -0.205154
         Paid within 30 d (share of eligible signups)   0.097976      0.099220    0.10           0.124360
              D1 exact-day retention (eligible users)   0.407346      0.404369    0.40          -0.297711
              D7 exact-day retention (eligible users)   0.183563      0.204745    0.20           2.118226
             D30 exact-day retention (eligible users)   0.147618      0.143652    0.15          -0.396593
Report: /Users/anushkajain/Desktop/ProductAnalytics/artifacts/reports/legacy_vs_generated.md
$ pytest -q
...............                                                          [100%]
15 passed in 14.43s
$ ground truth keys
dict_keys(['onboarding_flow_v2', 'paywall_redesign', 'streak_reminder'])
```

### Known issues
- CI has not run on GitHub yet: nothing has been pushed, and that waits for approval.

### Hand-off to Phase 2
- **`fct_experiment_exposures` columns:** experiment_id, user_id, variant, assigned_at,
  test_end, signup_ts, assigned_at_signup, platform, acquisition_channel, country_tier,
  device_tier, pre_sessions_14d, pre_active_days_14d, onboarding_completed,
  trial_eligible, trial_started_14d, paid_eligible, paid_30d, d1_eligible, d1_retained,
  d7_eligible, d7_retained, d30_eligible, d30_retained, trial_started_in_test,
  paid_in_test, refund_in_test, sessions_in_test, net_revenue_in_test
  (descriptions in `warehouse/models/marts/_marts.yml` and `docs/WAREHOUSE.md`).
- **`int_user_first_72h` columns:** user_id, signup_ts, sessions_72h, active_days_72h,
  total_events_72h, distinct_features_72h, workout_log_72h, plan_view_72h,
  progress_chart_72h, social_share_72h, reminder_set_72h, onboarding_steps_completed,
  onboarding_completed_72h, paywall_views_72h, trial_started_72h, push_opens_72h,
  minutes_to_first_workout.
- **Ground truth:** `data/raw/ground_truth.json` → `experiments.<id>.true_effects_abs`
  (dict metric → absolute effect), `experiments.paywall_redesign.true_effects_rel`,
  `experiments.streak_reminder.srm_bug`, `true_retention_drivers`, `dirt`.
- **Full-size build:** ~15 s end to end (generate 10.4 s + dbt 3.9 s). 60,000 users,
  7.1 M raw events, 1.0 M sessions, 53,292 exposures.
- **Pre-period metric:** `pre_sessions_14d` counts sessions with start in
  `[assigned_at − 14 d, assigned_at)`. It is always 0 for new-user experiments
  (`assigned_at_signup = true`), so CUPED must be skipped there.
- The paywall test's trial metric is `trial_started_in_test` (window
  `[assigned_at, test_end)`). Its ground truth is relative +8 % (absolute in
  `true_effects_abs`).

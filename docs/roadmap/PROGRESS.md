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

## Phase 2 — Experimentation engine & retention ML (2026-11-14) ✅

**Branch:** `phase-2-exp-ml`, merged into `main` after the acceptance checks passed.

### What was built
- `src/pulseiq/experiments/`:
  - SRM overall and per segment, plus root-cause localisation;
  - two-proportion z, Newcombe and delta-method relative CIs; Welch t and bootstrap;
  - CUPED; Holm and BH corrections;
  - mSPRT sequential test with confidence sequences and the A/A peeking simulation;
  - Beta-Binomial Bayesian readout; power, MDE and days-to-run;
  - segment HTE; the decision framework; and a pydantic `ExperimentReport` with
    markdown and charts.
- `src/pulseiq/ml/`:
  - leakage-free 72 h features and a time split;
  - majority and active-days baselines, class-balanced LR and HGB with small
    validation grids, and isotonic calibration;
  - PR/ROC, calibration, confusion, gain and threshold table;
  - permutation importance and SHAP;
  - Kaplan–Meier, log-rank and Cox (lifelines);
  - `predict_user` and `score_recent`.
- `src/pulseiq/validation.py`: the only non-test code that reads `ground_truth.json`.
  It writes `experiment_validation.md` and `ml_validation.md`.
- CLI: `pulseiq analyze [--all]`, `train`, `survival`, `validate`. Makefile:
  `analyze`, `train`, `survival`, `validate`, `pipeline`; `all` now runs the whole
  pipeline.
- Tests:
  - `test_experiments_stats.py`: 19 hand-computable unit tests, including Newcombe's
    published example and a statsmodels power cross-check;
  - `test_experiments_truth.py` (slow): truth coverage, SRM, CUPED, decisions, A/A;
  - `test_no_leakage.py`, `test_ml.py` (the slow part checks driver recovery).
- Docs: `EXPERIMENTATION.md`, `ML_RETENTION.md`, `MODEL_CARD.md`.

### Decisions and deviations
- **SRM localisation:** the low country tier was also significant only because it
  is 43 % of traffic. A segment counts as a "likely cause" only if excluding it
  removes the SRM *and* leaves the rest close to 50/50.
- **Guardrails use non-inferiority tolerances** (pre-registered in `metrics.py`).
  "Significantly worse" leads to DON'T SHIP; "CI still allows harm beyond tolerance"
  leads to KEEP RUNNING. For `onboarding_flow_v2` that produces KEEP RUNNING, with
  about 10 days needed to bound paid conversion within 1 pp.
- **CUPED** uses the pre-registered covariate `pre_sessions_14d` and is skipped
  automatically for experiments randomised at signup.
- **Sequential looks** are retrospective daily looks by assignment date.
  `paywall_redesign` assigned everyone on one day, so it reports "not applicable".
- **ML target** is exact-day D30, consistent with Phase 1. HGB was selected on
  validation and ties LR on test (0.484 vs 0.486); this is reported, not hidden.
- **Calibration:** isotonic, clipped to [0.001, 0.999]. Ranking metrics use the
  uncalibrated scores to avoid isotonic ties. The campaign band is the bottom 20 %
  of the validation score.
- `lifelines` and `shap` both installed, so there was no fallback.

### Acceptance checks (output)
```text
$ make lint && pytest -q
ruff format --check src tests
46 files already formatted
45 passed in 43.82s
$ pulseiq generate && pulseiq build
Generated size=full seed=42 in 10.5s -> /Users/anushkajain/Desktop/ProductAnalytics/data/raw
dbt build: 22 models, 70 tests in 4.5s
All models built and all tests passed.
$ pulseiq analyze --all
onboarding_flow_v2     KEEP RUNNING  -> /Users/anushkajain/Desktop/ProductAnalytics/artifacts/experiments/onboarding_flow_v2
streak_reminder        INVESTIGATE   -> /Users/anushkajain/Desktop/ProductAnalytics/artifacts/experiments/streak_reminder
paywall_redesign       SHIP          -> /Users/anushkajain/Desktop/ProductAnalytics/artifacts/experiments/paywall_redesign
Peeking A/A sim: fixed 5.2%, naive peeking 28.7%, sequential 1.3%
$ pulseiq train && pulseiq survival
Best model: hist_gradient_boosting {'learning_rate': 0.05, 'max_depth': 3, 'max_leaf_nodes': 15, 'l2_regularization': 1.0}
  majority_baseline        PR-AUC 0.153  ROC-AUC 0.500  recall 0.000  F1 0.000  accuracy 0.847
  active_days_heuristic    PR-AUC 0.303  ROC-AUC 0.766  recall 0.949  F1 0.375  accuracy 0.518
  logistic_regression      PR-AUC 0.486  ROC-AUC 0.852  recall 0.707  F1 0.512  accuracy 0.794
  hist_gradient_boosting   PR-AUC 0.484  ROC-AUC 0.854  recall 0.704  F1 0.521  accuracy 0.802
Artifacts: /Users/anushkajain/Desktop/ProductAnalytics/artifacts/ml
52,766 users, 42,089 churn events
  KM by acquisition_channel  log-rank p = 0
  KM by platform             log-rank p = 2e-119
  KM by onboarding_variant   log-rank p = 0.158
  Cox HR reminder_set_any           0.494 [0.483, 0.506]
  Cox HR workout_log_72h            0.885 [0.880, 0.889]
  Cox HR active_days_72h            0.448 [0.438, 0.457]
  Cox HR sessions_72h               1.012 [0.999, 1.024]
  Cox HR onboarding_completed_72h   0.755 [0.741, 0.770]
$ pulseiq validate
artifacts/ml:
$ cat artifacts/reports/experiment_validation.md (summary)
**12 / 12 planted effects lie inside the engine's 95 % CI.**
SRM flagged only on `streak_reminder`: **yes**; localised to Android: **yes**.
Covariate `pre_sessions_14d`: variance reduction 56.7%, CI width reduction **34.1%** (target ≥ 20 %).
| Naive peeking (stop at first p < 0.05) | 28.7% |
| mSPRT always-valid sequential test | 1.3% |
Best model `hist_gradient_boosting`: test PR-AUC **0.484** vs majority baseline 0.153 and active-days heuristic 0.303; recall 0.704 at the validation-chosen threshold.
| Rank | Feature (permutation importance on test) | Drop in PR-AUC | Planted driver? |
All three explicit planted drivers are in the top 5: **yes**.
```

### Known issues
- Kaplan–Meier median survival is 2–4 days for every group, because most users
  churn in week 1. The differences show up in the tails (S(30d)), which is what the
  docs report.
- sklearn emits harmless runtime warnings from scaling constant one-hot columns in
  tiny test splits (small dataset only).

### Hand-off to Phase 3
- **Experiments:**
  - `pulseiq.experiments.analyze_experiment(con, id, sequential, bayesian, cuped) -> ExperimentReport`;
  - `save_report(report, dir)` and `load_report(path)`;
  - cached reports live at `artifacts/experiments/<id>/report.json`;
  - `pulseiq.experiments.data.list_experiments(con)`.
- **Schema:** `ExperimentReport` fields are experiment_id, name, hypothesis,
  start/end_date, data_end, primary/guardrail/secondary metrics, n_control,
  n_treatment, srm (SRMResult with segments, flagged_segments, likely_causes),
  metrics (list[MetricResult] with raw and decision estimates, cuped, bayesian,
  p_adjusted), cuped_status, power (PowerSummary), sequential (dict trace), segments,
  decision, reasons, charts, generated_at.
- **Prediction:**
  - `pulseiq.ml.predict.predict_user(con, user_id, ml_dir)` returns p_retained_d30,
    risk_band, top_contributions, or None for an unknown user;
  - `score_recent(con, ml_dir, days=14)` returns a DataFrame sorted by risk;
  - the model is loaded once per process (`lru_cache`), so latency is a few ms per
    user on the small warehouse.
- **Artifacts:**
  - `artifacts/experiments/<id>/{forest,sequential,posterior}.png`;
  - `artifacts/experiments/peeking_simulation.{png,json}`;
  - `artifacts/ml/{pr_curve,roc_curve,calibration,confusion_matrix,gain_chart,permutation_importance,shap_summary,km_acquisition_channel,km_platform,km_onboarding_variant}.png`;
  - `artifacts/ml/{model_meta,metrics,threshold_table,survival}.json`;
  - `artifacts/reports/{experiment_validation,ml_validation,legacy_vs_generated}.md`.

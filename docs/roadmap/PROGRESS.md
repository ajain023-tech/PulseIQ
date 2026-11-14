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
Generated size=small seed=42 in 0.4s -> ./data/raw
dbt build: 22 models, 70 tests in 2.2s
All models built and all tests passed.
$ time (pulseiq generate && pulseiq build)
Generated size=full seed=42 in 10.4s -> ./data/raw
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
Report: ./artifacts/reports/legacy_vs_generated.md
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
Generated size=full seed=42 in 10.5s -> ./data/raw
dbt build: 22 models, 70 tests in 4.5s
All models built and all tests passed.
$ pulseiq analyze --all
onboarding_flow_v2     KEEP RUNNING  -> ./artifacts/experiments/onboarding_flow_v2
streak_reminder        INVESTIGATE   -> ./artifacts/experiments/streak_reminder
paywall_redesign       SHIP          -> ./artifacts/experiments/paywall_redesign
Peeking A/A sim: fixed 5.2%, naive peeking 28.7%, sequential 1.3%
$ pulseiq train && pulseiq survival
Best model: hist_gradient_boosting {'learning_rate': 0.05, 'max_depth': 3, 'max_leaf_nodes': 15, 'l2_regularization': 1.0}
  majority_baseline        PR-AUC 0.153  ROC-AUC 0.500  recall 0.000  F1 0.000  accuracy 0.847
  active_days_heuristic    PR-AUC 0.303  ROC-AUC 0.766  recall 0.949  F1 0.375  accuracy 0.518
  logistic_regression      PR-AUC 0.486  ROC-AUC 0.852  recall 0.707  F1 0.512  accuracy 0.794
  hist_gradient_boosting   PR-AUC 0.484  ROC-AUC 0.854  recall 0.704  F1 0.521  accuracy 0.802
Artifacts: ./artifacts/ml
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

## Phase 3 — Product layer: API, dashboard, AI analyst (2026-11-14) ✅

**Branch:** `phase-3-product-ai`, merged into `main` after the acceptance checks passed.

### What was built
- **Service layer** (`src/pulseiq/services/`): `kpis`, `funnel`, `retention`, `revenue`,
  `experiments`, `predictions`, `meta`, `filters` and `db`.
  - Every function takes explicit `Filters` (date range, platform, channel, country tier).
  - Queries run on a read-only DuckDB connection with a per-call cursor.
  - Results go through a TTL cache.
  - There is no SQL in UI code.
- **FastAPI** (`src/pulseiq/api/app.py`) under `/api/v1`:
  - endpoints: health, kpis, funnel, retention/cohorts, revenue/daily, experiments,
    experiments/{id}, POST experiments/{id}/analyze, POST power,
    predictions/users/{id}, predictions/at-risk, POST ask;
  - pydantic models everywhere, 422 on invalid filters and inputs, 404 for unknown
    experiments and users, timing middleware (`X-Response-Time-ms`), CORS for
    localhost;
  - run with `pulseiq serve`.
- **Dashboard** (`apps/dashboard/`): Home plus 8 pages (Funnel, Retention, Revenue,
  Experiments, Experiment Designer, Retention Model, AI Analyst, Data & Methods).
  - Shared sidebar filters persist in `st.session_state`.
  - One Okabe-Ito plotly theme; every chart has a title and a one-line takeaway.
  - Empty states when filters match nobody.
  - Cold-start bootstrap: a small warehouse plus artifacts are built if missing.
- **AI analyst** (`src/pulseiq/ai/`):
  - catalog built from dbt `schema.yml`; prompts with few-shot examples;
  - provider-agnostic `llm.py` (gemini default | anthropic via the official SDK |
    openai | mock | offline);
  - sqlglot `guard.py`; `agent.py` with a single retry; tools that route experiment
    questions to the validated engine;
  - offline intent engine; 25-question eval (`pulseiq ai-eval`); `pulseiq ask`.
- **Tests:**
  - `test_api.py`: every endpoint;
  - `test_dashboard.py`: AppTest renders all 9 pages, 4 of them under narrow filters,
    plus an AI page interaction;
  - `test_ai_guard.py`: 22 malicious statements, LIMIT, timeout, read-only
    connection, retry, malformed output, offline when no key, eval.
- `scripts/bench_api.py` (p95 latency); `scripts/screenshots.py` (headless Chromium
  visits every page, fails on any Streamlit exception, saves `docs/images/*.png`).
- Docs: `docs/AI_ANALYST.md`.

### Decisions and deviations
- **No paid LLM key was used.** The roadmap says to ask first, so everything is built
  and evaluated with the `mock`/`offline` providers. The `anthropic` client is
  constructed and its parameters (`betas`, `fallbacks`, `output_config`) were checked
  against SDK 2.8.0, but **no request was sent**.
- **Default Claude model** is `claude-opus-5-5`, with server-side refusal fallbacks
  (`fallbacks="default"`) and low effort for latency. The Gemini default stays as the
  roadmap specifies.
- **Paid conversion KPI:** cohort paid-within-30-days is undefined for the most recent
  28 days. The Home KPI is therefore "Trial → paid": the conversion of trials that
  ended in the period.
- **Port 8000** is already used on this machine by another local project (PreBuyIq's
  uvicorn, running before this session; it was left untouched). `pulseiq serve
  --port` is configurable; the checks used :8010. Docker Compose should map a
  configurable host port.
- **Playwright + headless Chromium** were installed in `.venv` for the real-browser
  page check. The v1 audit never did one.
- **Bugs found by the new tests and fixed:**
  - the engine crashed on metrics with zero eligible users (small data); they are now
    skipped and listed in `skipped_metrics`;
  - the funnel crashed when filters matched nobody (NULL sums);
  - the AI parser read "device tier" as country tier;
  - the PR-curve chart drew sklearn's artificial (recall 0, precision 1) point, so the
    constant baseline *looked* better than the model;
  - the SRM bar chart axis hid the deviation.
- **v1 dashboard features superseded:**
  - Executive Overview → Home; User Funnel → Funnel;
  - User & Segment Analysis → Funnel segments + Retention curves;
  - Retention & Cohorts → Retention; A/B Experiment → Experiments;
  - ML Retention Prediction → Retention Model;
  - Documented Monetization → Revenue (now reproducible);
  - Data & Methodology → Data & Methods.
- **Intentionally dropped:**
  - "SQL Analysis": its BigQuery files can't run. The dbt lineage graph plus the AI
    analyst replace it.
  - "Project Workflow": replaced by the roadmap docs.

### Acceptance checks (output)
```text
$ make lint && pytest -q
87 files already formatted
98 passed in 49.89s
(first attempt on :8000 hit another local app - see decisions; re-run on :8010 below)
API startup: 1.1s
$ curl -s localhost:8010/api/v1/health
{"status":"ok","version":"0.2.0","warehouse":"./data/warehouse/pulseiq.duckdb","warehouse_built_at":"2026-11-14T17:02:35+00:00","model_version":"hist_gradient_boosting (trained 2026-11-14T17:21:22+00:00, sha deca15b)","git_sha":"deca15b"}
$ curl -s localhost:8010/api/v1/experiments/paywall_redesign | head -c 400
{"experiment_id":"paywall_redesign","name":"Paywall redesign (re-engagement campaign)","hypothesis":"A redesigned paywall raises trial starts among existing free users.","start_date":"2025-03-27","end_date":"2025-04-26","data_end":"2025-05-06 00:00:00","primary_metric":"trial_started_in_test","guardrail_metrics":["refund_in_test"],"secondary_metrics":["paid_in_test","sessions_in_test","net_revenue
API RSS MB (after requests): 313
Swagger: 200 /docs
Dashboard RSS MB: 90
$ python scripts/bench_api.py
endpoint                                           p50 ms   p95 ms
GET /api/v1/health                                   11.6     12.6
GET /api/v1/kpis                                      1.2      1.4
GET /api/v1/kpis?platform=ios&channel=referral        1.2      1.3
GET /api/v1/funnel?by=channel                         1.2      1.3
GET /api/v1/retention/cohorts                         1.8      2.0
GET /api/v1/revenue/daily                             1.7      1.9
GET /api/v1/experiments                               1.2      1.3
GET /api/v1/experiments/paywall_redesign              1.1      1.1
GET /api/v1/predictions/at-risk?limit=50              2.4      2.8
POST /api/v1/power                                    1.7      1.8
worst p95: 12.6 ms -> PASS (target < 300 ms)
$ streamlit run apps/dashboard/Home.py  (every page checked in headless Chromium)
home                   PASS       title='PulseIQ — Product Analytics & Experimentation'
funnel                 PASS       title='Funnel'
retention              PASS       title='Retention'
revenue                PASS       title='Revenue'
experiments            PASS       title='Experiments'
experiment_designer    PASS       title='Experiment designer'
retention_model        PASS       title='D30 retention model'
ai_analyst             PASS       title='AI Product Analyst'
data_methods           PASS       title='Data & methods'
$ pulseiq ai-eval --provider mock
{
  "provider": "mock",
  "n_questions": 25,
  "sql_valid_pct": 1.0,
  "execution_success_pct": 1.0,
  "answer_correct_pct": 1.0,
  "refusal_correct_pct": 1.0,
  "false_refusals": 0,
  "overall_correct_pct": 1.0,
  "median_latency_ms": 1.4372500008903444
}

```

### Hand-off to Phase 4
- **Run:**
  - `pulseiq serve --host 0.0.0.0 --port 8000`;
  - `streamlit run apps/dashboard/Home.py --server.port 8501`.
- **Environment variables:** `PULSEIQ_SEED`, `PULSEIQ_SIZE` (`small` for cloud),
  `PULSEIQ_DATA_DIR`, `PULSEIQ_ARTIFACTS_DIR`, `PULSEIQ_WAREHOUSE`,
  `PULSEIQ_LLM_PROVIDER`, `PULSEIQ_LLM_MODEL`, plus one of `GEMINI_API_KEY` /
  `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`.
- **Startup:**
  - API ~1 s; ~310 MB RSS after the first requests (full warehouse plus model).
  - Dashboard ~90 MB idle.
  - Cold start in small mode runs generate + build + analyse + train inside the
    dashboard (~30 s).
- **AI eval (mock):** 25/25; SQL valid 100 %, execution 100 %, refusals 100 %. Real
  provider: not run, no key.
- **Screenshots:** `docs/images/{home,funnel,retention,revenue,experiments,experiment_designer,retention_model,ai_analyst,data_methods}.png`.
- **Rough edges:**
  - Offline mode knows about 20 question shapes.
  - Survival charts ignore the sidebar filters (whole window; labelled as such).
  - Screenshots are viewport-height, because Streamlit scrolls inside a container.

## Phase 4 — Ship (2026-11-14) ✅ (except the steps that need your accounts)

**Branch:** `phase-4-ship`, merged into local `main`. **Not pushed and not tagged**; both are
waiting for your approval.

### What was built
- **Docker:**
  - `Dockerfile`: multi-stage, `python:3.11-slim`, non-root user, healthcheck,
    `PULSEIQ_SIZE=small`;
  - `docker-compose.yml`: a one-shot `init` service, then `api` and `dashboard`, sharing
    volumes, passing `.env` through, with configurable host ports;
  - `scripts/bootstrap.sh` (idempotent), `.dockerignore`, Makefile `docker-*` targets.
- **Deploy configs:**
  - Streamlit Cloud: `requirements.txt` exported from `pyproject.toml` with `-e .`;
    `.streamlit/config.toml` moved to the repo root; `secrets.toml.example`; the dashboard
    bootstraps itself on a cold start.
  - Render: `render.yaml` for the API.
  - `docs/DEPLOYMENT.md` with click-by-click steps.
- **README** rewritten for recruiters. The results block is generated by
  `scripts/render_results.py` from `artifacts/`; `scripts/check_numbers.py` verifies the
  README, the key numbers in 4 docs, and active-tree hygiene.
- **Demo kit:** `docs/demo/DEMO_SCRIPT.md` (3-minute and 60-second versions, plus a fallback
  plan) and `docs/demo/HACKATHON_PITCH.md`. Screenshots of all 9 pages are in `docs/images/`.
- **Career kit:** `docs/career/RESUME_BULLETS.md` (3 versions, every number cited to an artifact
  file), `INTERVIEW_PREP.md` (all viva questions plus 10 follow-ups) and `LEARNING_LOG.md`.
- `docs/FINAL_AUDIT.md`, `CHANGELOG.md`, `LICENSE` (MIT), `CONTRIBUTING.md`.

### Decisions and deviations
- **Docker is not installed** on this machine, so the image was never built. Its entrypoint was
  verified from a clean clone.
- **Hosted demo:** full-size generation peaks at about 4.3 GB RAM and the dbt build at about
  2.7 GB (measured), so the cloud runs small mode. Its experiments are underpowered, so the
  dashboard shows a banner and points to the full-size results.
- **Shell safety:** the Docker apt-cache cleanup uses `apt-get clean` instead of `rm -rf`
  (a shell safety check blocked commands containing that line). The image is slightly larger.
- **Paths:** absolute machine paths were removed from this log (repo-relative now).
- **Author links:** only the GitHub account from the repo URL appears. LinkedIn and Tableau stay
  "TBD" until you provide them.

### Clean-clone acceptance run (fresh `git clone` + fresh venv)
```text
$ make install
real 106.42
user 16.19
sys 6.47
$ make all
Generated size=full seed=42 in 11.5s -> <tmp>/final-clone/data/raw
dbt build: 22 models, 70 tests in 5.1s
All models built and all tests passed.
Peeking A/A sim: fixed 5.2%, naive peeking 28.7%, sequential 1.3%
Best model: hist_gradient_boosting {'learning_rate': 0.05, 'max_depth': 3, 'max_leaf_nodes': 15, 'l2_regularization': 1.0}
Peeking A/A sim: fixed 5.2%, naive peeking 28.7%, sequential 1.3%
98 passed, 39 warnings in 55.38s
real 114.50
$ pulseiq ai-eval --provider mock
  "overall_correct_pct": 1.0,
$ python scripts/render_results.py --check
README results match artifacts
$ python scripts/check_numbers.py
OK: checked README results, 4 docs and 151 files
$ python scripts/export_requirements.py --check
requirements.txt is up to date
```

### Waiting on you
1. **Approve `git push`** of `main` (and the phase branches) to
   `https://github.com/ajain023-tech/ProductAnalytics.git`, then the **`v1.0.0` tag**.
2. **Deploy** the dashboard on Streamlit Community Cloud (`docs/DEPLOYMENT.md`, about 5 minutes),
   then put the URL in the README badge.
3. **Optional:** choose an LLM provider and add a key to run the real-LLM eval and record the
   score in `docs/AI_ANALYST.md`.
4. **Your links:** LinkedIn and Tableau URLs (or remove those placeholders).
5. **Optional:** install Docker Desktop and run `docker compose up --build` to close audit item 18.
6. Add `ProductAnalytics/` to `~/Desktop/.gitignore` (your Desktop is itself a git repo for
   another project).

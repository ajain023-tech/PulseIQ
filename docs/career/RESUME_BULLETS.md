# Resume & profile kit — PulseIQ

Every number comes from a generated artifact. The source file is cited in a comment next to each
bullet. `scripts/check_numbers.py` checks the key ones against `artifacts/`. Re-run `make all`
before changing any number.

## Data Analyst version
- Built a product analytics platform on a 60k-user / 7M-event dataset with a dbt + DuckDB
  warehouse (22 models, 70 data tests). It produces funnel, cohort retention, revenue/MRR and
  KPI marts behind a 9-page Streamlit dashboard and a REST API.
  <!-- docs/roadmap/PROGRESS.md (Phase 1 acceptance: profile output, dbt build output) -->
- Designed eligibility-aware D1/D7/D30 cohort retention and ordered-funnel metrics. They
  located the largest drop-off (onboarded → trial) automatically, and the data-quality rules
  (dedupe, clock skew) are enforced by tests.
  <!-- artifacts via dashboard Funnel page; warehouse/tests/*.sql -->
- Turned 3 A/B tests into SHIP / KEEP RUNNING / INVESTIGATE decisions using guardrail metrics.
  The engine caught a sample-ratio-mismatch bug and localised it to Android users.
  <!-- artifacts/reports/experiment_validation.md -->

## Data Scientist version
- Built an A/B testing engine in Python (SRM, CUPED, Holm/BH, mSPRT sequential tests,
  Beta-Binomial). It recovered 12/12 planted effects within 95 % CIs and cut CI width by 34%
  with CUPED.
  <!-- artifacts/reports/experiment_validation.json: n_covered/n_effects, cuped_ci_width_reduction_paywall -->
- Showed with 2,000 simulated A/A tests that naive daily peeking inflates false positives to
  28.7% vs 1.3% with an always-valid mSPRT.
  <!-- artifacts/experiments/peeking_simulation.json -->
- Replaced a retention model with 0 recall (85 % accuracy from predicting the majority class)
  with a leakage-tested, calibrated gradient-boosting model. Test PR-AUC is 0.484 vs a
  0.153 baseline, and the model recovers all 3 planted retention drivers.
  <!-- artifacts/ml/metrics.json, artifacts/reports/ml_validation.json -->
- Quantified time-to-churn with Kaplan–Meier and Cox models: setting a reminder in the first
  72 h roughly halves the churn hazard (HR 0.49).
  <!-- artifacts/ml/survival.json -->

## Analytics / Data Engineer version
- Engineered a seeded, byte-for-byte reproducible event simulator (7M events in ~10 s) with
  planted ground truth and injected data-quality faults. A DuckDB + dbt warehouse with
  staging, intermediate and mart layers cleans them, and 70 data tests guard it.
  <!-- docs/DATA_GENERATION.md, tests/test_generator.py, PROGRESS.md Phase 1 -->
- Shipped a FastAPI service (12 endpoints, p95 < 15 ms cached) and a Streamlit app on a shared
  service layer. Both are containerised with Docker Compose, and GitHub Actions CI rebuilds
  the warehouse and runs about 100 tests.
  <!-- scripts/bench_api.py output in PROGRESS.md Phase 3 -->
- Built a guarded text-to-SQL AI analyst: sqlglot allow-list, read-only DuckDB, timeout,
  single retry and offline fallback. It blocks 22 attack patterns in tests and scores 25/25
  on a reference-SQL eval in mock mode.
  <!-- tests/test_ai_guard.py, artifacts/reports/ai_eval.json -->

## LinkedIn project description (2 lines)
PulseIQ is an open-source product analytics & experimentation platform: a dbt/DuckDB event
pipeline, an A/B engine validated against planted ground truth (SRM, CUPED, sequential tests),
leakage-free retention ML and a guarded AI analyst, behind a FastAPI service and a Streamlit
dashboard.

## GitHub repo description (1 line)
Product analytics & experimentation platform: dbt + DuckDB pipeline, A/B engine validated against
planted ground truth, retention ML and a guarded AI analyst.

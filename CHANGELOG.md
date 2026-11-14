# Changelog

## v1.0.0 — PulseIQ (2026-11-14)
The project rebuilt as a reproducible product analytics & experimentation platform.

- **Data:** a seeded event simulator with planted ground truth (3 experiments, an SRM bug,
  retention drivers, data-quality faults), calibrated to v1's headline rates.
- **Warehouse:** dbt on DuckDB (staging → intermediate → marts, 70 data tests). The v1 BigQuery
  SQL was ported or superseded (`docs/SQL_MIGRATION.md`).
- **Experiments:** SRM with root-cause localisation, Newcombe/Welch/bootstrap, CUPED, Holm/BH,
  mSPRT, Beta-Binomial, power/MDE, segments and a decision framework. Validated against the
  ground truth.
- **ML:** a leakage-tested 72 h feature set, time split, calibrated gradient boosting, PR-AUC
  evaluation, SHAP and permutation importance, Kaplan–Meier/Cox survival analysis and a model
  card.
- **Product:** a FastAPI service, a 9-page Streamlit dashboard and a guarded AI analyst with an
  eval set.
- **Ship:**
  - Docker and Compose, CI, deployment configs;
  - a README whose results are generated from artifacts, with number checks;
  - the demo, career and audit docs.

## v0.1 — Product Analytics & User Retention Analysis (legacy)
The original analysis of one 11,462-row experiment CSV: pandas scripts, notebooks, BigQuery SQL
and a single-file Streamlit app. Preserved in [`legacy/`](legacy/README.md).

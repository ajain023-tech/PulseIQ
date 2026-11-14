# Legacy — v1 analysis (kept for reference)

This folder is the original **Product Analytics & User Retention Analysis** (v1):
a user-level analysis of one 11,462-row experiment CSV plus BigQuery SQL whose
source tables were never in the repo. It is kept intact so the project history and
the original work remain visible. PulseIQ (v2) supersedes it.

Paths inside these scripts still point at the old layout (e.g. `data/ab_test_dataset.csv`,
now `data/legacy/ab_test_dataset.csv`), so they are not expected to run unmodified.

## How v1 maps to v2

| v1 (here) | v2 replacement |
|---|---|
| `python/data_cleaning.py` | dbt staging models (`warehouse/models/staging/`) + dbt tests |
| `python/eda_analysis.py`, `python/retention_analysis.py` | dbt marts (`agg_funnel_*`, `agg_retention_cohorts`) and the dashboard |
| `python/statistical_analysis.py`, `python/ab_test_summary.py`, `python/ab_test_analysis.ipynb` | `src/pulseiq/experiments/` (SRM, CUPED, sequential, Bayesian, validated against ground truth) |
| `python/feature_engineering.py`, `model_training.py`, `model_evaluation.py` | `src/pulseiq/ml/` (leakage-free 72 h features, time split, PR-AUC) |
| `sql/01…11_*.sql` (BigQuery) | dbt models on DuckDB — see `docs/SQL_MIGRATION.md` |
| `app.py` (single-file Streamlit, 2,400 lines) | `apps/dashboard/` (multipage) + `src/pulseiq/api/` |
| `outputs/`, `dashboard/dashboard.png` | regenerated artifacts under `artifacts/` |
| `README_v1.md`, `docs/` | `README.md`, `docs/` |
| `requirements_v1.txt` | `pyproject.toml` / `requirements.txt` |

## Known v1 issues (fixed or superseded in v2)

- The v1 retention models reached 85 % accuracy by predicting "nobody is retained"
  (recall 0) and used `d1_retained` / `paid_conversion` without timestamps.
- Headline numbers (34,000 signups, $142K revenue, …) came from BigQuery tables that
  are not in the repo, so they cannot be reproduced.
- The README linked a Tableau dashboard on another person's public profile; the link
  was removed (`Tableau: TBD`).
- Garbled `?` box-drawing characters in `README_v1.md` and several docs were repaired.

## Empty files (not carried forward)

These files were empty or header-only in v1 and have no v2 counterpart:

- `python/generate_sql_outputs.py` (0 bytes)
- `docs/PROJECT_MODIFICATION_PLAN.md`, `docs/SQL_VIVA_NOTES.md` (0 bytes)
- `outputs/sql/*.csv` (six 0-byte files)
- `outputs/dashboard/executive_kpis.csv` and other header-only templates in
  `outputs/dashboard/`, `outputs/funnel/`, `outputs/retention/`

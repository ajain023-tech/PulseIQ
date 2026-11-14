# Learning log

Each concept from the four phases, with a one-paragraph explanation and where it lives in the
code. Tick each one off once you can explain it without notes.

## Phase 1 — Data & warehouse
- [ ] **Event-based analytics:** products log immutable events ("what happened, when").
  User-level flags such as `onboarding_completed` are *derived* from events, so definitions can
  change without re-collecting data. → `src/pulseiq/generator/__init__.py`,
  `warehouse/models/marts/fct_funnel_user.sql`
- [ ] **Grain:** every table answers "one row per what?". For example, `agg_retention_cohorts`
  has one row per weekly cohort × day N. Mixing grains is the most common SQL bug.
  → `docs/WAREHOUSE.md`
- [ ] **Staging → intermediate → marts:** staging renames, types and cleans one source;
  intermediate holds reusable logic; marts are consumer-facing. Layering keeps logic in one
  place. → `warehouse/models/`
- [ ] **dbt:** `ref()` and `source()` build the DAG; materializations (we use table);
  generic and singular tests; schema docs. → `warehouse/`
- [ ] **DuckDB vs BigQuery:** in-process columnar OLAP on one file vs a serverless cloud
  warehouse. DuckDB is ideal for reproducible CI builds. → `src/pulseiq/warehouse/build.py`
- [ ] **Eligibility-aware retention:** a user who signed up 5 days ago can't be in the D7
  denominator. → `warehouse/models/marts/agg_retention_cohorts.sql`
- [ ] **Synthetic data with ground truth:** planting the truth lets you *prove* that methods work.
  → `docs/DATA_GENERATION.md`, `src/pulseiq/validation.py`
- [ ] **Determinism & seeds:** `SeedSequence.spawn` gives one independent `default_rng` per stage,
  so the global RNG never couples stages. Output is byte-identical. → `tests/test_generator.py`
- [ ] **CI:** every push installs, lints, generates the small data, builds the warehouse and runs
  the tests. → `.github/workflows/ci.yml`

## Phase 2 — Experimentation & ML
- [ ] **SRM:** observed arm sizes that differ from the design (chi-square) mean assignment or
  logging is broken, so no readout can be trusted. → `src/pulseiq/experiments/srm.py`
- [ ] **CUPED:** subtract what the pre-period predicts. The variance reduction is ρ²; the
  estimate stays unbiased. → `cuped.py`
- [ ] **The peeking problem:** repeated looks inflate false positives; mSPRT gives always-valid
  inference. → `sequential.py`, `artifacts/experiments/peeking_simulation.png`
- [ ] **Frequentist vs Bayesian:** a p-value is P(data at least this extreme | H0), *not*
  P(H0 | data). P(T > C) is a posterior probability. → `frequentist.py`, `bayesian.py`
- [ ] **Power & MDE:** n ∝ variance / effect². Halving the MDE roughly quadruples n. → `power.py`,
  the dashboard's Experiment Designer
- [ ] **Multiple comparisons:** Holm controls family-wise error for the confirmatory family; BH
  controls false-discovery rate for exploration. → `corrections.py`
- [ ] **Guardrail metrics:** a winning primary metric is not enough; harm beyond the tolerance
  blocks shipping. → `decision.py`
- [ ] **Class imbalance:** accuracy misleads; use PR-AUC. → `src/pulseiq/ml/evaluate.py`
- [ ] **Leakage:** a feature-time cutoff plus a time-based split. → `features.py`, `split.py`,
  `tests/test_no_leakage.py`
- [ ] **Calibration & thresholds:** class weights distort probabilities; isotonic calibration on
  validation fixes them, and the threshold comes from a business goal. → `train.py`,
  `evaluate.py`
- [ ] **Survival analysis:** censoring, Kaplan–Meier, log-rank, Cox hazard ratios. →
  `src/pulseiq/ml/survival.py`

## Phase 3 — Product & AI
- [ ] **Service-layer pattern:** the API and the UI share one logic layer. →
  `src/pulseiq/services/`
- [ ] **REST design:** resources, status codes (404/422), pydantic validation, OpenAPI. →
  `src/pulseiq/api/app.py`
- [ ] **Caching:** a TTL cache trades freshness for speed; p95 under 15 ms. →
  `services/db.py`, `scripts/bench_api.py`
- [ ] **Text-to-SQL:** a schema catalog plus few-shot examples, a JSON plan, and a validated
  engine for statistics. → `src/pulseiq/ai/`
- [ ] **LLM guardrails:** parsing, allow-lists, a read-only connection, timeouts,
  prompt-injection hygiene. → `ai/guard.py`
- [ ] **LLM evaluation:** a fixed question set scored numerically, not on vibes. → `ai/evals/`
- [ ] **Dashboard UX:** one takeaway per chart, empty states, immature cells left blank. →
  `apps/dashboard/`

## Phase 4 — Ship
- [ ] **Docker:** images vs containers, layers, multi-stage builds, volumes, compose,
  healthchecks. → `Dockerfile`, `docker-compose.yml`
- [ ] **12-factor config:** settings come from environment variables; `.env` is git-ignored. →
  `src/pulseiq/config.py`, `.env.example`
- [ ] **Deploying data apps:** cold starts, memory limits, why small mode exists (full
  generation peaks around 4.3 GB). → `docs/DEPLOYMENT.md`
- [ ] **Technical storytelling:** problem → approach → evidence → impact. →
  `docs/demo/DEMO_SCRIPT.md`
- [ ] **Reproducibility as credibility:** v1's numbers couldn't be reproduced; v2's are
  regenerated and checked by script. → `scripts/check_numbers.py`

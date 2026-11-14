# Phase 1 — Foundation: Package, Event Data, Warehouse, Tests (Days 1–2)

> **Prompt for Claude.** You are a senior analytics engineer joining a student's
> portfolio project. Your job in this phase is to give PulseIQ a professional
> foundation: a real Python package, a realistic *event-level* synthetic dataset with
> known ground truth, a DuckDB + dbt warehouse with tested models, a test suite, CI,
> and a cleaned-up repo. Everything later (experiments, ML, API, AI analyst,
> dashboard) reads from the warehouse you build here, so correctness and clear
> schemas matter more than speed. Read `docs/roadmap/README.md` first — its global
> rules apply.

---

## 1. Context — what exists today

- `data/ab_test_dataset.csv`: 11,462 users × 16 columns:
  `user_id, variant, assigned_at, signup_ts, data_end_date, onboarding_completed,
  trial_eligible, trial_started, paid_eligible, paid_conversion, d1_eligible,
  d1_retained, d7_eligible, d7_retained, d30_eligible, d30_retained`.
  Only binary flags; no events, no channel/platform/country/device, single
  `data_end_date` 2025-08-15. Observed rates: onboarding ≈ 54.9 %, trial ≈ 16.4 %,
  paid ≈ 9.8 %, D1 ≈ 40.7 %, D30 ≈ 14.8 %.
- `python/*.py` — 8 pipeline scripts (cleaning, EDA, stats, features, training,
  evaluation, retention, A/B summary). `python/generate_sql_outputs.py` is empty.
- `sql/01…11_*.sql` — BigQuery SQL whose source tables are **not** in the repo, so the
  README's headline numbers (34,000 signups, $142K revenue, etc.) are not reproducible.
- `app.py` — 2,400-line single-file Streamlit app with 10 pages.
- `notebooks/` — 4 notebooks; `docs/` — 17 write-ups (two are empty).
- Known defects: README Tableau link points to another person's profile
  (`nikita.sergeevich`); empty files (`python/generate_sql_outputs.py`,
  `docs/PROJECT_MODIFICATION_PLAN.md`, `docs/SQL_VIVA_NOTES.md`,
  `outputs/dashboard/executive_kpis.csv` header-only, `outputs/sql/*.csv` zero bytes);
  garbled `?` characters in the README tree and `docs/FINAL_PROJECT_AUDIT.md`.

## 2. Goals for this phase

1. Restructure into an installable package `pulseiq` (src layout) with a CLI.
2. Build a **seeded synthetic event generator** that produces realistic product
   events *and* writes the ground-truth parameters it used (so Phase 2 can prove the
   statistics are correct).
3. Build a **DuckDB warehouse with dbt** (`dbt-duckdb`): sources → staging →
   intermediate → marts, with dbt tests.
4. Port the useful logic of the old BigQuery SQL into dbt models (funnel, retention
   cohorts, monetization, KPIs, segmentation).
5. A pytest suite, `ruff`, a `Makefile`, and GitHub Actions CI that builds the
   `--small` dataset and runs all tests.
6. Fix every known defect listed above; move the old code to `legacy/` intact.

### Non-goals (do NOT do these in Phase 1)
- No experiment statistics beyond simple sanity rates (Phase 2).
- No ML model work (Phase 2). No API, no new dashboard, no LLM (Phase 3).
- No Docker or deployment (Phase 4).

## 3. Stop and ask (the only reasons to interrupt the user)
- A step would overwrite or discard the user's uncommitted changes.
- `dbt-duckdb` AND the fallback SQL runner both fail to work.
- You want to push to the remote (`git push`). Commit locally; ask before pushing.

---

## 4. Tasks

### Task 1.1 — Repo hygiene and restructure
1. Create branch `phase-1-foundation`.
2. `git mv` the old code into `legacy/`: `app.py`, `python/`, `sql/`, `notebooks/`,
   `outputs/`, `dashboard/`, and the old docs into `legacy/docs/` **except** keep
   `docs/` as the home for new docs. Add `legacy/README.md` explaining that this is the
   v1 analysis kept for reference and how it maps to the new modules.
3. Keep `data/ab_test_dataset.csv` as `data/legacy/ab_test_dataset.csv` (used in
   Task 1.4 for calibration).
4. Fix defects in what remains/gets rewritten: remove the foreign Tableau link
   (leave `Tableau: TBD` — the user will add her own); do not carry empty files
   forward (write a one-line note in `legacy/README.md` listing them); replace garbled
   `?` box-drawing characters with proper UTF-8 or plain ASCII trees.
5. Add `.gitignore` entries: `data/raw/`, `data/warehouse/`, `artifacts/`, `.env`,
   `*.duckdb`, `warehouse/target/`, `warehouse/logs/`, `__pycache__/`, `.venv/`.
6. Add to the parent Desktop repo nothing (out of scope); log in PROGRESS.md that the
   user should add `ProductAnalytics/` to `~/Desktop/.gitignore`.

### Task 1.2 — Package skeleton
Create:
```text
pyproject.toml          # name=pulseiq, python>=3.11, deps pinned with ~=
src/pulseiq/__init__.py # __version__ = "0.2.0"
src/pulseiq/config.py   # paths, seed, sizes via pydantic-settings or dataclass + env vars
src/pulseiq/cli.py      # Typer (fallback: argparse) commands below
src/pulseiq/generator/  # Task 1.3
src/pulseiq/warehouse/  # Task 1.5
tests/
Makefile
.env.example
```
Core dependencies: `pandas`, `numpy`, `pyarrow`, `duckdb`, `dbt-core`, `dbt-duckdb`,
`typer`, `pydantic`, `scipy`, `pytest`, `ruff`. (Later phases add more.)

CLI commands (implement those for this phase; stub later ones with a clear
"implemented in Phase N" message):
```text
pulseiq generate [--small] [--seed 42]   # writes data/raw/*.parquet + data/raw/ground_truth.json
pulseiq build                            # runs dbt build (models + tests) into data/warehouse/pulseiq.duckdb
pulseiq profile                          # prints row counts + headline KPIs from marts
```
Makefile targets: `install`, `generate`, `generate-small`, `build`, `test`, `lint`,
`format`, `all` (= generate + build + test), `clean` (removes generated data only).

`config.py` must define sizes: **full** = 60,000 users over 120 days;
**small** = 4,000 users over 60 days. Single source of truth for seed and paths.

### Task 1.3 — Synthetic event generator (the heart of this phase)

Build `src/pulseiq/generator/` as a small, readable simulation — not random noise.
Every user follows a lifecycle driven by latent traits, so that patterns are
realistic and learnable.

**Modules:** `params.py` (all knobs + ground truth as dataclasses), `users.py`,
`lifecycle.py`, `experiments.py`, `billing.py`, `write.py`, `__init__.py`
(`generate(size, seed) -> GenerationResult`).

**Entities & output tables (parquet in `data/raw/`):**

| Table | Grain | Key columns |
|---|---|---|
| `users` | 1 row / user | `user_id, signup_ts, country, platform (ios/android/web), acquisition_channel (organic/paid_social/search/referral/influencer), device_tier (low/mid/high), app_version_at_signup` |
| `events` | 1 row / event | `event_id, user_id, session_id, event_ts, event_name, properties (JSON string), platform, app_version` |
| `sessions` | 1 row / session | `session_id, user_id, session_start, session_end, n_events` |
| `experiment_assignments` | 1 row / user × experiment | `experiment_id, user_id, variant, assigned_at` |
| `subscriptions` | 1 row / subscription | `subscription_id, user_id, plan (monthly/annual), price_usd, currency, started_at, trial_started_at, canceled_at, status` |
| `invoices` | 1 row / charge | `invoice_id, subscription_id, user_id, charged_at, amount_usd, is_refund` |
| `experiments` | 1 row / experiment | `experiment_id, name, hypothesis, start_date, end_date, population, primary_metric, guardrail_metrics, allocation` |

**Event taxonomy** (document it in `docs/EVENT_SCHEMA.md` with properties per event):
`app_install, signup, onboarding_step_viewed {step 1–5}, onboarding_step_completed
{step}, onboarding_completed, session_start, session_end, feature_used
{feature: workout_log | plan_view | progress_chart | social_share | reminder_set},
paywall_viewed {source, paywall_variant}, trial_started {plan}, subscription_started
{plan, price_usd}, subscription_renewed, subscription_canceled {reason}, refund_issued,
push_received, push_opened`. Treat the product as a fitness/habit subscription app.

**Simulation logic (make each a documented, tunable parameter):**
1. **Latent engagement** per user ~ Beta distribution, shifted by channel
   (referral/organic higher, paid_social lower), platform (iOS slightly higher), and
   device_tier. Country affects price (PPP tiers: US/UK/DE high, IN/BR/ID low) and
   conversion.
2. **Signups** arrive over the date range with weekday seasonality (+15 % Mon,
   −20 % Sat) and a marketing spike week.
3. **Onboarding** is a 5-step funnel; per-step drop probabilities depend on
   engagement and the onboarding experiment variant.
4. **Activity:** daily return probability decays with days since signup (power-law /
   exponential mix), scaled by engagement and boosted by `reminder_set` and
   `push_opened`. Sessions contain 2–15 events. Habit features (`workout_log`,
   `reminder_set`) in the first 72 h causally raise later retention — this is the
   signal Phase 2's model should discover. **Write this "true driver" list into
   ground truth.**
5. **Monetization:** paywall shown after onboarding and on feature gates; trial
   7 days; trial → paid conversion depends on engagement + price tier; monthly renews
   every 30 days with churn hazard; annual plan less likely to churn; ~2–4 % refunds.
6. **Calibrate** the default parameters so headline rates land near the legacy data
   (onboarding ~55 %, trial ~16 %, paid ~10 % of signups, D1 ~40 %, D7 ~20 %,
   D30 ~15 %). Write a small calibration test (Task 1.6) that asserts each rate is
   within ±3 pp of target on the full dataset.

**Experiments to plant (with ground truth):**

| experiment_id | Population | Design | Planted truth |
|---|---|---|---|
| `onboarding_flow_v2` | new signups in days 30–75 | 50/50 at signup | +3.0 pp onboarding completion; −0.5 pp paid conversion (real but small → likely not significant); no D30 effect |
| `paywall_redesign` | users active ≥ 14 days before start, test days 80–110 | 50/50, existing users | +8 % relative trial-start rate; pre-period sessions strongly correlated with outcome (**so CUPED will help**) |
| `streak_reminder` | new signups days 60–100 | 50/50 intended, **but a planted assignment bug drops ~6 % of treatment users on Android** | true effect +1.5 pp D7 retention; **SRM must be detectable** |

`ground_truth.json` must contain: seed, size, every parameter, each experiment's true
effects and the planted SRM bug, and the list of true retention drivers. Mark it
clearly as "for validation only — models must not read it".

**Engineering requirements:**
- Vectorize with numpy where possible; full size must generate in < 90 s.
- Same seed → byte-identical parquet content (sort rows deterministically; use
  `numpy.random.Generator` streams, never the global RNG).
- Inject realistic dirt at low rates, flagged in ground truth: ~0.3 % duplicate
  events, ~0.2 % events with client clock skew (timestamp before signup), a few
  null `platform` values. The warehouse must clean these (Task 1.5).

### Task 1.4 — Bridge to the legacy data
Write `src/pulseiq/generator/legacy_compare.py` + CLI `pulseiq compare-legacy` that
computes the legacy CSV's headline rates and the generated dataset's rates side by side
and writes `artifacts/reports/legacy_vs_generated.md`. This lets the user honestly
say: "v2 data is a calibrated simulation of v1's observed behavior."

### Task 1.5 — DuckDB + dbt warehouse
Create a dbt project in `warehouse/` (profile `pulseiq`, target path
`data/warehouse/pulseiq.duckdb`, `profiles.yml` committed inside `warehouse/` with
paths from env vars). Raw parquet registered as dbt **sources** via
`external_location` or `read_parquet`.

**Model layers (naming is important for interviews):**
- `staging/` — one model per source, renaming, typing, light cleaning:
  `stg_users, stg_events (dedupe on event_id, drop/flag clock-skew rows, coalesce
  platform), stg_sessions, stg_assignments, stg_subscriptions, stg_invoices,
  stg_experiments`.
- `intermediate/` — `int_user_first_72h` (feature-ready counts per user in first
  72 h), `int_user_daily_activity` (user × day active flag), `int_onboarding_steps`,
  `int_subscription_periods`.
- `marts/` —
  - `fct_events` (cleaned, enriched with user dims),
  - `dim_users` (dims + lifecycle timestamps: onboarded_at, trial_at, paid_at,
    last_active_at, is_paying),
  - `fct_funnel_user` (one row/user: each funnel stage flag + timestamp),
  - `agg_funnel_daily` and `agg_funnel_by_segment` (channel, platform, country tier),
  - `agg_retention_cohorts` (weekly signup cohort × day N for N ∈ {1,3,7,14,30},
    **eligibility-aware**: only users whose cohort age ≥ N count in the denominator),
  - `fct_revenue_daily` (gross, refunds, net, MRR, active subs, ARPU, ARPPU),
  - `agg_kpis_daily` (DAU, WAU, MAU, stickiness DAU/MAU, new users, conversions),
  - `fct_experiment_exposures` (one row per user × experiment with variant, pre-period
    metrics, and outcome metrics: onboarding, trial, paid, D1/D7/D30) — this is the
    contract Phase 2 depends on; document every column.
- `models/**/schema.yml` with descriptions for every model and column.

**dbt tests (required):** `unique` + `not_null` on all primary keys;
`relationships` (events → users, assignments → users, invoices → subscriptions);
`accepted_values` on event_name, platform, channel, variant; custom singular tests:
no event before signup in `fct_events`, funnel monotonicity (paid ⊆ trial ⊆ onboarded
⊆ signed up), retention rates in [0,1], cohort denominators non-increasing in N,
revenue net = gross − refunds.

**Fallback:** if `dbt-duckdb` cannot be installed, implement
`src/pulseiq/warehouse/runner.py` that executes the same `.sql` files in dependency
order (layer folder order + an explicit list) with simple `{{ ref('x') }}` string
substitution, and port the tests as SQL assertions run by pytest. Log the fallback.

**Port legacy SQL:** for each of `legacy/sql/01…11`, either map it to a new model or
note in `docs/SQL_MIGRATION.md` why it's no longer needed. Translate BigQuery syntax to
DuckDB (e.g. `DATE_DIFF` → `date_diff`, `SAFE_DIVIDE` → `x / nullif(y,0)`,
`QUALIFY` works in DuckDB).

### Task 1.6 — Tests and CI
- `tests/test_generator.py`: determinism (two runs same seed → identical frames),
  schema/dtypes, no orphan foreign keys before dirt injection, dirt rates within
  tolerance, experiment allocation ≈ 50/50 except the planted SRM.
- `tests/test_calibration.py` (marked `slow`, full size): headline rates within ±3 pp.
- `tests/test_warehouse.py`: build small warehouse in a tmp dir; assert marts exist,
  row counts > 0, dedupe removed the planted duplicates, funnel monotonic.
- `.github/workflows/ci.yml`: Python 3.11, cache pip, `make install`,
  `make lint`, `pulseiq generate --small`, `pulseiq build`, `pytest -m "not slow"`.
- `ruff` config in `pyproject.toml` (line length 100, isort rules on).

### Task 1.7 — Docs for this phase
- `docs/EVENT_SCHEMA.md` — every table and event, properties, examples.
- `docs/WAREHOUSE.md` — layer diagram (mermaid), each mart's grain and purpose,
  how to run, how tests work. Include `dbt docs generate` instructions.
- `docs/DATA_GENERATION.md` — the simulation story, parameters, ground truth, why
  synthetic data with known truth is a *feature* (you can validate methods).
- Create `docs/roadmap/PROGRESS.md` with the Phase 1 entry.
- Update the top-level `README.md` minimally: new project name "PulseIQ — Product
  Analytics & Experimentation Platform", quickstart (`make install && make all`),
  status "Phase 1 of 4 complete". The full rewrite happens in Phase 4.

---

## 5. Acceptance checks (run all; paste output into PROGRESS.md)
```bash
make install
make lint                         # zero errors
pulseiq generate --small && pulseiq build   # dbt: all models + tests PASS
pulseiq generate && pulseiq build           # full size, < 3 min total
pulseiq profile                   # prints row counts + headline KPIs
pulseiq compare-legacy            # writes artifacts/reports/legacy_vs_generated.md
pytest -q                         # all pass, including slow calibration test
python -c "import json;print(json.load(open('data/raw/ground_truth.json'))['experiments'].keys())"
git status                        # clean on branch phase-1-foundation
```
Definition of done: every check passes, headline rates are within ±3 pp of the legacy
targets, `fct_experiment_exposures` is documented column by column, legacy code is in
`legacy/`, no empty/garbled files remain in the active tree, PROGRESS.md is updated.

## 6. Cut list (if behind schedule, drop in this order)
1. `push_received/push_opened` events and the marketing spike week.
2. `int_onboarding_steps` and per-step funnel (keep stage-level funnel).
3. `sessions` table (derive sessions in staging from events instead).
4. The legacy SQL migration doc (just list files as "superseded").
Never cut: determinism, ground truth, `fct_experiment_exposures`, dbt tests, CI.

## 7. Hand-off to Phase 2 (write this into PROGRESS.md)
- Exact column list of `fct_experiment_exposures` and `int_user_first_72h`.
- Location of `ground_truth.json` and its keys.
- Full-size build time and row counts.
- Anything in the generator Phase 2 should know (e.g. how pre-period metrics are defined).

---

## 8. Learn this (Anushka — be able to explain each in an interview)
- **Event-based analytics:** why products log events (immutable facts) instead of
  user-level flags, and how flags are *derived* from events.
- **Grain:** say the grain of every mart in one sentence ("one row per user per day").
- **Staging → intermediate → marts:** why layer models; what belongs in each layer.
- **dbt:** `ref()`, `source()`, materializations (view vs table), tests, docs, lineage
  graph.
- **DuckDB vs BigQuery:** in-process OLAP vs cloud warehouse; columnar storage; why
  DuckDB is perfect for a reproducible portfolio project.
- **Eligibility-aware retention:** why a user who signed up 5 days ago can't be in the
  D7 denominator.
- **Synthetic data with ground truth:** why it lets you *prove* your methods work.
- **Determinism & seeds:** why `np.random.default_rng(seed)` beats `np.random.seed`.
- **CI:** what GitHub Actions runs on every push and why tests guard data quality.

### Viva questions to practice
1. What is the grain of `agg_retention_cohorts`, and how do you handle immature cohorts?
2. How did you deduplicate events, and why might duplicates exist in real pipelines?
3. Why did you move from BigQuery to DuckDB? What would change in production?
4. What does a dbt `relationships` test catch?
5. How do you know your synthetic data is realistic?

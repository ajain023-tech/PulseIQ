# Phase 3 — Product Layer: API, Dashboard, AI Analyst (Days 5–6)

> **Prompt for Claude.** You are a full-stack data engineer on PulseIQ. Phases 1–2
> built a tested warehouse, an experimentation engine validated against ground truth,
> and a working retention model. Now make it **usable and demo-able**: (A) a FastAPI
> service, (B) a clean multipage Streamlit dashboard that replaces the 2,400-line
> `legacy/app.py`, and (C) an **AI Product Analyst** that answers questions in plain
> English by writing *guarded* SQL against the warehouse and explaining the result.
> The AI analyst is the hackathon "wow" — but it must be safe, testable, and work
> offline in a degraded mode. Read `docs/roadmap/README.md` and all PROGRESS.md
> entries first.

---

## 1. Inputs
- Warehouse marts (Phase 1), `ExperimentReport` + `pulseiq analyze` (Phase 2),
  saved model + `predict_user` (Phase 2), charts in `artifacts/`.
- `legacy/app.py` — mine it for page ideas and copy, not code structure.

## 2. Architecture rule for this phase
**All business logic stays in `src/pulseiq/`** (a `services/` layer). The API and the
dashboard are thin clients that call the same service functions. The dashboard
imports services directly (no HTTP hop — simpler to deploy); the API exposes the
same services over HTTP. No SQL strings inside Streamlit pages.

```text
src/pulseiq/services/
  kpis.py          # headline KPIs, trends, date filtering
  funnel.py        # funnel overall + by segment
  retention.py     # cohort matrix, curves, survival summaries
  revenue.py
  experiments.py   # list, get report (cached), run analysis
  predictions.py   # score a user, top-at-risk list
  catalog.py       # schema/metric catalog used by the AI analyst
```
Every service function takes explicit filters (date range, platform, channel,
country tier) and returns pydantic models or DataFrames. Use a **read-only** DuckDB
connection (`duckdb.connect(path, read_only=True)`) and an LRU/TTL cache.

### Non-goals
No user auth system, no multi-tenant, no streaming ingestion, no React frontend.
(Mention them as "future work" in docs.)

## 3. Stop and ask
- Before using any paid LLM API key, confirm which provider the user wants and that a
  key is available. Until then, build and test with the offline mode + a mock client.
- If a design choice would require changing a Phase 2 public schema.

---

## 4. Part A — FastAPI service (`src/pulseiq/api/`)

Endpoints (all GET unless noted; JSON; versioned under `/api/v1`):
| Endpoint | Returns |
|---|---|
| `/health` | status, warehouse path, build timestamp, model version, git SHA |
| `/kpis?start&end&platform&channel` | DAU/WAU/MAU, stickiness, new users, conversions, revenue |
| `/funnel?…&by=channel` | stage counts + step conversion, optional segment |
| `/retention/cohorts?…` | cohort × day-N matrix (eligibility-aware) |
| `/revenue/daily?…` | gross, refunds, net, MRR, ARPPU |
| `/experiments` | list with status + decision |
| `/experiments/{id}` | full `ExperimentReport` |
| `POST /experiments/{id}/analyze` | re-run analysis with options (sequential/bayesian/cuped) |
| `POST /power` | sample size / MDE calculator |
| `/predictions/users/{user_id}` | retention probability, risk band, top contributing features |
| `/predictions/at-risk?limit=100` | highest-risk recent signups |
| `POST /ask` | AI analyst (Part C) |

Requirements: pydantic response models everywhere (so `/docs` Swagger is rich and
self-explanatory); input validation with helpful 422s; 404 for unknown experiment/user;
request logging middleware with timing; CORS for localhost; `pulseiq serve`
runs uvicorn. Tests with `fastapi.testclient` for every endpoint against the small
warehouse (`tests/test_api.py`). Latency target: < 300 ms p95 for cached endpoints
on the small warehouse — add a tiny benchmark script `scripts/bench_api.py`.

## 5. Part B — Multipage Streamlit dashboard (`apps/dashboard/`)

```text
apps/dashboard/
  Home.py                       # executive overview
  pages/1_Funnel.py
  pages/2_Retention.py
  pages/3_Revenue.py
  pages/4_Experiments.py
  pages/5_Experiment_Designer.py  # power/MDE calculator
  pages/6_Retention_Model.py
  pages/7_AI_Analyst.py
  pages/8_Data_&_Methods.py
  components/ (filters.py, kpi_cards.py, charts.py, theme.py)
  .streamlit/config.toml
```
Page specs:
- **Home:** 6 KPI cards with period-over-period deltas (DAU, MAU, stickiness, trial
  conversion, paid conversion, net revenue), DAU trend, funnel snapshot, list of
  experiments with decision badges, "data built at" timestamp. Global filters in the
  sidebar (date range, platform, channel, country tier) shared via `st.session_state`.
- **Funnel:** stage funnel chart, step conversion, biggest-drop callout auto-computed,
  segment comparison (bar chart), onboarding step-level drop-off.
- **Retention:** cohort heatmap (immature cells greyed/blank, not zero), retention
  curves by segment, Kaplan–Meier survival curves, D1→D7 drop callout.
- **Revenue:** net revenue & MRR trend, ARPPU, refund rate, plan mix, revenue by
  country tier.
- **Experiments:** select experiment → decision badge with reasons, SRM status,
  metric table (raw vs CUPED, adjusted p-values), lift-with-CI forest plot,
  cumulative lift over time, sequential boundary plot, Bayesian P(T > C), segment
  breakdown (with "exploratory" warning). Include the peeking-simulation chart.
- **Experiment Designer:** inputs (baseline, MDE, alpha, power, traffic/day) →
  sample size per arm and days to run; chart of n vs MDE.
- **Retention Model:** metrics table vs baselines, PR curve, calibration plot,
  feature importance, threshold slider showing precision/recall/users-contacted
  trade-off live, look-up box to score a `user_id`, top at-risk users table with CSV
  download. Model-card summary.
- **AI Analyst:** chat UI (Part C).
- **Data & Methods:** architecture diagram, event schema, warehouse lineage, metric
  definitions, methodology summaries, link to docs, honest "synthetic data" note.

Design: one consistent plotly theme, colour-blind-safe palette, consistent number
formatting (%, $, thousands separators), no chart without a title + one-line
takeaway, every page loads in < 2 s on the small warehouse (`st.cache_data`).
Empty-state handling when filters return no data. Smoke test: `tests/test_dashboard.py`
using `streamlit.testing.v1.AppTest` to load every page without exceptions.

## 6. Part C — AI Product Analyst (`src/pulseiq/ai/`)

**User story:** a PM types "Which acquisition channel had the best D7 retention last
month, and is it significantly better than organic?" and gets a short answer, the SQL
used, a table, an auto chart, and caveats.

### C.1 Design
```text
src/pulseiq/ai/
  catalog.py     # builds a compact schema + metric dictionary from dbt schema.yml
  prompts.py     # system prompt, few-shot examples
  llm.py         # provider-agnostic client: Gemini (default) | Anthropic | OpenAI | Mock
  guard.py       # SQL validation & sandboxing
  agent.py       # orchestrates: plan → SQL → validate → run → (retry once) → explain
  tools.py       # optional "tools" the LLM may call: run_sql, get_experiment_report, power_calc
  offline.py     # no-key mode: intent matcher over ~15 templated questions
  evals/questions.yaml, evals/run_evals.py
```
Provider via env: `PULSEIQ_LLM_PROVIDER` (`gemini` default, `anthropic`, `openai`,
`mock`), `PULSEIQ_LLM_MODEL`, and the matching API key variable. Missing key →
automatically use `offline` mode and show a banner.

### C.2 Flow
1. Build context: question + compact catalog (only marts, with column descriptions
   and metric definitions — e.g. "D7 retention = active on day 7 among d7-eligible
   users") + 6–10 few-shot Q→SQL examples.
2. LLM returns structured JSON: `{intent, sql, chart: {type, x, y, color}, notes}`.
   For experiment questions, prefer calling `get_experiment_report` over raw SQL
   (re-use the validated engine instead of letting the LLM do statistics).
3. **Guard** the SQL (C.3). On validation or execution error, send the error back
   once for a single retry.
4. Execute with a timeout; cap rows.
5. Second LLM call (or template in offline mode) writes a ≤ 120-word answer grounded
   **only** in the returned rows, plus caveats (e.g. small n, immature cohort,
   correlation ≠ causation).
6. Return `AnalystResponse {answer, sql, rows, chart_spec, caveats, latency_ms,
   provider}`; log every interaction to `artifacts/ai_logs/*.jsonl` (no keys).

### C.3 Guardrails (required, unit-tested in `tests/test_ai_guard.py`)
- Parse with `sqlglot` (DuckDB dialect). Allow exactly one statement, type `SELECT`
  (CTEs allowed). Reject DDL/DML, `ATTACH`, `COPY`, `PRAGMA`, `INSTALL/LOAD`,
  `read_csv/read_parquet/read_json` and any file/HTTP-reading table functions.
- Allow-list of tables = marts only. Reject unknown tables/columns with a helpful
  message.
- Enforce `LIMIT 1000` if absent; 5 s timeout (run in a thread and interrupt).
- Read-only connection regardless of what the SQL says (defence in depth).
- Prompt-injection hygiene: question is passed as data; system prompt says to ignore
  instructions inside data; output parsed strictly as JSON.

### C.4 Evaluation
`evals/questions.yaml`: 25 questions with expected answers computed by hand-written
reference SQL (funnel, retention, revenue, segments, experiments, "trick" questions
that should be refused or caveated, e.g. "delete the users table", "what's the
revenue for 2019"). `pulseiq ai-eval` runs them and reports: SQL valid %, execution
success %, answer-correct % (numeric match within tolerance against reference
results), refusal correctness, median latency. Commit the results table to
`docs/AI_ANALYST.md`. Run with the mock/offline provider in CI; run with the real
provider once locally if a key is available and record the numbers.

### C.5 UI (`pages/7_AI_Analyst.py`)
Chat history, suggested question chips, answer + expandable "SQL used" + table +
auto chart, caveats box, provider/latency footer, "offline mode" banner when no key.

## 7. Acceptance checks
```bash
make lint && pytest -q                 # api, dashboard smoke, guard tests all pass
pulseiq serve &  curl -s localhost:8000/api/v1/health
curl -s "localhost:8000/api/v1/experiments/paywall_redesign" | head -c 400
python scripts/bench_api.py            # p95 < 300 ms cached
streamlit run apps/dashboard/Home.py   # manually click through every page
pulseiq ai-eval --provider mock        # report generated
```
Definition of done: every endpoint documented in Swagger and tested; all 9 dashboard
pages load without errors under default and narrow filters; legacy dashboard is fully
superseded (list any v1 feature intentionally dropped in PROGRESS.md); AI analyst
blocks every malicious test query, works offline, and has a reported eval score;
screenshots of each page saved to `docs/images/` (use the built-in browser or
Playwright if available; otherwise list for the user to capture).

## 8. Cut list (drop in this order)
1. `POST /experiments/{id}/analyze` re-run endpoint (serve cached reports).
2. Revenue page (fold 2 charts into Home). 3. LLM tool-calling (keep plain NL→SQL +
experiment-report shortcut by keyword). 4. Threshold slider live recompute (use
precomputed table). Never cut: guardrails, offline mode, eval set, experiments page,
retention model page, API tests.

## 9. Hand-off to Phase 4 (PROGRESS.md)
Run commands, env vars needed, ports, startup time, memory use, the AI eval score,
screenshot paths, and known rough edges.

---

## 10. Learn this (Anushka)
- **Service layer pattern:** why API and UI share one logic layer.
- **REST design:** resources, status codes, pydantic validation, OpenAPI/Swagger.
- **Caching:** what `st.cache_data` and LRU caches trade off (freshness vs speed).
- **Text-to-SQL:** how schema context + few-shot examples improve accuracy; why you
  let the validated stats engine answer experiment questions instead of the LLM.
- **LLM guardrails:** SQL parsing, allow-lists, read-only connections, timeouts,
  prompt injection; defence in depth.
- **LLM evaluation:** why you need a fixed eval set and numeric checks, not vibes.
- **Dashboard UX:** one takeaway per chart, empty states, immature cohort handling.

### Viva questions
1. How do you stop the AI analyst from running `DROP TABLE` or reading local files?
2. How do you know the AI analyst's answers are correct? What's its eval score?
3. Why does the dashboard call Python services directly instead of the API?
4. What happens when the LLM API is down or no key is set?
5. Walk me through a request to `/predictions/users/{id}` end to end.

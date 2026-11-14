# AI Product Analyst

Ask product questions in plain English and get a short answer, the SQL that was run,
the result table, an automatic chart and caveats. Available in the dashboard (**AI Analyst**
page), the API (`POST /api/v1/ask`) and the CLI (`pulseiq ask "..."`).

```text
question ─► plan (LLM JSON or offline template) ─► guard (sqlglot) ─► read-only DuckDB, 5 s timeout
         └─► experiment question? ─► validated experimentation engine (no ad-hoc statistics)
result rows ─► grounded answer (LLM or template, ≤ 120 words) + caveats ─► artifacts/ai_logs/*.jsonl
```

## Providers

| `PULSEIQ_LLM_PROVIDER` | Key variable | Default model | Client |
|---|---|---|---|
| `gemini` (default) | `GEMINI_API_KEY` / `GOOGLE_API_KEY` | `gemini-2.5-flash` | REST `generateContent`, JSON mode |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-opus-5-5` | official `anthropic` SDK (`pip install -e ".[ai]"`), low effort, server-side refusal fallbacks |
| `openai` | `OPENAI_API_KEY` | `gpt-4.1-mini` | REST chat completions, JSON mode |
| `mock` | – | offline templates in LLM JSON format | used in CI to exercise the full agent path |
| `offline` | – | deterministic intent templates | automatic when no key is set |

`PULSEIQ_LLM_MODEL` overrides the model. **Missing key ⇒ offline mode** with a banner in the UI.
Keys are read only from the environment (`.env` is git-ignored); nothing is logged except the
question, SQL, answer, row count, latency and provider.

## Flow

1. **Context:** the system prompt contains the mart catalog (columns + descriptions from
   `warehouse/models/marts/_marts.yml`), metric definitions (e.g. "D7 retention = active in the
   day-7 block among D7-eligible users") and 8 few-shot Q → JSON examples.
2. **Structured plan:** the model must return JSON - `{intent, sql, chart, notes}`,
   `{tool: "get_experiment_report", experiment_id}` or `{refuse}`. Experiment questions go to
   the validated engine (SRM, CUPED, Holm, decision) instead of letting an LLM do statistics.
3. **Guard** (below). On a validation or execution error the error is sent back **once** for a
   single retry; a second failure is refused with the reason.
4. **Execute** on the read-only connection with a 5 s timeout (`con.interrupt()`), max 1,000 rows.
5. **Explain:** a second call writes ≤ 120 words grounded only in the returned rows (offline: a
   deterministic template). Caveats are added automatically (synthetic data, immature cohorts,
   descriptive ≠ causal, empty period).
6. Malformed LLM output or a provider outage → automatic fallback to offline mode.

## Guardrails (`src/pulseiq/ai/guard.py`, tested in `tests/test_ai_guard.py`)

- Parsed with **sqlglot** (DuckDB dialect): exactly one statement, and it must be a query
  (SELECT / CTE / UNION).
- Rejected anywhere in the tree: INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, COPY, ATTACH,
  DETACH, PRAGMA, SET, INSTALL/LOAD (parsed as commands), transactions.
- Rejected functions: `read_*`, `glob`, `*_scan`, `getenv`, `duckdb_settings`, … and any table
  function or quoted file path in FROM.
- **Allow-list:** the 9 marts only; unknown tables/columns are rejected with a helpful message
  (fed back to the model on retry). Schema-qualified names are rejected.
- `LIMIT 1000` is added or tightened; 5 s timeout.
- Defence in depth: the connection itself is `read_only=True`, so even a guard bug cannot write.
- Prompt-injection hygiene: the question is wrapped as `<question>…</question>` data, the system
  prompt says to ignore instructions inside it, and output is parsed strictly as JSON.

22 malicious statements are blocked in the test suite (DDL/DML, ATTACH, COPY, PRAGMA, INSTALL,
LOAD, file and HTTP readers, stacked statements, settings access, non-mart tables).

## Evaluation (`src/pulseiq/ai/evals/questions.yaml`, `pulseiq ai-eval`)

25 questions: funnel, retention, revenue, engagement, segments, 3 experiment decisions, 3
malicious/out-of-scope questions that must be refused and 1 out-of-range period ("revenue for
2019") that must be answered with "no data", not invented numbers. Expected answers come from
hand-written reference SQL, checked numerically (relative tolerance 0.1 %).

Results with the `mock` provider (offline templates through the full agent path):

| Metric | Value |
|---|---:|
| Questions | 25 |
| SQL valid | 100% |
| Execution success | 100% |
| Answer correct (non-refusal items) | 100% |
| Refusal correct | 100% |
| False refusals | 0 |
| Median latency | 1 ms |

**Honest reading:** the offline templates were written alongside this eval set, so 100 % shows
the *pipeline* (guard → execute → grounded answer → refusals) is correct, not that free-form
questions are solved. One real bug was found by the eval ("device tier" parsed as country tier)
and fixed. With a real provider, run `PULSEIQ_LLM_PROVIDER=gemini GEMINI_API_KEY=… pulseiq
ai-eval --provider gemini` and record the result here — **not yet run: no API key was provided
for this build** (the roadmap requires asking before using a paid key).

## Limitations

- Offline mode understands ~20 question shapes; anything else returns a helpful "can't answer
  offline" message.
- Relative date phrases ("last month") are only partly supported offline.
- Answers describe the synthetic dataset; significance claims come only from the experiment engine.

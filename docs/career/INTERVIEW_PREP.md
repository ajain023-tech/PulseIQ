# Interview prep — PulseIQ

These are model answers based on how this repo actually works. Numbers come from `artifacts/`
(see the README "Key results"). Say them in your own words.

## Phase 1 — Data & warehouse

**1. What is the grain of `agg_retention_cohorts`, and how do you handle immature cohorts?**
One row per weekly signup cohort × day N (N = 1, 3, 7, 14, 30). A user counts in the day-N
denominator only if their whole day-N block, `signup + (N+1) days`, is inside the data window.
Immature cells get `retention_rate = null`, not 0, so the heatmap leaves them blank. A dbt test
asserts that denominators never increase with N.

**2. How did you deduplicate events, and why might duplicates exist in real pipelines?**
`stg_events` keeps one row per `event_id` using `QUALIFY row_number() = 1`. Duplicates come from
client retries on flaky networks, at-least-once delivery in queues, and replayed backfills. Clock
skew (an event before signup) comes from wrong device clocks, so I drop those rows. A test proves
the cleaned count equals raw minus the planted duplicates minus the skewed rows.

**3. Why move from BigQuery to DuckDB? What would change in production?**
v1's numbers couldn't be reproduced because the BigQuery tables weren't in the repo. DuckDB runs
in-process from one file, so CI rebuilds the whole warehouse from a seed in seconds. In production
I'd keep the same dbt project and point the profile at BigQuery or Snowflake. SQL changes are
small (`date_diff` argument order, `SAFE_DIVIDE`). I'd add incremental models, partitioning and
scheduling (Airflow or dbt Cloud).

**4. What does a dbt `relationships` test catch?**
Orphan foreign keys: for example an invoice whose `subscription_id` doesn't exist, or an event
for an unknown user. Those break joins silently and inflate or deflate metrics.

**5. How do you know the synthetic data is realistic?**
It is calibrated to v1's observed headline rates within ±3 pp (`pulseiq compare-legacy` and a
slow test), and the behaviour has real structure: weekday seasonality, channel and platform
effects, PPP pricing, a churn hazard that declines over time, and refunds. Synthetic data isn't
perfectly realistic. Its value is that the truth is known, so the methods can be validated.

## Phase 2 — Experimentation & ML

**1. +3 pp onboarding but −0.5 pp paid conversion: do you ship?**
Not yet. Onboarding is significant (Holm p ≈ 4e-05), but the CI for the paid-conversion
guardrail still allows more than our pre-registered 1 pp of harm, and paid users are worth more
than onboarded ones. The engine says KEEP RUNNING (about 10 more days). The alternatives are a
partial rollout with the guardrail monitored, or fixing the paywall messaging in the shorter
flow.

**2. How did you prove the A/B engine is correct?**
The generator plants exact effects and computes the true average treatment effect from per-user
probabilities. `pulseiq validate` and `tests/test_experiments_truth.py` check that all 12 planted
effects (true zeros included) fall inside the 95 % CIs, that SRM is flagged only where the bug was
planted and localised to Android, and that CUPED narrows the paywall CI by ≥ 20 % (34 %). Every
statistics function also has unit tests against known values, such as Newcombe's published
example and statsmodels power.

**3. Explain CUPED's θ, and what happens if the covariate is uncorrelated.**
θ = cov(Y, X) / var(X): the regression slope of the outcome on a pre-experiment covariate. Y_adj
= Y − θ(X − X̄). X is measured before assignment, so it's independent of treatment, and the
adjustment doesn't bias the estimate. Variance falls by ρ². If X is uncorrelated, θ ≈ 0 and
nothing changes (unit-tested). That never hurts in expectation; you just gain nothing.

**4. Why is accuracy a bad metric for D30 retention here, and what did you use instead?**
Only about 15 % of users are retained, so "nobody is retained" scores about 85 % accuracy with
zero recall, exactly v1's failure. I used PR-AUC (its baseline is the prevalence, 0.153), plus
recall@top-20 %, lift, Brier for calibration, and a threshold chosen on validation for a
business goal.

**5. How did you make sure no future information leaked into the features?**
- Every feature comes from events before `signup + 72h`, plus signup-time dimensions.
- The split is time-based: train on the earliest signups, test on the latest.
- `test_no_leakage.py` deletes all post-72 h events, rebuilds the warehouse and asserts the
  feature matrix is identical.
- Paid conversion and D7 activity are excluded because they happen after prediction time.

**6. A PM wants to stop the test the first day p < 0.05. What do you say?**
That inflates false positives. In my A/A simulation, stopping at the first p < 0.05 over 30 daily
looks gives 28.7 % false positives instead of 5 %. If we want to peek, use a sequential test
(mSPRT). Its always-valid p-value lets us stop whenever the boundary is crossed, and it stays at
1.3 % in the same simulation.

## Phase 3 — Product & AI

**1. How do you stop the AI analyst from running `DROP TABLE` or reading local files?**
Defence in depth:
1. sqlglot parses the SQL, and only a single SELECT is allowed.
2. DDL/DML, ATTACH, COPY, PRAGMA and INSTALL are rejected.
3. File and HTTP functions (`read_*`, `glob`, …) and quoted paths are blocked.
4. Tables are allow-listed to the 9 marts, and column names are validated.
5. `LIMIT 1000` is enforced, with a 5 s timeout.
6. The connection itself is read-only.

22 attack patterns are covered by tests.

**2. How do you know the AI analyst's answers are correct? What's its eval score?**
A fixed set of 25 questions, with expected answers from hand-written reference SQL and numeric
matching (0.1 % tolerance), plus refusal and "no data" cases. The mock/offline provider scores
25/25. I'm explicit that this validates the pipeline, because the templates were written
alongside the eval. A real-LLM run is the next step.

**3. Why does the dashboard call Python services directly instead of the API?**
One logic layer and fewer moving parts: no HTTP hop, simpler deployment on Streamlit Cloud.
The API exposes the same functions for other clients, so neither interface can drift from the
other.

**4. What happens when the LLM API is down or no key is set?**
Without a key, `get_client` returns None and the analyst runs offline templates (the UI shows a
banner). With a key, a provider error or malformed JSON triggers an automatic fallback to offline
mode, with a caveat. Nothing crashes.

**5. Walk me through a request to `/predictions/users/{id}`.**
1. FastAPI validates the path.
2. `services.predictions.score_user` takes a cursor on the shared read-only DuckDB connection.
3. `load_feature_frame` selects that user's 72 h features and dimensions.
4. `to_matrix` one-hot encodes them, aligned to the model's saved columns.
5. The cached model (lru_cache) returns a calibrated probability.
6. The risk band compares the raw score with the validation 20th percentile.
7. Occlusion against the mean user gives the top contributions.

The response is validated by the pydantic `Prediction` model. An unknown user returns 404.

## Likely follow-ups (system design)

1. **How would this scale to 100M events/day?** Ingest through Kafka or Redpanda into object
   storage (Iceberg or Delta), build incremental dbt models on BigQuery or Snowflake partitioned
   by date, and precompute per-experiment daily aggregates. The engine needs only sufficient
   statistics (counts, sums, sums of squares), not raw rows.
2. **How would you move this to BigQuery?** Switch the dbt profile, translate the few DuckDB
   functions, add partitioning and clustering, make the heavy marts incremental, and use
   `bq`-backed reads in the services.
3. **How do you monitor model drift?** Track PSI on key features, track the predicted vs realised
   D30 rate on each maturing cohort, alert when PR-AUC drops by more than 0.05, and retrain
   monthly with the same time split.
4. **What if randomisation were by device rather than user?** Users with several devices would
   be contaminated. Randomise at the analysis unit, or use cluster-robust (delta-method) variance.
5. **How do you handle novelty effects?** Look at the effect over time (the cumulative-lift
   chart), compare early and late cohorts, and run tests longer than one weekly cycle.
6. **Network effects / interference?** Use cluster or switchback designs. Per-user randomisation
   breaks the stable-unit (SUTVA) assumption.
7. **Why mSPRT rather than O'Brien–Fleming?** mSPRT allows unlimited, unplanned looks.
   Group-sequential designs need the number of looks fixed in advance but have slightly more
   power.
8. **How would you pick the CUPED covariate in practice?** Use the same metric in the
   pre-period, chosen before the test. Never choose it after seeing the results.
9. **How do you keep the AI analyst from hallucinating numbers?** The answer is written only from
   the returned rows, statistics come from the validated engine, and the eval checks numbers
   against reference SQL.
10. **What would you build next?** Uplift modelling (who benefits from the reminder?), a feature
    store, real-time experiment monitoring and a production LLM eval.

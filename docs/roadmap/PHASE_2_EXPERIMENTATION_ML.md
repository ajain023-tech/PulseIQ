# Phase 2 — Experimentation Engine & Retention ML (Days 3–4)

> **Prompt for Claude.** You are a senior data scientist on PulseIQ. Phase 1 built a
> seeded event generator with known ground truth and a tested DuckDB/dbt warehouse.
> In this phase you build (A) a reusable **experimentation engine** that analyses any
> experiment in the warehouse and is **proven correct** by recovering the effects
> planted in `data/raw/ground_truth.json`, and (B) a **retention model that genuinely
> works** — replacing the v1 models that hit 85 % accuracy by predicting "nobody is
> retained" (recall 0). Rigor and honesty beat fancy methods. Read
> `docs/roadmap/README.md` (global rules) and the Phase 1 entry in
> `docs/roadmap/PROGRESS.md` before you start.

---

## 1. Inputs (from Phase 1)
- `data/warehouse/pulseiq.duckdb` with marts, especially `fct_experiment_exposures`
  (user × experiment: variant, pre-period metrics, outcomes), `int_user_first_72h`,
  `dim_users`, `int_user_daily_activity`, `stg_experiments`.
- `data/raw/ground_truth.json` — **only tests and validation reports may read this.
  Library code and models must never import it.**
- Three planted experiments: `onboarding_flow_v2` (+3 pp onboarding, −0.5 pp paid),
  `paywall_redesign` (+8 % relative trial start, strong pre-period covariate),
  `streak_reminder` (+1.5 pp D7, **planted SRM** on Android treatment).

If PROGRESS.md says Phase 1 deviated (e.g. dbt fallback, renamed columns), adapt and log.

## 2. Goals
**A. Experimentation engine — `src/pulseiq/experiments/`**
1. Sample-ratio-mismatch (SRM) detection, overall and per segment.
2. Frequentist readout for proportion and mean metrics, with CIs and relative lift.
3. CUPED variance reduction using pre-period covariates.
4. Multiple-testing correction across metrics (Holm / Benjamini–Hochberg).
5. Sequential testing (always-valid / mSPRT or alpha-spending) so peeking is safe.
6. Bayesian readout (Beta-Binomial): P(treatment > control), expected loss.
7. Power / MDE / sample-size calculator.
8. Segment (heterogeneous-effect) breakdown with appropriate caution.
9. A **decision framework** producing `SHIP / DON'T SHIP / KEEP RUNNING / INVESTIGATE`
   with reasons, from primary metric + guardrails + SRM status.
10. A validation report proving the engine recovers ground truth.

**B. Retention ML — `src/pulseiq/ml/`**
1. Leakage-free features from the first 72 h after signup only.
2. Time-based train/validation/test split.
3. Baseline + 2 stronger models, handling class imbalance properly.
4. Evaluate with PR-AUC, ROC-AUC, recall@k, calibration; choose a business threshold.
5. Explainability (permutation importance; SHAP if it installs).
6. Survival analysis: Kaplan–Meier curves by segment + Cox model.
7. Check whether the model recovers the true drivers planted in Phase 1.
8. A model card.

### Non-goals
No API endpoints, no dashboard pages, no LLM (Phase 3). No deep learning. No
hyper-parameter search bigger than a small grid / ≤ 30 random trials.

## 3. Stop and ask
- The engine **cannot** recover a planted effect within its 95 % CI after you've
  checked for bugs — report findings instead of tuning the generator to match.
- You want to change the Phase 1 generator's ground truth or schema (allowed only
  for genuine bugs; explain the bug).

---

## 4. Part A tasks — Experimentation engine

Structure:
```text
src/pulseiq/experiments/
  __init__.py
  data.py        # load exposures for an experiment from DuckDB -> tidy DataFrame
  srm.py
  frequentist.py
  cuped.py
  corrections.py
  sequential.py
  bayesian.py
  power.py
  segments.py
  decision.py
  report.py      # builds ExperimentReport (pydantic) + markdown/JSON rendering
```

### A.1 Data access
`load_experiment(con, experiment_id) -> ExperimentData` returning a DataFrame plus
metadata (primary metric, guardrails, start/end dates) from `stg_experiments`.
Metrics registry in `metrics.py` or config: name, type (`proportion` | `mean`),
column, direction (higher is better?), eligibility column (e.g. `d30_eligible`).
Always filter on eligibility before computing a rate — this was a v1 strength;
keep it.

### A.2 SRM
Chi-square goodness-of-fit vs expected allocation; flag when p < 0.001 (industry
convention). Also run per `platform` and `country_tier` to localise the cause.
**Must flag `streak_reminder` overall and localise it to Android.**

### A.3 Frequentist readout
- Proportions: two-proportion z-test, Newcombe/Wilson or normal-approx CI for the
  difference; relative lift with delta-method CI.
- Means: Welch's t-test; for heavy-tailed revenue, also report a bootstrap CI
  (vectorised, ≤ 2,000 resamples, seeded).
- Output per metric: n per arm, rate/mean per arm, abs diff, rel lift, CI, p-value.

### A.4 CUPED
θ = cov(Y, X)/var(X) on pooled data; Y_adj = Y − θ(X − mean(X)). Report variance
reduction % and CI width before/after. Use the pre-period covariate from
`fct_experiment_exposures` (e.g. sessions in the 14 days before the test).
**On `paywall_redesign` it must cut CI width by ≥ 20 %.** For new-user experiments
with no pre-period, skip CUPED gracefully with a reason.

### A.5 Multiple testing
Holm for confirmatory metrics; BH-FDR when ≥ 5 exploratory metrics/segments. Show raw
and adjusted p-values side by side.

### A.6 Sequential testing
Implement an always-valid mixture SPRT for the difference in proportions (normal
approximation, documented mixing variance τ²) **or** O'Brien–Fleming alpha spending
over K looks. Provide `simulate_peeking(...)` showing: naive daily peeking on an A/A
test inflates false-positive rate far above 5 %, while your sequential method stays
≤ ~5 %. Save this as a chart — it is a great demo/interview story.

### A.7 Bayesian
Beta(1,1) priors; posterior draws (seeded, 100k); P(T > C), expected loss for
shipping each variant, 95 % credible interval for lift. Explain in docs when you'd
use Bayesian vs frequentist readouts.

### A.8 Power / MDE
`sample_size(baseline, mde, alpha, power, ratio)` and `mde(n, baseline, ...)` for
proportions; plus a "how many days to run" estimate from daily traffic in the warehouse.
Validate against `statsmodels` if installed (tests).

### A.9 Segments
Effects by platform, channel, country tier with CIs and BH correction; label clearly as
exploratory; warn when segment n is underpowered.

### A.10 Decision framework (`decision.py`)
Rules, documented in `docs/EXPERIMENTATION.md`:
1. SRM detected → `INVESTIGATE` (no readout trusted).
2. Primary metric significant positive (after correction) and no guardrail
   significantly negative beyond its tolerance → `SHIP`.
3. Guardrail significantly worse → `DON'T SHIP` (even if primary wins).
4. Not significant and sample < required n → `KEEP RUNNING` (+ estimated days left).
5. Not significant and adequately powered → `DON'T SHIP (no detectable effect)`.
Each decision carries a list of human-readable reasons.
Expected: `onboarding_flow_v2` → most likely `KEEP RUNNING` or ship-with-caution
discussion because of the paid-conversion guardrail; `paywall_redesign` → `SHIP`;
`streak_reminder` → `INVESTIGATE`. If your engine says otherwise, explain why in the
report — don't force it.

### A.11 Reports & CLI
- `pulseiq analyze <experiment_id> [--sequential] [--bayesian]` → writes
  `artifacts/experiments/<id>/report.json` and `report.md` plus charts (PNG via
  matplotlib or plotly static): metric lifts with CIs, cumulative lift over time,
  sequential boundary plot, posterior distributions.
- `pulseiq analyze --all`.
- `ExperimentReport` is a pydantic model — Phase 3's API and dashboard consume it, so
  keep it stable and documented.

### A.12 Validation against ground truth
`tests/test_experiments_truth.py` + `artifacts/reports/experiment_validation.md`:
- For each planted effect: true value, estimate, 95 % CI, covered? (yes/no).
- SRM correctly flagged only on `streak_reminder`.
- CUPED variance reduction on `paywall_redesign`.
- A/A simulation (≥ 500 runs, small n, seeded, vectorised): false-positive rate of
  naive fixed-horizon test ≈ 5 %, naive peeking ≫ 5 %, sequential ≈ ≤ 5 %.
Unit tests for every stats function with hand-computable examples.

---

## 5. Part B tasks — Retention ML

Structure:
```text
src/pulseiq/ml/
  features.py    # build feature matrix from warehouse (SQL + pandas)
  split.py       # time-based split
  train.py       # model zoo + training
  evaluate.py    # metrics, curves, calibration, threshold selection
  explain.py     # permutation importance, SHAP (optional)
  survival.py    # Kaplan–Meier, Cox
  model_card.py
```

### B.1 Target & features (no leakage)
- **Target:** `d30_retained` (active on any day in [day 28, day 31] after signup —
  match whatever Phase 1 defined; document it). Population: `d30_eligible = 1`.
- **Features (only events with `event_ts < signup_ts + 72h`):** sessions, active days
  (0–3), total events, distinct features used, counts per feature (esp.
  `workout_log`, `reminder_set`), onboarding steps completed, onboarding completed,
  minutes to first key action, paywall views, trial started within 72 h, push opens,
  plus dims (platform, channel, country tier, device tier, signup weekday) one-hot.
  Experiment variants may be included as features only with a note.
- **Explicitly excluded:** anything after 72 h, including `paid_conversion`, D7 flags,
  later sessions. v1 used `d1_retained` and `paid_conversion` without timestamps —
  write in the docs why that was risky.
- Write a `tests/test_no_leakage.py` that rebuilds features with all post-72 h events
  deleted and asserts the feature matrix is identical.

### B.2 Split
Time-based by signup date: train = earliest 70 %, validation = next 15 %, test = last
15 % of eligible users. Never shuffle across time. Report class balance per split.

### B.3 Models
1. Baseline: always-majority (to show why accuracy is meaningless here) and a
   one-rule heuristic ("retained if active ≥ 2 of first 3 days").
2. Logistic regression (standardised, `class_weight='balanced'`).
3. `HistGradientBoostingClassifier` (sklearn; native categorical support). Use
   LightGBM only if it installs cleanly — optional.
Small hyper-parameter search on validation using PR-AUC. Fix seeds.

### B.4 Evaluation (`artifacts/ml/`)
- Metrics table on **test**: PR-AUC (primary), ROC-AUC, Brier score, recall,
  precision, F1 at chosen threshold, recall@top-20 %, lift@top-decile.
- Threshold chosen on validation for a stated business goal, e.g. "a retention
  campaign can contact 20 % of new users — maximise retained users caught" — or
  cost-based (cost of contact vs value of a saved user). Document the reasoning.
- Calibration curve; apply isotonic/Platt calibration on validation if needed.
- PR and ROC curves, confusion matrix at the threshold, lift/gain chart.
- Target: the best model must clearly beat both baselines on PR-AUC; there is no
  fixed number to hit — report honestly.
- Persist the best model with `joblib` + a `model_meta.json` (features, threshold,
  training window, metrics, git SHA, sklearn version).

### B.5 Explainability
Permutation importance on test (always). SHAP summary plot if `shap` installs.
Compare top drivers to `ground_truth.json` true drivers in a validation section
(test code may read ground truth; the model may not).

### B.6 Survival analysis
Define "churn" = no activity for 14 consecutive days (document). Kaplan–Meier curves
of time-to-churn by channel, platform, and onboarding variant; log-rank tests; a Cox
PH model with key 72 h features (report hazard ratios). Use `lifelines`; fallback:
implement Kaplan–Meier yourself in numpy and skip Cox with a log entry.

### B.7 CLI & docs
- `pulseiq train` (features → split → train → evaluate → save), `pulseiq survival`.
- `docs/ML_RETENTION.md`: problem framing, why accuracy failed in v1, leakage policy,
  split, models, results table (generated numbers only), threshold rationale, drivers,
  limitations.
- `docs/MODEL_CARD.md` (intended use, data, metrics, caveats, fairness check of
  recall across platform/country tier, retraining plan).
- `docs/EXPERIMENTATION.md`: every method with formula, when to use it, assumptions,
  and the validation results.

---

## 6. Acceptance checks
```bash
make lint && pytest -q                         # incl. truth + leakage tests
pulseiq analyze --all                          # 3 reports in artifacts/experiments/
pulseiq train && pulseiq survival              # artifacts/ml/ populated
cat artifacts/reports/experiment_validation.md # all planted effects covered, SRM only on streak_reminder
```
Definition of done:
- Every planted effect lies in its 95 % CI (or a documented, investigated exception).
- SRM flagged only for `streak_reminder`, localised to Android.
- CUPED reduces CI width ≥ 20 % on `paywall_redesign`.
- Peeking simulation chart shows the inflation and the fix.
- Best model beats baselines on test PR-AUC with recall > 0 and a justified threshold.
- Leakage test passes. Model card + docs written. PROGRESS.md updated, branch
  `phase-2-exp-ml` merged after checks pass.

## 7. Cut list (drop in this order)
1. Cox model (keep Kaplan–Meier). 2. SHAP (keep permutation importance).
3. Bayesian expected-loss (keep P(T > C)). 4. Segment HTE (keep overall + SRM by
segment). Never cut: SRM, CUPED, sequential + peeking demo, truth validation,
leakage test, time split, PR-AUC.

## 8. Hand-off to Phase 3 (in PROGRESS.md)
- `ExperimentReport` schema and the function to produce it.
- Model loading function + feature-building function for a single user
  (`predict_user(con, user_id)`), threshold, and expected latency.
- Paths of every chart/artifact the dashboard should show.

---

## 9. Learn this (Anushka)
- **SRM:** what it is, why it invalidates a test, common causes (redirect bugs,
  bot filtering, platform-specific crashes).
- **CUPED:** intuition — "subtract the part of the outcome you could predict before the
  test started"; why it shrinks variance without bias; when it can't be used.
- **Peeking problem:** why checking p-values daily inflates false positives; how
  sequential tests fix it.
- **Frequentist vs Bayesian readouts:** what a p-value is *not*; what P(T > C) means.
- **Power & MDE:** relationship between sample size, baseline, effect size.
- **Multiple comparisons:** Holm vs BH; why segment fishing is dangerous.
- **Guardrail metrics** and why a winning primary metric isn't enough.
- **Class imbalance:** why 85 % accuracy was meaningless; PR-AUC vs ROC-AUC.
- **Leakage:** feature-time cutoff, time-based splits.
- **Calibration** and threshold choice from business costs.
- **Survival analysis:** censoring, Kaplan–Meier, hazard ratios.

### Viva questions
1. Your test shows +3 pp onboarding but −0.5 pp paid conversion. Do you ship?
2. How did you prove your A/B engine is correct?
3. Explain CUPED's θ and what happens if the covariate is uncorrelated.
4. Why is accuracy a bad metric for D30 retention here? What did you use instead?
5. How did you make sure no future information leaked into features?
6. A PM wants to stop the test the first day p < 0.05. What do you say?

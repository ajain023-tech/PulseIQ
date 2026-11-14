# Experimentation engine

`src/pulseiq/experiments/` analyses any experiment in `fct_experiment_exposures`
and produces an `ExperimentReport` (a pydantic model the API and dashboard read).

```bash
pulseiq analyze --all            # artifacts/experiments/<id>/report.{json,md} + charts
pulseiq analyze paywall_redesign --no-bayesian
pulseiq validate                 # artifacts/reports/experiment_validation.md (vs ground truth)
```

| Module | What it does |
|---|---|
| `data.py` | `load_experiment(con, id)`: reads the exposures plus metadata (primary, guardrails, secondaries, dates, allocation) from `stg_experiments` |
| `metrics.py` | Metric registry (name, kind = proportion or mean, column, direction, **eligibility column**), plus the pre-registered design (MDE, guardrail tolerances) |
| `srm.py` | Chi-square SRM test overall and per segment, plus root-cause localisation |
| `frequentist.py` | Two-proportion z-test, Wilson and Newcombe CIs, delta-method relative lift, Welch t, seeded bootstrap |
| `cuped.py` | CUPED adjustment and diagnostics |
| `corrections.py` | Holm (confirmatory) and Benjamini–Hochberg (exploratory) |
| `sequential.py` | mSPRT always-valid test, confidence sequences, and the A/A peeking simulation |
| `bayesian.py` | Beta-Binomial posterior: P(T > C), expected loss, credible intervals |
| `power.py` | Sample size, MDE, days to run |
| `segments.py` | Heterogeneous effects by platform, channel and country tier (BH, underpowered warnings) |
| `decision.py` | SHIP / DON'T SHIP / KEEP RUNNING / INVESTIGATE, with reasons |
| `report.py`, `charts.py` | Report assembly, markdown rendering, forest, sequential and posterior charts |

**Eligibility first.** Every rate is computed only over rows whose matching
`*_eligible` flag is 1. For example, D30 retention for a user who signed up 10 days
ago is unknown, not 0.

## Methods

### Sample-ratio mismatch (SRM)
Chi-square goodness of fit of the observed arm sizes against the intended allocation:
χ² = Σ (O − E)² / E, with 1 df. The engine flags SRM at **p < 0.001** (the industry
convention; SRM tests run on every experiment, so a strict α keeps false alarms
rare). The same test runs inside every platform and country tier.

A flagged segment is a **likely cause** only if two things hold. First, excluding it
removes the SRM. Second, the remaining traffic's deviation from the intended split
is less than half the segment's own deviation. Without the second condition, a
large segment such as "low country tier" would look guilty simply because removing
it removes power.

*Why it matters:* SRM means assignment or logging is broken: redirect bugs, bot
filtering, platform-specific crashes, or (here) a logging bug that drops Android
treatment users. The arms are no longer comparable, so **no** readout can be
trusted.

### Frequentist readout
- **Proportions:** a pooled two-proportion z-test gives the p-value. The CI for the
  difference is the Newcombe hybrid score interval (method 10), built from Wilson
  intervals. Relative lift t/c − 1 gets a delta-method CI on log(p_t/p_c):
  SE² = (1−p_t)/(n_t p_t) + (1−p_c)/(n_c p_c).
- **Means:** Welch's t-test with Welch–Satterthwaite degrees of freedom. For
  heavy-tailed revenue there is also a percentile bootstrap CI (2,000 resamples,
  vectorised, seeded).

### CUPED (Deng et al., 2013)
θ = cov(Y, X) / var(X) on pooled data; Y_adj = Y − θ (X − X̄). Then Welch on Y_adj.
- **Intuition:** subtract the part of the outcome you could have predicted *before*
  the test started. X is measured before assignment, so it is independent of the
  treatment, and the adjustment removes variance without adding bias (the mean is
  unchanged).
- The variance reduction equals ρ²(Y, X). If the covariate is uncorrelated, θ ≈ 0
  and nothing changes (unit-tested).
- **Covariate:** `pre_sessions_14d`, the sessions in the 14 days before assignment.
  It is pre-registered, not picked after looking at results.
- **When it can't be used:** new-user experiments randomised at signup have no
  pre-period. The engine detects `assigned_at_signup` and skips CUPED with a reason.

### Multiple testing
- **Holm** across the confirmatory family (primary + guardrails). It controls the
  family-wise error rate.
- **Benjamini–Hochberg** across secondary metrics and across segment tests. These
  are exploratory, so false-discovery-rate control is enough.

Raw and adjusted p-values are reported side by side.

### Sequential testing (mSPRT)
For an effect estimate d̂ ~ N(θ, V) and a N(0, τ²) mixing prior, the mixture
likelihood ratio is

  Λ = √(V / (V + τ²)) · exp(τ² d̂² / (2 V (V + τ²))).

Rejecting the first time Λ ≥ 1/α keeps the type-I error at α **however often you
look** (Johari et al., 2017). The always-valid p-value is min over looks of 1/Λ. The
confidence sequence is d̂ ± √(V (V + τ²)/τ² · (2 ln(1/α) + ln((V + τ²)/V))). τ is
set to the pre-registered MDE: a larger τ gives more power against large effects,
a smaller τ against small ones. Reports show retrospective daily looks by assignment
date.

**Peeking demo** (`simulate_peeking`, 2,000 A/A tests, 30 daily looks, 200 users
per arm per look, baseline 20 %):

| Procedure | False-positive rate |
|---|---:|
| Fixed horizon (one look) | 5.2 % |
| Naive peeking (stop at first p < 0.05) | **28.7 %** |
| mSPRT (always valid) | 1.3 % |

![peeking](../artifacts/experiments/peeking_simulation.png)

### Bayesian readout
Each arm gets a Beta(1, 1) prior and a Beta(1 + x, 1 + n − x) posterior. The engine
takes 100,000 seeded draws and reports P(T > C), the expected loss of shipping each
arm, E[max(p_other − p_ship, 0)], and 95 % credible intervals for the absolute and
relative lift.

*When to use which:* frequentist readouts give error-rate guarantees for a
pre-registered decision rule, which is the right tool for the ship gate.
Bayesian readouts answer "how likely is B better, and how much do we lose if we're
wrong?". They are easier to communicate and suit low-stakes or reversible
decisions, but they depend on the prior and are not protected against peeking by
default.

### Power, MDE and run length
n per arm = (z₁₋α/₂ √(p̄ q̄ (1 + 1/k)) + z₁₋β √(p₁q₁ + p₂q₂/k))² / δ², with k the
treatment/control ratio. `mde()` inverts this numerically and `days_to_run()` uses
daily traffic from the warehouse. The test suite checks the formula against
statsmodels (within 3 %) and against the textbook value: 10 % → 12 % needs about
3,840 users per arm.

### Segments
The primary metric's effect is computed within each platform, channel and country
tier, with Newcombe CIs and BH correction. Segments too small for the MDE are
flagged `underpowered`. This analysis is **labelled exploratory**: a segment
"winning" after slicing 11 ways is often noise.

### Decision framework (`decision.py`)
Rules are checked in order:

1. SRM (p < 0.001) → **INVESTIGATE**.
2. A guardrail is significantly worse (Holm) → **DON'T SHIP**, even if the primary
   wins.
3. The primary is significantly better (Holm) and every guardrail is shown
   non-inferior (the CI excludes harm beyond the tolerance) → **SHIP**.
4. The primary is significantly better but a guardrail is not yet shown safe →
   **KEEP RUNNING**, with the days needed to bound it.
5. The primary is not significant and n is below the required n → **KEEP RUNNING**,
   with the days left.
6. The primary is not significant and the test is adequately powered →
   **DON'T SHIP (no detectable effect)**.
7. The primary is significantly worse → **DON'T SHIP**.

Pre-registered tolerances (`metrics.py`): onboarding_flow_v2 allows paid_30d −1.0 pp
and d30 −1.5 pp; paywall_redesign allows refund_in_test +0.5 pp; streak_reminder
allows D1 −1.0 pp.

## Results on the generated data (full size, seed 42)

| Experiment | Decision | Why |
|---|---|---|
| `onboarding_flow_v2` | **KEEP RUNNING** | Onboarding +2.81 pp (95 % CI +1.54 to +4.07, Holm p = 4.1e-05). The paid-conversion guardrail is −0.31 pp, but its CI allows up to 1.07 pp of harm, above the 1.0 pp tolerance. About 10 more days of traffic would bound it. |
| `paywall_redesign` | **SHIP** | Trial start +2.81 pp with CUPED (95 % CI +1.66 to +3.96, Holm p = 3.5e-06). The refund guardrail's worst plausible harm is 0.27 pp, within the 0.5 pp tolerance. |
| `streak_reminder` | **INVESTIGATE** | SRM p = 3.2e-06: treatment share 48.3 % vs 50 %. The likely cause is `platform=android`. |

### Validation against planted ground truth
`artifacts/reports/experiment_validation.md` (also enforced by
`tests/test_experiments_truth.py`):

- **12 / 12 planted effects** lie inside the engine's 95 % CI. This includes the
  −0.5 pp paid-conversion harm, the +1.5 pp D7 effect behind the SRM, and the true
  zeros.
- SRM is flagged **only** on `streak_reminder` and localised to **Android**.
- CUPED on `paywall_redesign` cuts variance by 56.7 % and **CI width by 34.1 %**
  (target ≥ 20 %).
- A/A false-positive rates: fixed horizon 5.2 %, naive peeking 28.7 %, mSPRT 1.3 %.

The ground truth is the exact average treatment effect, computed by the generator
from per-user probabilities. The engine never reads it; only `pulseiq validate` and
the tests do.

## The onboarding trade-off (viva question 1)

The new flow lifts onboarding by about 3 pp. The paid-conversion guardrail's point
estimate is slightly negative, and in truth it is −0.5 pp. The engine says **KEEP
RUNNING**: the onboarding gain is real, but we can't yet rule out more than 1 pp of
paid-conversion harm, and paid users are worth more than onboarded ones. The
options are to run about 10 more days, to ship to a small share with the guardrail
monitored, or to fix the paywall messaging in the shorter flow before shipping.

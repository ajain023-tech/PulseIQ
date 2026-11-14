# Data generation: a simulation with known ground truth

`pulseiq generate [--small] [--seed 42]` runs `pulseiq.generator.generate()`. It
simulates users of a fitness/habit subscription app and writes raw parquet plus
`data/raw/ground_truth.json`.

| Size | Users | Days | Typical runtime | Events |
|---|---:|---:|---:|---:|
| `full` (default) | 60,000 | 120 | ~10 s | ~7.1 M |
| `small` (`--small`, CI / cloud) | 4,000 | 60 | < 1 s | ~0.3 M |

The data starts on Monday 2025-01-06. Every parameter is in
`src/pulseiq/generator/params.py`.

## Why synthetic data with ground truth is a feature

Real product data never tells you the *true* effect of an experiment, so you
cannot prove an A/B engine is right. Here we **plant** effects, for example
"+3.0 pp onboarding completion". The generator computes the exact average treatment
effect from the per-user probabilities it uses, and writes it to `ground_truth.json`.
Phase 2 then checks that the engine's 95 % confidence intervals cover these values,
that SRM is flagged where a bug was planted, and that the retention model finds the
drivers that really cause retention. **Library code and models never read the
ground-truth file; only tests and validation reports do.**

## The simulation story

1. **Users.** Country (with a PPP price tier), platform, acquisition channel and
   device tier are drawn from fixed mixes. Each user gets a latent **engagement**
   `z = logit(Beta(2.2, 2.8))`, shifted by segment. Referral and organic are higher,
   paid social lower, iOS a little higher, and low-end devices lower.
2. **Signups** arrive with weekday seasonality (Monday ×1.15, Saturday ×0.80) and a
   ×1.6 marketing-spike week at 35 % of the date range. Time of day follows a curve
   that peaks in the evening.
3. **Onboarding.** Five steps; completion probability is `sigmoid(0.5 + 0.9 z)`.
   Users who don't finish drop at step 1–5 with probabilities 34/25/18/13/10 %.
4. **First 72 h (days 0–2).** Day 0 is always active. Days 1–2 are active with
   probability `sigmoid(-0.18 + 0.9 z)`. Each active day has `1 + Poisson(0.25 + 0.6·eng)`
   sessions, and each session has `Poisson(2.5 + 3·eng)` middle events (at most 13),
   drawn from user-specific weights. More engaged users log more workouts and set
   more reminders.
5. **Habits cause retention (the "true drivers").** From day 3 on, a user stays
   *alive* until a latent churn time with cumulative hazard
   `m · 1.55 · (d − 2)^0.32`, where
   `log m = −0.55 z − 0.70·[reminder_set in 72 h] − 0.10·min(workout_log in 72 h, 8) − 0.35·(active days among days 1–2)`.
   While alive, a user is active on a given day with probability `sigmoid(0.35 + 0.6 z)`.
6. **Monetization.** Only onboarded users see the onboarding paywall. A trial
   starts with probability `sigmoid(-0.92 + 0.7 z + tier shift)`. 60 % of trials
   start on day 0; the rest start in a later session within 14 days. A trial lasts
   7 days. It converts with probability `sigmoid(0.22 + 0.6 z + tier shift)` (low
   tier −0.25, high +0.15). 25 % of plans are annual. Monthly plans renew every 30
   days; the cancel probability per renewal is 8 % if the user is still active in
   the app and 45 % if they have churned. About 3 % of charges are refunded, which
   also cancels the subscription.
7. **Calibration.** The defaults reproduce the v1 data's headline rates within
   ±3 pp (`tests/test_calibration.py`, full size). See
   `artifacts/reports/legacy_vs_generated.md` (`pulseiq compare-legacy`).

## Planted experiments

The day windows below are for the 120-day full size. For other sizes they are
scaled in proportion (small: ×0.5).

| Experiment | Population | Planted truth |
|---|---|---|
| `onboarding_flow_v2` (days 30–75) | new signups, 50/50 at signup | onboarding completion +3.0 pp (additive per user, capped at 99.5 %). Paid-in-30-days −0.5 pp exactly, by scaling treatment P(paid \| trial) with a factor solved in closed form. No effect on retention. |
| `paywall_redesign` (days 80–110) | existing free users with ≥ 14 days tenure and a session in the 28 days before the start | trial-in-test probability `min(0.045 × pre_sessions_14d, 0.88)`; treatment ×1.08 (**+8 % relative**). The strong link to the pre-period covariate is what lets CUPED help. |
| `streak_reminder` (days 60–100) | new signups, 50/50 at signup | churn-hazard multiplier chosen by root-finding so that **mean D7 lift = +1.5 pp** exactly. **Planted SRM bug:** 6 % of all treatment users, all on Android, are silently missing from the assignment log. |

Each experiment's entry in `ground_truth.json` holds the exact effect over its
population (`true_effects_abs`, and `true_effects_rel` for the paywall), the
logged/intended counts, and any planted bug.

## Determinism

- One master seed feeds `numpy.random.SeedSequence(seed).spawn(14)`, giving one
  independent `Generator` stream per stage. The global numpy RNG is never used, so
  adding a draw in one stage can't change the others.
- Rows are sorted deterministically, and parquet is written without pandas metadata
  using fixed compression. The same seed gives byte-identical files
  (`tests/test_generator.py::test_determinism_parquet_bytes`).

## ground_truth.json keys

`_note`, `seed`, `size`, `n_users`, `n_days`, `start_date`, `data_end`, `params`
(every parameter), `experiments.<id>` (window, counts, true effects, bug),
`true_retention_drivers`, `dirt`, `definitions`, `row_counts`.

# D30 retention model

```bash
pulseiq train      # features -> time split -> train -> calibrate -> evaluate -> artifacts/ml/
pulseiq survival   # Kaplan-Meier, log-rank, Cox -> artifacts/ml/survival.json + km_*.png
pulseiq validate   # also writes artifacts/reports/ml_validation.md (drivers vs ground truth)
```

## Problem framing

Predict at **72 hours after signup** whether a new user will still be active on
**day 30**. The product use is an early retention campaign: rank new users, then
contact the most at-risk 20 % (or reward the likely-retained).

- **Target:** `d30_retained` means a session started in the day-30 block
  `[signup + 30 d, signup + 31 d)`. This is the same exact-day definition used by
  the warehouse, dashboards and experiments.
- **Population:** users with `signup_ts + 31 d ≤ data_end`, i.e. 45,095 users at
  full size, with a positive rate of about 14–15 %.

## Why v1's 85 % accuracy was meaningless

Only about 15 % of users are retained at D30. A model that predicts "nobody is
retained" is therefore about 85 % accurate and completely useless; v1's Logistic
Regression and Decision Tree did exactly that (recall 0). Our majority baseline
reproduces the failure: **accuracy 0.847, recall 0.000, PR-AUC 0.153**. With
imbalanced classes we use **PR-AUC** as the primary metric. Its baseline equals the
prevalence, and it focuses on the minority class. ROC-AUC, recall@k, lift and Brier
are secondary.

## Leakage policy

- All behavioural features come from `int_user_first_72h`: events with
  `event_ts < signup_ts + 72h`. The rest are signup-time dimensions (platform,
  channel, country tier, device tier, signup weekday).
- **Excluded:** anything after 72 h, including paid conversion, D7 activity, later
  sessions and the experiment variants.
- v1 used `d1_retained` and `paid_conversion` without timestamps. Paid conversion
  happens about 7+ days after signup (trial length), so at prediction time it is
  information from the future. Its high "importance" in v1 was partly leakage.
- `tests/test_no_leakage.py` deletes every event at or after signup + 72 h,
  rebuilds the warehouse, and asserts the feature matrix is **byte-for-byte
  identical**.

**Features (37):** sessions, active days (0–3), total events, distinct features,
per-feature counts (`workout_log`, `plan_view`, `progress_chart`, `social_share`,
`reminder_set`), a reminder-set flag, onboarding steps completed, onboarding
completed, paywall views, trial started within 72 h, push opens, minutes to the
first workout, and one-hot dimensions.

## Split

The split is time-based by signup date and is never shuffled across time: train is
the earliest 70 %, validation the next 15 %, test the latest 15 %.

| Split | Signups | Rows | Positive rate |
|---|---|---:|---:|
| train | 2025-01-06 → 2025-03-08 | 31,566 | 14.1 % |
| validation | 2025-03-08 → 2025-03-21 | 6,764 | 14.5 % |
| test | 2025-03-21 → 2025-04-04 | 6,765 | 15.3 % |

## Models

1. **Majority baseline**: predicts the training rate for everyone.
2. **Active-days heuristic**: "retained if active on ≥ 2 of the first 3 days".
   Ranked by the training retention rate of each active-days level.
3. **Logistic regression**: standardised, `class_weight="balanced"`, C ∈
   {0.01, 0.1, 1, 10}.
4. **HistGradientBoostingClassifier**: `class_weight="balanced"`, 16-point grid
   (learning rate, depth, leaves, L2).

Hyper-parameters are chosen on **validation PR-AUC**, with seeds fixed. Class
weighting inflates predicted probabilities, so the chosen model gets **isotonic
calibration** fitted on validation. Ranking metrics use the uncalibrated scores,
because isotonic steps create ties.

## Results (test set, generated numbers from `artifacts/ml/metrics.json`)

| Model | PR-AUC | ROC-AUC | Brier | Recall | Precision | F1 | Recall @ top 20 % | Lift @ top 10 % | Accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Majority baseline | 0.153 | 0.500 | 0.129 | 0.000 | 0.000 | 0.000 | 0.199 | 1.04 | 0.847 |
| Active-days heuristic | 0.303 | 0.766 | 0.112 | 0.949 | 0.234 | 0.375 | 0.486 | 2.39 | 0.518 |
| Logistic regression | 0.486 | 0.852 | 0.099 | 0.707 | 0.401 | 0.512 | 0.600 | 3.54 | 0.794 |
| **HistGradientBoosting (selected)** | **0.484** | **0.854** | **0.099** | **0.704** | **0.413** | **0.521** | **0.600** | **3.55** | 0.802 |

HistGradientBoosting was selected on validation PR-AUC. On test it ties with
logistic regression (0.484 vs 0.486). We report this honestly instead of switching
models after looking at test. Both models **more than triple** the majority
baseline's PR-AUC and clearly beat the heuristic.

## Threshold

- **Classification threshold 0.267** (calibrated P(retained)) maximises F1 for the
  retained class on **validation**. On test it gives recall 0.704 and precision
  0.413 (confusion matrix: TN 4,700, FP 1,033, FN 305, TP 727).
- **Campaign band:** the business goal is "a retention campaign can contact 20 %
  of new users". Users below the 20th percentile of the validation score are
  *high risk*. On test that band holds 19.2 % of users, **99.6 % of whom churn**
  (vs 84.7 % overall), and it captures 22.6 % of all churners.
- The dashboard's threshold slider uses the precomputed trade-off table
  `artifacts/ml/threshold_table.json`.

## Drivers (explainability)

Permutation importance on test (drop in PR-AUC; `permutation_importance.png`), plus
a SHAP summary for the tree model (`shap_summary.png`):

1. `workout_log_72h`
2. `active_days_72h`
3. `reminder_set_72h`
4. `total_events_72h`

**Validation:** the generator planted exactly three explicit drivers (reminder set,
workout logs and early active days in the first 72 h), plus latent engagement. All
three are the model's top three features (`artifacts/reports/ml_validation.md`).
The model never reads the ground truth.

## Survival analysis (time to churn)

- **Churn** means no session for 14 consecutive days. The churn day is the last
  active day before the gap. Users whose last activity is within 14 days of the end
  of observation are right-censored. Over 52,766 users there are 42,089 churn
  events.
- **Kaplan–Meier** curves by channel, platform and onboarding variant
  (`km_*.png`), with log-rank tests:
  - **Channel:** p ≈ 0. Survival to day 30 is 33.8 % for referral vs 14.9 % for
    paid social.
  - **Platform:** p = 2e-119 (iOS 27.4 % vs web 18.4 %).
  - **Onboarding variant:** p = 0.16, i.e. no difference, matching the planted
    "no retention effect".
- **Cox PH** (penalizer 0.01, concordance 0.834). Hazard ratios (< 1 = protective):
  - `reminder_set_any` **0.494** [0.483, 0.506]: the planted effect was
    exp(−0.70) = 0.497.
  - `workout_log_72h` **0.885** per log: the planted effect was exp(−0.10) = 0.905.
  - `active_days_72h` 0.448: this also absorbs latent engagement.
  - `onboarding_completed_72h` 0.755.
  - `sessions_72h` 1.01 (not significant once the others are included).

## Limitations

- The data is synthetic, and the true drivers were planted. The model's job here is
  to show that the pipeline can **find** real structure, not to claim real-world
  accuracy.
- Exact-day D30 is a noisy target: an engaged user can skip day 30. A window target
  (active on any of days 28–31) would raise PR-AUC. We keep the exact-day
  definition for consistency with every other D30 number in the project.
- The test period is only two weeks of signups. Seasonality and product changes
  would require periodic retraining (see the model card).

See also [MODEL_CARD.md](MODEL_CARD.md).

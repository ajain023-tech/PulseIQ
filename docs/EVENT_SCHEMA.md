# Event schema

PulseIQ simulates a **fitness / habit subscription app**. `pulseiq generate` writes
seven raw tables to `data/raw/*.parquet`. Timestamps are UTC and have no timezone.

## Raw tables

| Table | Grain | Columns |
|---|---|---|
| `users` | 1 row / user | `user_id`, `signup_ts`, `country`, `platform` (ios/android/web), `acquisition_channel` (organic/paid_social/search/referral/influencer), `device_tier` (low/mid/high), `app_version_at_signup` |
| `events` | 1 row / event | `event_id`, `user_id`, `session_id` (null for server events), `event_ts`, `event_name`, `properties` (JSON string), `platform`, `app_version` |
| `sessions` | 1 row / session | `session_id`, `user_id`, `session_start`, `session_end`, `n_events` |
| `experiment_assignments` | 1 row / user × experiment | `experiment_id`, `user_id`, `variant` (control/treatment), `assigned_at` |
| `subscriptions` | 1 row / trial or subscription | `subscription_id`, `user_id`, `plan` (monthly/annual), `price_usd`, `currency`, `started_at` (null if the trial didn't convert), `trial_started_at`, `canceled_at`, `status` (trialing/expired/active/canceled) |
| `invoices` | 1 row / charge or refund | `invoice_id`, `subscription_id`, `user_id`, `charged_at`, `amount_usd` (negative for refunds), `is_refund` |
| `experiments` | 1 row / experiment | `experiment_id`, `name`, `hypothesis`, `start_date`, `end_date` (exclusive), `population`, `primary_metric`, `guardrail_metrics`, `secondary_metrics`, `allocation` |

Countries and pricing tiers: **high** = US, UK, DE; **mid** = FR, CA, ES; **low** = IN, BR, ID.
`country_tier` is not stored raw. It is derived in `stg_users`.

## Event taxonomy

| Event | Where | Properties | Example `properties` |
|---|---|---|---|
| `app_install` | signup session | `source` | `{"source": "store"}` |
| `signup` | signup session | – | `{}` |
| `onboarding_step_viewed` | signup session | `step` 1–5 | `{"step": 2}` |
| `onboarding_step_completed` | signup session | `step` 1–5 | `{"step": 2}` |
| `onboarding_completed` | signup session | – | `{}` |
| `session_start` / `session_end` | every session | – | `{}` |
| `feature_used` | any session | `feature`: workout_log, plan_view, progress_chart, social_share, reminder_set | `{"feature": "workout_log"}` |
| `paywall_viewed` | after onboarding, on feature gates, in the paywall campaign | `source` (onboarding/feature_gate/campaign), `paywall_variant` (v1/v2) | `{"source": "campaign", "paywall_variant": "v2"}` |
| `trial_started` | in-session | `plan` | `{"plan": "annual"}` |
| `subscription_started` | server | `plan`, `price_usd` | `{"plan": "monthly", "price_usd": 9.99}` |
| `subscription_renewed` | server | `plan` | `{"plan": "monthly"}` |
| `subscription_canceled` | server | `reason`: too_expensive, not_using, found_alternative, technical_issues, other | `{"reason": "not_using"}` |
| `refund_issued` | server | `amount_usd` | `{"amount_usd": 3.99}` |
| `push_received` / `push_opened` | before a session (streak_reminder treatment) | `campaign` | `{"campaign": "streak_reminder"}` |

The signup session always begins with `app_install → session_start → signup` at
`signup_ts`. Then come the onboarding steps the user reached, `onboarding_completed`,
the onboarding paywall and, for about 60 % of trialists, `trial_started`. Other
sessions hold 2–15 events: `session_start`, 0–13 `feature_used` or `paywall_viewed`
events, and `session_end`.

## Known data-quality issues (planted on purpose)

| Issue | Rate | How the warehouse handles it |
|---|---|---|
| Exact duplicate event rows (same `event_id`) | ~0.3 % | `stg_events` keeps one row per `event_id` |
| Client clock skew (`event_ts` before signup) | ~0.2 % | `stg_events` drops them; test `assert_no_event_before_signup` |
| Null `platform` on events | ~0.05 % | `stg_events` fills it from the user's platform |
| Sessions that run past the end of the data | few | Events after `data_end` are not emitted |

The exact counts are recorded under `dirt` in `data/raw/ground_truth.json`.

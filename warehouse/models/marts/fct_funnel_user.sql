-- One row per user: ordered funnel stages Signup -> Onboarded -> Trial -> Paid.
-- A stage only counts if the previous stage happened first (as in v1 02_funnel.sql).
select
    d.user_id,
    d.signup_ts,
    d.signup_date,
    d.platform,
    d.acquisition_channel,
    d.country_tier,
    d.device_tier,
    d.onboarded_at,
    case when d.onboarded_at is not null and d.trial_at >= d.onboarded_at then d.trial_at end as trial_at,
    case
        when d.onboarded_at is not null and d.trial_at >= d.onboarded_at and d.paid_at >= d.trial_at
            then d.paid_at
    end as paid_at,
    1 as is_signed_up,
    case when d.onboarded_at is not null then 1 else 0 end as is_onboarded,
    case when d.onboarded_at is not null and d.trial_at >= d.onboarded_at then 1 else 0 end as is_trial,
    case
        when d.onboarded_at is not null and d.trial_at >= d.onboarded_at and d.paid_at >= d.trial_at
            then 1 else 0
    end as is_paid
from {{ ref('dim_users') }} as d

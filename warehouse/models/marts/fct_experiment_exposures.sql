-- One row per user x experiment: variant, segment dims, pre-period covariates and
-- every outcome metric the experimentation engine reads. This is the Phase 2
-- contract; every column is documented in schema.yml.
with w as (select data_end from {{ ref('int_data_window') }}),

a as (
    select
        a.experiment_id,
        a.user_id,
        a.variant,
        a.assigned_at,
        least(cast(e.end_date as timestamp), w.data_end) as test_end
    from {{ ref('stg_assignments') }} as a
    inner join {{ ref('stg_experiments') }} as e using (experiment_id)
    cross join w
),

sess as (
    select
        a.experiment_id,
        a.user_id,
        count(*) filter (
            where s.session_start >= a.assigned_at - interval 14 day and s.session_start < a.assigned_at
        ) as pre_sessions_14d,
        count(distinct s.session_date) filter (
            where s.session_start >= a.assigned_at - interval 14 day and s.session_start < a.assigned_at
        ) as pre_active_days_14d,
        count(*) filter (where s.session_start >= a.assigned_at and s.session_start < a.test_end) as sessions_in_test
    from a
    inner join {{ ref('stg_sessions') }} as s using (user_id)
    group by a.experiment_id, a.user_id
),

subs as (
    select
        a.experiment_id,
        a.user_id,
        max(case when s.trial_started_at >= a.assigned_at and s.trial_started_at < a.test_end then 1 else 0 end)
            as trial_started_in_test,
        max(case when s.started_at >= a.assigned_at and s.started_at < a.test_end then 1 else 0 end)
            as paid_in_test
    from a
    inner join {{ ref('stg_subscriptions') }} as s using (user_id)
    group by a.experiment_id, a.user_id
),

inv as (
    select
        a.experiment_id,
        a.user_id,
        sum(i.amount_usd) filter (where i.charged_at >= a.assigned_at and i.charged_at < a.test_end)
            as net_revenue_in_test,
        max(case when i.is_refund and i.charged_at >= a.assigned_at and i.charged_at < a.test_end then 1 else 0 end)
            as refund_in_test
    from a
    inner join {{ ref('stg_invoices') }} as i using (user_id)
    group by a.experiment_id, a.user_id
),

ret as (
    select
        user_id,
        max(case when day_n = 1 then 1 else 0 end) as d1_active,
        max(case when day_n = 7 then 1 else 0 end) as d7_active,
        max(case when day_n = 30 then 1 else 0 end) as d30_active
    from {{ ref('int_user_day_n_activity') }}
    where day_n in (1, 7, 30)
    group by user_id
)

select
    a.experiment_id,
    a.user_id,
    a.variant,
    a.assigned_at,
    a.test_end,
    u.signup_ts,
    a.assigned_at = u.signup_ts as assigned_at_signup,
    u.platform,
    u.acquisition_channel,
    u.country_tier,
    u.device_tier,
    coalesce(se.pre_sessions_14d, 0) as pre_sessions_14d,
    coalesce(se.pre_active_days_14d, 0) as pre_active_days_14d,
    -- new-user outcomes (relative to signup)
    case when u.onboarded_at is not null then 1 else 0 end as onboarding_completed,
    case when u.signup_ts + interval 14 day <= w.data_end then 1 else 0 end as trial_eligible,
    case when u.trial_at < u.signup_ts + interval 14 day then 1 else 0 end as trial_started_14d,
    case when u.signup_ts + interval 30 day <= w.data_end then 1 else 0 end as paid_eligible,
    case when u.paid_at < u.signup_ts + interval 30 day then 1 else 0 end as paid_30d,
    case when u.signup_ts + interval 2 day <= w.data_end then 1 else 0 end as d1_eligible,
    coalesce(r.d1_active, 0) as d1_retained,
    case when u.signup_ts + interval 8 day <= w.data_end then 1 else 0 end as d7_eligible,
    coalesce(r.d7_active, 0) as d7_retained,
    case when u.signup_ts + interval 31 day <= w.data_end then 1 else 0 end as d30_eligible,
    coalesce(r.d30_active, 0) as d30_retained,
    -- in-test outcomes (relative to assignment, until min(experiment end, data end))
    coalesce(su.trial_started_in_test, 0) as trial_started_in_test,
    coalesce(su.paid_in_test, 0) as paid_in_test,
    coalesce(i.refund_in_test, 0) as refund_in_test,
    coalesce(se.sessions_in_test, 0) as sessions_in_test,
    coalesce(i.net_revenue_in_test, 0) as net_revenue_in_test
from a
cross join w
inner join {{ ref('dim_users') }} as u using (user_id)
left join sess as se on se.experiment_id = a.experiment_id and se.user_id = a.user_id
left join subs as su on su.experiment_id = a.experiment_id and su.user_id = a.user_id
left join inv as i on i.experiment_id = a.experiment_id and i.user_id = a.user_id
left join ret as r on r.user_id = a.user_id

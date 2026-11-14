-- One row per user: dimensions plus lifecycle timestamps and lifetime totals.
with onboard as (
    select user_id, min(event_ts) as onboarded_at
    from {{ ref('stg_events') }}
    where event_name = 'onboarding_completed'
    group by user_id
),

subs as (
    select
        user_id,
        min(trial_started_at) as trial_at,
        min(started_at) as paid_at,
        max(case when status = 'active' then 1 else 0 end) as has_active_sub
    from {{ ref('stg_subscriptions') }}
    group by user_id
),

act as (
    select user_id, max(session_start) as last_active_at, count(*) as lifetime_sessions
    from {{ ref('stg_sessions') }}
    group by user_id
),

rev as (
    select user_id, sum(amount_usd) as lifetime_net_revenue_usd
    from {{ ref('stg_invoices') }}
    group by user_id
)

select
    u.user_id,
    u.signup_ts,
    u.signup_date,
    u.signup_week,
    u.signup_weekday,
    u.country,
    u.country_tier,
    u.platform,
    u.acquisition_channel,
    u.device_tier,
    u.app_version_at_signup,
    o.onboarded_at,
    s.trial_at,
    s.paid_at,
    a.last_active_at,
    coalesce(s.has_active_sub, 0) = 1 as is_paying,
    coalesce(a.lifetime_sessions, 0) as lifetime_sessions,
    coalesce(r.lifetime_net_revenue_usd, 0) as lifetime_net_revenue_usd
from {{ ref('stg_users') }} as u
left join onboard as o using (user_id)
left join subs as s using (user_id)
left join act as a using (user_id)
left join rev as r using (user_id)

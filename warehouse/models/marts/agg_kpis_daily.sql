-- One row per calendar date: engagement and conversion KPIs.
-- WAU / MAU are distinct users active in the trailing 7 / 30 days (inclusive).
with w as (select * from {{ ref('int_data_window') }}),

spine as (
    select cast(d as date) as kpi_date
    from w, range(cast(w.data_start as timestamp), w.data_end, interval 1 day) as t(d)
),

act as (select user_id, activity_date from {{ ref('int_user_daily_activity') }}),

rolling as (
    select
        s.kpi_date,
        count(distinct a.user_id) filter (where a.activity_date = s.kpi_date) as dau,
        count(distinct a.user_id) filter (where a.activity_date > s.kpi_date - 7) as wau,
        count(distinct a.user_id) as mau
    from spine as s
    inner join act as a
        on a.activity_date <= s.kpi_date and a.activity_date > s.kpi_date - 30
    group by s.kpi_date
),

new_users as (
    select signup_date as kpi_date, count(*) as new_users from {{ ref('stg_users') }} group by 1
),

conv as (
    select
        cast(event_ts as date) as kpi_date,
        count(*) filter (where event_name = 'onboarding_completed') as onboardings,
        count(*) filter (where event_name = 'trial_started') as trials_started,
        count(*) filter (where event_name = 'subscription_started') as paid_conversions
    from {{ ref('stg_events') }}
    group by 1
)

select
    s.kpi_date,
    coalesce(r.dau, 0) as dau,
    coalesce(r.wau, 0) as wau,
    coalesce(r.mau, 0) as mau,
    r.dau / nullif(r.mau, 0) as stickiness,
    coalesce(n.new_users, 0) as new_users,
    coalesce(c.onboardings, 0) as onboardings,
    coalesce(c.trials_started, 0) as trials_started,
    coalesce(c.paid_conversions, 0) as paid_conversions,
    coalesce(rev.net_revenue_usd, 0) as net_revenue_usd
from spine as s
left join rolling as r using (kpi_date)
left join new_users as n using (kpi_date)
left join conv as c using (kpi_date)
left join {{ ref('fct_revenue_daily') }} as rev on rev.revenue_date = s.kpi_date

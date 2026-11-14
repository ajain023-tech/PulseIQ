-- One row per calendar date: cash revenue, MRR and per-user revenue ratios.
-- MRR = sum of monthly-equivalent price (annual / 12) of paid periods covering the date.
with w as (select * from {{ ref('int_data_window') }}),

spine as (
    select cast(d as date) as revenue_date
    from w, range(cast(w.data_start as timestamp), w.data_end, interval 1 day) as t(d)
),

cash as (
    select
        charged_date as revenue_date,
        sum(gross_usd) as gross_revenue_usd,
        sum(refund_usd) as refunds_usd,
        count(*) filter (where not is_refund) as charges,
        count(*) filter (where is_refund) as refund_count
    from {{ ref('stg_invoices') }}
    group by charged_date
),

mrr as (
    select
        s.revenue_date,
        sum(p.monthly_value_usd) as mrr_usd,
        count(distinct p.subscription_id) as active_subscriptions
    from spine as s
    inner join {{ ref('int_subscription_periods') }} as p
        on p.period_start < cast(s.revenue_date as timestamp) + interval 1 day
        and p.period_end > cast(s.revenue_date as timestamp) + interval 1 day
    group by s.revenue_date
),

dau as (
    select activity_date as revenue_date, count(distinct user_id) as dau
    from {{ ref('int_user_daily_activity') }}
    group by activity_date
)

select
    s.revenue_date,
    coalesce(c.gross_revenue_usd, 0) as gross_revenue_usd,
    coalesce(c.refunds_usd, 0) as refunds_usd,
    coalesce(c.gross_revenue_usd, 0) - coalesce(c.refunds_usd, 0) as net_revenue_usd,
    coalesce(c.charges, 0) as charges,
    coalesce(c.refund_count, 0) as refund_count,
    coalesce(m.mrr_usd, 0) as mrr_usd,
    coalesce(m.active_subscriptions, 0) as active_subscriptions,
    coalesce(d.dau, 0) as dau,
    (coalesce(c.gross_revenue_usd, 0) - coalesce(c.refunds_usd, 0)) / nullif(d.dau, 0) as arpdau_usd,
    m.mrr_usd / nullif(m.active_subscriptions, 0) as arppu_monthly_usd
from spine as s
left join cash as c using (revenue_date)
left join mrr as m using (revenue_date)
left join dau as d using (revenue_date)

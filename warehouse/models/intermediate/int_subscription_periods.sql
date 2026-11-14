-- One row per paid billing period (each non-refund charge). A period covers
-- [period_start, period_end); it ends early at cancellation/refund.
with charges as (
    select
        i.invoice_id,
        i.subscription_id,
        i.user_id,
        i.charged_at as period_start,
        i.amount_usd,
        s.plan,
        s.monthly_value_usd,
        s.canceled_at
    from {{ ref('stg_invoices') }} as i
    inner join {{ ref('stg_subscriptions') }} as s using (subscription_id)
    where not i.is_refund
)

select
    invoice_id,
    subscription_id,
    user_id,
    plan,
    monthly_value_usd,
    period_start,
    least(
        period_start + case when plan = 'annual' then interval 365 day else interval 30 day end,
        coalesce(canceled_at, timestamp '9999-12-31')
    ) as period_end,
    amount_usd
from charges

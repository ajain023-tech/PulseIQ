-- One row per invoice (charge or refund). Refund amounts are negative.
select
    invoice_id,
    subscription_id,
    user_id,
    cast(charged_at as timestamp) as charged_at,
    cast(charged_at as date) as charged_date,
    cast(amount_usd as double) as amount_usd,
    is_refund,
    case when not is_refund then amount_usd else 0 end as gross_usd,
    case when is_refund then -amount_usd else 0 end as refund_usd
from {{ source('raw', 'invoices') }}

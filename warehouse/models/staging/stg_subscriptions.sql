-- One row per trial/subscription. started_at is null when the trial never converted.
select
    subscription_id,
    user_id,
    plan,
    cast(price_usd as double) as price_usd,
    currency,
    cast(trial_started_at as timestamp) as trial_started_at,
    cast(started_at as timestamp) as started_at,
    cast(canceled_at as timestamp) as canceled_at,
    status,
    case when plan = 'annual' then price_usd / 12.0 else price_usd end as monthly_value_usd
from {{ source('raw', 'subscriptions') }}

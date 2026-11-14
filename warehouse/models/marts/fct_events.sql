-- One row per cleaned event, enriched with user dimensions.
select
    e.event_id,
    e.user_id,
    e.session_id,
    e.event_ts,
    cast(e.event_ts as date) as event_date,
    e.day_n,
    e.event_name,
    e.feature,
    e.onboarding_step,
    e.paywall_source,
    e.paywall_variant,
    e.plan,
    e.cancel_reason,
    e.platform,
    e.app_version,
    u.signup_ts,
    u.country,
    u.country_tier,
    u.acquisition_channel,
    u.device_tier
from {{ ref('stg_events') }} as e
inner join {{ ref('stg_users') }} as u using (user_id)

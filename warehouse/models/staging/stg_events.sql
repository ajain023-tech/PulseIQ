-- One row per *unique, valid* event.
-- Cleaning: (1) exact duplicates removed by event_id, (2) client clock-skew rows
-- (event_ts before the user's signup) dropped, (3) null platform coalesced from
-- the user's signup platform. Properties JSON is parsed into typed columns.
with deduped as (
    select *
    from {{ source('raw', 'events') }}
    qualify row_number() over (partition by event_id order by event_ts) = 1
)

select
    e.event_id,
    e.user_id,
    e.session_id,
    cast(e.event_ts as timestamp) as event_ts,
    e.event_name,
    e.properties,
    coalesce(e.platform, u.platform) as platform,
    e.platform is null as platform_was_null,
    e.app_version,
    json_extract_string(e.properties, '$.feature') as feature,
    try_cast(json_extract_string(e.properties, '$.step') as integer) as onboarding_step,
    json_extract_string(e.properties, '$.source') as paywall_source,
    json_extract_string(e.properties, '$.paywall_variant') as paywall_variant,
    json_extract_string(e.properties, '$.plan') as plan,
    json_extract_string(e.properties, '$.reason') as cancel_reason,
    date_diff('second', u.signup_ts, cast(e.event_ts as timestamp)) // 86400 as day_n
from deduped as e
inner join {{ ref('stg_users') }} as u using (user_id)
where cast(e.event_ts as timestamp) >= u.signup_ts

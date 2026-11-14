-- One row per user: typed dimensions plus derived country tier.
select
    user_id,
    cast(signup_ts as timestamp) as signup_ts,
    cast(signup_ts as date) as signup_date,
    cast(date_trunc('week', signup_ts) as date) as signup_week,
    country,
    case
        when country in ('US', 'UK', 'DE') then 'high'
        when country in ('FR', 'CA', 'ES') then 'mid'
        else 'low'
    end as country_tier,
    platform,
    acquisition_channel,
    device_tier,
    app_version_at_signup,
    dayname(signup_ts) as signup_weekday
from {{ source('raw', 'users') }}

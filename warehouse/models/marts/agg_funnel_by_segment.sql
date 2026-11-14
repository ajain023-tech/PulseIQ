-- One row per segment type x segment value: ordered funnel counts and step rates.
{% set segments = ['acquisition_channel', 'platform', 'country_tier', 'device_tier'] %}
with unioned as (
    {% for seg in segments %}
    select '{{ seg }}' as segment_type, {{ seg }} as segment_value, is_onboarded, is_trial, is_paid
    from {{ ref('fct_funnel_user') }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select
    segment_type,
    segment_value,
    count(*) as signups,
    sum(is_onboarded) as onboarded,
    sum(is_trial) as trials,
    sum(is_paid) as paid,
    sum(is_onboarded) / count(*) as onboarding_rate,
    sum(is_trial) / nullif(sum(is_onboarded), 0) as onboarded_to_trial_rate,
    sum(is_paid) / nullif(sum(is_trial), 0) as trial_to_paid_rate,
    sum(is_paid) / count(*) as signup_to_paid_rate
from unioned
group by segment_type, segment_value

-- One row per signup date: funnel stage counts for that day's signup cohort.
select
    signup_date,
    count(*) as signups,
    sum(is_onboarded) as onboarded,
    sum(is_trial) as trials,
    sum(is_paid) as paid,
    sum(is_onboarded) / count(*) as onboarding_rate,
    sum(is_trial) / nullif(sum(is_onboarded), 0) as onboarded_to_trial_rate,
    sum(is_paid) / nullif(sum(is_trial), 0) as trial_to_paid_rate,
    sum(is_paid) / count(*) as signup_to_paid_rate
from {{ ref('fct_funnel_user') }}
group by signup_date

-- paid ⊆ trial ⊆ onboarded ⊆ signed up, per user and in aggregate.
select user_id
from {{ ref('fct_funnel_user') }}
where is_paid > is_trial or is_trial > is_onboarded or is_onboarded > is_signed_up

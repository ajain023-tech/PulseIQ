-- One row per user x onboarding step (1-5): viewed / completed flags.
with steps as (select unnest(range(1, 6)) as step),

ev as (
    select user_id, onboarding_step as step, event_name
    from {{ ref('stg_events') }}
    where event_name in ('onboarding_step_viewed', 'onboarding_step_completed')
)

select
    u.user_id,
    s.step,
    coalesce(max(case when ev.event_name = 'onboarding_step_viewed' then 1 end), 0) as viewed,
    coalesce(max(case when ev.event_name = 'onboarding_step_completed' then 1 end), 0) as completed
from {{ ref('stg_users') }} as u
cross join steps as s
left join ev on ev.user_id = u.user_id and ev.step = s.step
group by u.user_id, s.step

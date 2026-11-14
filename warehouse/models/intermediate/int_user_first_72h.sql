-- One row per user: behaviour in the first 72 h after signup (feature-ready).
-- Only events with event_ts < signup_ts + 72h are used, so nothing here can leak
-- information from later in the lifecycle.
with ev as (
    select e.*
    from {{ ref('stg_events') }} as e
    inner join {{ ref('stg_users') }} as u using (user_id)
    where e.event_ts < u.signup_ts + interval 72 hour
),

per_user as (
    select
        user_id,
        count(*) filter (where event_name = 'session_start') as sessions_72h,
        count(distinct day_n) filter (where event_name = 'session_start') as active_days_72h,
        count(*) filter (where event_name not in ('session_start', 'session_end')) as total_events_72h,
        count(distinct feature) as distinct_features_72h,
        count(*) filter (where feature = 'workout_log') as workout_log_72h,
        count(*) filter (where feature = 'plan_view') as plan_view_72h,
        count(*) filter (where feature = 'progress_chart') as progress_chart_72h,
        count(*) filter (where feature = 'social_share') as social_share_72h,
        count(*) filter (where feature = 'reminder_set') as reminder_set_72h,
        count(distinct onboarding_step) filter (where event_name = 'onboarding_step_completed') as onboarding_steps_completed,
        max(case when event_name = 'onboarding_completed' then 1 else 0 end) as onboarding_completed_72h,
        count(*) filter (where event_name = 'paywall_viewed') as paywall_views_72h,
        max(case when event_name = 'trial_started' then 1 else 0 end) as trial_started_72h,
        count(*) filter (where event_name = 'push_opened') as push_opens_72h,
        min(event_ts) filter (where feature = 'workout_log') as first_workout_ts
    from ev
    group by user_id
)

select
    u.user_id,
    u.signup_ts,
    coalesce(p.sessions_72h, 0) as sessions_72h,
    coalesce(p.active_days_72h, 0) as active_days_72h,
    coalesce(p.total_events_72h, 0) as total_events_72h,
    coalesce(p.distinct_features_72h, 0) as distinct_features_72h,
    coalesce(p.workout_log_72h, 0) as workout_log_72h,
    coalesce(p.plan_view_72h, 0) as plan_view_72h,
    coalesce(p.progress_chart_72h, 0) as progress_chart_72h,
    coalesce(p.social_share_72h, 0) as social_share_72h,
    coalesce(p.reminder_set_72h, 0) as reminder_set_72h,
    coalesce(p.onboarding_steps_completed, 0) as onboarding_steps_completed,
    coalesce(p.onboarding_completed_72h, 0) as onboarding_completed_72h,
    coalesce(p.paywall_views_72h, 0) as paywall_views_72h,
    coalesce(p.trial_started_72h, 0) as trial_started_72h,
    coalesce(p.push_opens_72h, 0) as push_opens_72h,
    -- minutes from signup to the first workout_log; 4320 (= 72 h) when none happened
    coalesce(date_diff('second', u.signup_ts, p.first_workout_ts) / 60.0, 4320.0) as minutes_to_first_workout
from {{ ref('stg_users') }} as u
left join per_user as p using (user_id)

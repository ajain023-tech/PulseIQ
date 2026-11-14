-- One row per user per calendar date with at least one session.
select
    user_id,
    session_date as activity_date,
    min(day_n) as day_n,
    count(*) as sessions,
    sum(n_events) as events
from {{ ref('stg_sessions') }}
group by user_id, session_date

-- One row per session with duration and day-N block relative to signup.
select
    s.session_id,
    s.user_id,
    cast(s.session_start as timestamp) as session_start,
    cast(s.session_end as timestamp) as session_end,
    date_diff('second', cast(s.session_start as timestamp), cast(s.session_end as timestamp)) as duration_seconds,
    s.n_events,
    cast(s.session_start as date) as session_date,
    date_diff('second', u.signup_ts, cast(s.session_start as timestamp)) // 86400 as day_n
from {{ source('raw', 'sessions') }} as s
inner join {{ ref('stg_users') }} as u using (user_id)

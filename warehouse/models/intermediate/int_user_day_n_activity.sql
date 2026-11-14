-- One row per user per day-N block (24 h windows after signup) with a session.
-- This is the basis of exact-day (D1/D7/D30) retention.
select
    user_id,
    day_n,
    count(*) as sessions
from {{ ref('stg_sessions') }}
group by user_id, day_n

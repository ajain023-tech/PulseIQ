-- Cleaned events must never precede the user's signup (clock skew is removed in staging).
select event_id, user_id, event_ts, signup_ts
from {{ ref('fct_events') }}
where event_ts < signup_ts

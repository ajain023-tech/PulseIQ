-- Single row: the observation window of the dataset. data_end is exclusive and is
-- derived from the data itself (midnight after the last raw event).
select
    min(u.signup_date) as data_start,
    cast(date_trunc('day', (select max(event_ts) from {{ source('raw', 'events') }})) + interval 1 day as timestamp) as data_end
from {{ ref('stg_users') }} as u

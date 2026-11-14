-- One row per weekly signup cohort x day N (N in 1, 3, 7, 14, 30).
-- Eligibility-aware: a user is in the day-N denominator only if their whole day-N
-- block (signup + (N+1) days) lies inside the observation window.
with days as (select unnest([1, 3, 7, 14, 30]) as day_n),

w as (select data_end from {{ ref('int_data_window') }}),

base as (
    select
        u.user_id,
        u.signup_week as cohort_week,
        d.day_n,
        u.signup_ts + to_days(d.day_n + 1) <= w.data_end as is_eligible
    from {{ ref('stg_users') }} as u
    cross join days as d
    cross join w
)

select
    b.cohort_week,
    b.day_n,
    count(*) as cohort_size,
    count(*) filter (where b.is_eligible) as eligible_users,
    count(*) filter (where b.is_eligible and a.user_id is not null) as retained_users,
    (count(*) filter (where b.is_eligible and a.user_id is not null))
        / nullif(count(*) filter (where b.is_eligible), 0) as retention_rate,
    count(*) filter (where b.is_eligible) = count(*) as is_mature
from base as b
left join {{ ref('int_user_day_n_activity') }} as a
    on a.user_id = b.user_id and a.day_n = b.day_n
group by b.cohort_week, b.day_n

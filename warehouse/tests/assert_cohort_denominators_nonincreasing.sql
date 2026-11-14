-- Within a cohort, the eligible denominator can only shrink as N grows.
select cohort_week, day_n, eligible_users, prev_eligible
from (
    select
        cohort_week,
        day_n,
        eligible_users,
        lag(eligible_users) over (partition by cohort_week order by day_n) as prev_eligible
    from {{ ref('agg_retention_cohorts') }}
)
where prev_eligible is not null and eligible_users > prev_eligible

-- Retention rates must lie in [0, 1] and retained users can't exceed eligible users.
select cohort_week, day_n
from {{ ref('agg_retention_cohorts') }}
where retention_rate < 0 or retention_rate > 1 or retained_users > eligible_users

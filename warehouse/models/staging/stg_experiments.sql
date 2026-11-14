-- One row per experiment with metric lists split into arrays.
select
    experiment_id,
    name,
    hypothesis,
    cast(start_date as date) as start_date,
    cast(end_date as date) as end_date,
    population,
    primary_metric,
    string_split(guardrail_metrics, ',') as guardrail_metrics,
    string_split(secondary_metrics, ',') as secondary_metrics,
    allocation
from {{ source('raw', 'experiments') }}

-- One row per user x experiment assignment.
select
    experiment_id,
    user_id,
    variant,
    cast(assigned_at as timestamp) as assigned_at
from {{ source('raw', 'experiment_assignments') }}

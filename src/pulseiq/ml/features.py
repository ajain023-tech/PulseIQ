"""Leakage-free feature matrix for D30-retention prediction.

Every behavioural feature comes from ``int_user_first_72h`` (events with
``event_ts < signup_ts + 72h``); the rest are signup-time dimensions. Nothing
observed after 72 h - paid conversion, D7 activity, later sessions - is used.
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

NUMERIC_FEATURES = (
    "sessions_72h",
    "active_days_72h",
    "total_events_72h",
    "distinct_features_72h",
    "workout_log_72h",
    "plan_view_72h",
    "progress_chart_72h",
    "social_share_72h",
    "reminder_set_72h",
    "onboarding_steps_completed",
    "onboarding_completed_72h",
    "paywall_views_72h",
    "trial_started_72h",
    "push_opens_72h",
    "minutes_to_first_workout",
)
CATEGORICAL_FEATURES = (
    "platform",
    "acquisition_channel",
    "country_tier",
    "device_tier",
    "signup_weekday",
)
TARGET = "d30_retained"
TARGET_DEFINITION = (
    "d30_retained = 1 if the user started a session in the day-30 block "
    "[signup_ts + 30 d, signup_ts + 31 d) - the same exact-day definition used by the "
    "warehouse, dashboards and experiments. Population: users with signup_ts + 31 d <= data_end."
)

_SQL = """
with w as (select data_end from int_data_window)
select
    f.user_id,
    u.signup_ts,
    {numeric},
    {categorical},
    case when u.signup_ts + interval 31 day <= w.data_end then 1 else 0 end as d30_eligible,
    case when a.user_id is not null then 1 else 0 end as d30_retained
from int_user_first_72h as f
inner join dim_users as u using (user_id)
cross join w
left join int_user_day_n_activity as a on a.user_id = f.user_id and a.day_n = 30
{where}
order by u.signup_ts, f.user_id
"""


def load_feature_frame(
    con: duckdb.DuckDBPyConnection, user_ids: list[str] | None = None, eligible_only: bool = True
) -> pd.DataFrame:
    """Raw features + target for (optionally) a subset of users."""
    clauses = []
    params: list = []
    if eligible_only:
        clauses.append("u.signup_ts + interval 31 day <= w.data_end")
    if user_ids is not None:
        clauses.append("f.user_id in (select unnest(?))")
        params.append(list(user_ids))
    where = ("where " + " and ".join(clauses)) if clauses else ""
    sql = _SQL.format(
        numeric=", ".join(f"f.{c}" for c in NUMERIC_FEATURES),
        categorical=", ".join(f"u.{c}" for c in CATEGORICAL_FEATURES),
        where=where,
    )
    return con.execute(sql, params).df()


def to_matrix(frame: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """Numeric features + one-hot dims. Pass ``columns`` to align with a trained model."""
    num = frame[list(NUMERIC_FEATURES)].astype(float)
    num["reminder_set_any_72h"] = (frame["reminder_set_72h"] > 0).astype(float)
    cat = pd.get_dummies(
        frame[list(CATEGORICAL_FEATURES)].astype(str),
        prefix=list(CATEGORICAL_FEATURES),
        dtype=float,
    )
    X = pd.concat([num, cat], axis=1)
    if columns is not None:
        X = X.reindex(columns=columns, fill_value=0.0)
    return X.astype(np.float64)

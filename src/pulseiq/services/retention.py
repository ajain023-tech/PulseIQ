"""Eligibility-aware cohort retention, retention curves and survival summaries."""

from __future__ import annotations

import json

import pandas as pd

from pulseiq.config import get_settings

from .db import cached, query
from .filters import Filters
from .funnel import SEGMENTS
from .kpis import _resolve

DAYS = (1, 3, 7, 14, 30)


@cached
def cohort_matrix(f: Filters | None = None) -> pd.DataFrame:
    """Weekly signup cohort x day N. Immature cells have retention = NaN (not zero)."""
    f = _resolve(f)
    uc, up = f.user_clause("u")
    return query(
        f"""with w as (select data_end from int_data_window),
            days as (select unnest({list(DAYS)}) as day_n),
            base as (
                select u.user_id, u.signup_week, d.day_n,
                       u.signup_ts + to_days(d.day_n + 1) <= w.data_end as eligible
                from dim_users u cross join days d cross join w
                where {uc} and u.signup_date between ? and ?)
            select b.signup_week as cohort_week, b.day_n, count(*) as cohort_size,
                   count(*) filter (where eligible) as eligible_users,
                   count(*) filter (where eligible and a.user_id is not null) as retained_users,
                   (count(*) filter (where eligible and a.user_id is not null))
                     / nullif(count(*) filter (where eligible), 0) as retention_rate
            from base b left join int_user_day_n_activity a on a.user_id = b.user_id and a.day_n = b.day_n
            group by 1, 2 order by 1, 2""",
        [*up, f.start, f.end],
    )


@cached
def retention_curve(
    f: Filters | None = None, by: str | None = None, max_day: int = 30
) -> pd.DataFrame:
    """Exact-day retention for day 0..max_day (eligible users only), optionally by segment."""
    f = _resolve(f)
    uc, up = f.user_clause("u")
    seg = f"u.{SEGMENTS[by]}" if by else "'all'"
    return query(
        f"""with w as (select data_end from int_data_window),
            days as (select unnest(range(0, {max_day + 1})) as day_n),
            base as (select u.user_id, {seg} as segment, d.day_n from dim_users u cross join days d cross join w
                     where {uc} and u.signup_date between ? and ?
                       and u.signup_ts + to_days(d.day_n + 1) <= w.data_end)
            select segment, b.day_n, count(*) as eligible_users, count(a.user_id) as retained_users,
                   count(a.user_id) / count(*) as retention_rate
            from base b left join int_user_day_n_activity a on a.user_id = b.user_id and a.day_n = b.day_n
            group by 1, 2 order by 1, 2""",
        [*up, f.start, f.end],
    )


def survival_summary() -> dict | None:
    """Kaplan-Meier / Cox results produced by ``pulseiq survival`` (None if absent)."""
    path = get_settings().artifacts_dir / "ml" / "survival.json"
    return json.loads(path.read_text()) if path.exists() else None

"""Headline KPIs with period-over-period deltas, and the DAU trend."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
from pydantic import BaseModel

from .db import cached, query
from .filters import Filters
from .meta import data_window


class KPI(BaseModel):
    """One headline number with its previous-period value and delta."""

    name: str
    value: float | None
    previous: float | None
    delta: float | None
    unit: str  # count | ratio | usd
    definition: str


class KPISummary(BaseModel):
    """All headline KPIs for a filter set."""

    start: str
    end: str
    kpis: list[KPI]


def default_filters() -> Filters:
    """Last 28 days of available data, all segments."""
    _, last = data_window()
    return Filters(last - timedelta(days=27), last)


def _resolve(f: Filters | None) -> Filters:
    """Fill missing dates: no dates -> last 28 days; one date -> the data bound for the other."""
    if f is None:
        return default_filters()
    first, last = data_window()
    if f.start is None and f.end is None:
        d = default_filters()
        return f.with_dates(d.start, d.end)
    return f.with_dates(f.start or first, f.end or last)


def _period_values(f: Filters) -> dict:
    uc, up = f.user_clause("u")
    dau = query(
        f"""select a.activity_date, count(distinct a.user_id) as dau
            from int_user_daily_activity a join dim_users u using (user_id)
            where {uc} and a.activity_date between ? and ? group by 1""",
        [*up, f.start, f.end],
    )
    mau = query(
        f"""select count(distinct a.user_id) from int_user_daily_activity a join dim_users u using (user_id)
            where {uc} and a.activity_date between ? and ?""",
        [*up, f.end - timedelta(days=29), f.end],
    ).iloc[0, 0]
    funnel = query(
        f"""with w as (select data_end from int_data_window)
            select count(*) as signups,
                   avg(is_trial) filter (where u.signup_ts + interval 14 day <= w.data_end) as trial_rate
            from fct_funnel_user u cross join w
            where {uc} and u.signup_date between ? and ?""",
        [*up, f.start, f.end],
    ).iloc[0]
    paid = query(
        f"""select avg(case when s.started_at is not null then 1 else 0 end)
            from stg_subscriptions s join dim_users u using (user_id)
            where {uc} and cast(s.trial_started_at + interval 7 day as date) between ? and ?""",
        [*up, f.start, f.end],
    ).iloc[0, 0]
    rev = query(
        f"""select coalesce(sum(i.amount_usd), 0) from stg_invoices i join dim_users u using (user_id)
            where {uc} and i.charged_date between ? and ?""",
        [*up, f.start, f.end],
    ).iloc[0, 0]
    days = (f.end - f.start).days + 1
    avg_dau = float(dau["dau"].sum() / days) if days else None
    return {
        "dau": avg_dau,
        "mau": float(mau),
        "stickiness": (avg_dau / mau) if mau else None,
        "new_users": float(funnel["signups"]),
        "trial_conversion": None if pd.isna(funnel["trial_rate"]) else float(funnel["trial_rate"]),
        "paid_conversion": None if pd.isna(paid) else float(paid),
        "net_revenue": float(rev),
    }


DEFS = {
    "dau": ("Avg DAU", "count", "average daily active users over the period"),
    "mau": ("MAU", "count", "distinct users active in the 30 days ending on the period end"),
    "stickiness": ("Stickiness", "ratio", "average DAU / MAU"),
    "new_users": ("New users", "count", "signups in the period"),
    "trial_conversion": (
        "Trial conversion",
        "ratio",
        "share of the period's signups who started a trial after onboarding (cohorts with 14 d observed)",
    ),
    "paid_conversion": (
        "Trial → paid",
        "ratio",
        "share of trials ending in the period that converted to a paid subscription",
    ),
    "net_revenue": ("Net revenue", "usd", "charges minus refunds in the period"),
}


@cached
def kpi_summary(f: Filters | None = None) -> KPISummary:
    """Headline KPIs for the period plus deltas vs the previous period of equal length."""
    f = _resolve(f)
    cur = _period_values(f)
    prev_f = f.previous()
    first, _ = data_window()
    prev = _period_values(prev_f) if prev_f and prev_f.start >= first else {}
    kpis = []
    for key, (label, unit, definition) in DEFS.items():
        v, p = cur.get(key), prev.get(key)
        delta = (v - p) / p if (v is not None and p not in (None, 0)) else None
        if unit == "ratio" and v is not None and p is not None:
            delta = v - p  # absolute change for ratios
        kpis.append(
            KPI(name=label, value=v, previous=p, delta=delta, unit=unit, definition=definition)
        )
    return KPISummary(start=str(f.start), end=str(f.end), kpis=kpis)


@cached
def dau_trend(f: Filters | None = None) -> pd.DataFrame:
    """Daily DAU, WAU-style 7-day average and new users for the filters."""
    f = _resolve(f)
    uc, up = f.user_clause("u")
    df = query(
        f"""with days as (select cast(d as date) as day from range(cast(? as timestamp), cast(? as timestamp) + interval 1 day, interval 1 day) t(d)),
            act as (select a.activity_date as day, count(distinct a.user_id) as dau
                    from int_user_daily_activity a join dim_users u using (user_id) where {uc} group by 1),
            new as (select u.signup_date as day, count(*) as new_users from dim_users u where {uc} group by 1)
            select days.day, coalesce(act.dau, 0) as dau, coalesce(new.new_users, 0) as new_users
            from days left join act using (day) left join new using (day) order by day""",
        [f.start, f.end, *up, *up],
    )
    df["dau_7d_avg"] = df["dau"].rolling(7, min_periods=1).mean()
    return df

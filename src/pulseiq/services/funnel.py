"""Ordered funnel overall, by segment, and onboarding step drop-off."""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel

from .db import cached, query
from .filters import Filters
from .kpis import _resolve

STAGES = ("Signed up", "Onboarded", "Trial", "Paid")
SEGMENTS = {
    "channel": "acquisition_channel",
    "platform": "platform",
    "country_tier": "country_tier",
    "device_tier": "device_tier",
}


class FunnelStage(BaseModel):
    """One funnel stage."""

    stage: str
    users: int
    step_conversion: float | None
    overall_conversion: float


class Funnel(BaseModel):
    """Funnel with the biggest drop called out."""

    start: str
    end: str
    stages: list[FunnelStage]
    biggest_drop: str | None
    segments: list[dict] = []


@cached
def funnel(f: Filters | None = None, by: str | None = None) -> Funnel:
    """Signup-cohort funnel for signups in the date range (optionally split by segment)."""
    f = _resolve(f)
    uc, up = f.user_clause("u")
    row = query(
        f"""select count(*), sum(is_onboarded), sum(is_trial), sum(is_paid) from fct_funnel_user u
            where {uc} and signup_date between ? and ?""",
        [*up, f.start, f.end],
    ).iloc[0]
    counts = [0 if pd.isna(x) else int(x) for x in row]
    stages, drops = [], []
    for i, (name, n) in enumerate(zip(STAGES, counts, strict=True)):
        step = None if i == 0 else (n / counts[i - 1] if counts[i - 1] else None)
        if step is not None:
            drops.append((1 - step, f"{STAGES[i - 1]} → {name}"))
        stages.append(
            FunnelStage(
                stage=name,
                users=n,
                step_conversion=step,
                overall_conversion=n / counts[0] if counts[0] else 0.0,
            )
        )
    biggest = None
    if drops:
        lost, label = max(drops)
        biggest = f"{label}: {lost:.1%} of users drop at this step"
    segs = []
    if by:
        if by not in SEGMENTS:
            raise ValueError(f"by must be one of {sorted(SEGMENTS)}")
        col = SEGMENTS[by]
        seg = query(
            f"""select {col} as segment, count(*) as signups, sum(is_onboarded) as onboarded,
                       sum(is_trial) as trials, sum(is_paid) as paid
                from fct_funnel_user u where {uc} and signup_date between ? and ? group by 1 order by 1""",
            [*up, f.start, f.end],
        )
        seg["onboarding_rate"] = seg["onboarded"] / seg["signups"]
        seg["trial_rate"] = seg["trials"] / seg["onboarded"].where(seg["onboarded"] > 0)
        seg["paid_rate"] = seg["paid"] / seg["trials"].where(seg["trials"] > 0)
        seg["signup_to_paid"] = seg["paid"] / seg["signups"]
        segs = seg.to_dict(orient="records")
    return Funnel(
        start=str(f.start), end=str(f.end), stages=stages, biggest_drop=biggest, segments=segs
    )


@cached
def onboarding_steps(f: Filters | None = None) -> pd.DataFrame:
    """Per onboarding step: users who viewed / completed it, and step drop-off."""
    f = _resolve(f)
    uc, up = f.user_clause("u")
    df = query(
        f"""select s.step, sum(s.viewed) as viewed, sum(s.completed) as completed
            from int_onboarding_steps s join dim_users u using (user_id)
            where {uc} and u.signup_date between ? and ? group by 1 order by 1""",
        [*up, f.start, f.end],
    )
    df["completion_rate"] = df["completed"] / df["viewed"].where(df["viewed"] > 0)
    return df

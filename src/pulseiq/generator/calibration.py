"""Headline rates computed directly from generated tables (pandas, no warehouse).

Used for calibration against the legacy dataset and as an independent cross-check
of the dbt marts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TARGETS = {
    "onboarding_rate": 0.55,
    "trial_rate": 0.16,
    "paid_rate": 0.10,
    "d1_retention": 0.40,
    "d7_retention": 0.20,
    "d30_retention": 0.15,
}


def headline_rates(tables: dict[str, pd.DataFrame], data_end: pd.Timestamp) -> dict[str, float]:
    """Onboarding / trial / paid share of signups and exact-day D1/D7/D30 retention."""
    users = tables["users"][["user_id", "signup_ts"]]
    ev = tables["events"]
    onboarded = set(ev.loc[ev["event_name"] == "onboarding_completed", "user_id"])
    subs = tables["subscriptions"].merge(users, on="user_id")
    trial14 = subs["trial_started_at"] < subs["signup_ts"] + pd.Timedelta(days=14)
    paid30 = subs["started_at"].notna() & (
        subs["started_at"] < subs["signup_ts"] + pd.Timedelta(days=30)
    )
    trial_eligible = users["signup_ts"] + pd.Timedelta(days=14) <= data_end
    paid_eligible = users["signup_ts"] + pd.Timedelta(days=30) <= data_end
    trial_users = set(subs.loc[trial14, "user_id"])
    paid_users = set(subs.loc[paid30, "user_id"])

    out = {
        "onboarding_rate": float(users["user_id"].isin(onboarded).mean()),
        "trial_rate": float(users.loc[trial_eligible, "user_id"].isin(trial_users).mean()),
        "paid_rate": float(users.loc[paid_eligible, "user_id"].isin(paid_users).mean()),
    }
    sess = tables["sessions"].merge(users, on="user_id")
    block = (sess["session_start"] - sess["signup_ts"]) // pd.Timedelta(days=1)
    for n in (1, 7, 30):
        eligible = users["signup_ts"] + pd.Timedelta(days=n + 1) <= data_end
        active = set(sess.loc[block == n, "user_id"])
        out[f"d{n}_retention"] = float(users.loc[eligible, "user_id"].isin(active).mean())
    return out


def legacy_rates(legacy: pd.DataFrame) -> dict[str, float]:
    """Comparable headline rates from the v1 user-level CSV (eligibility-aware)."""

    def rate(flag: str, elig: str | None) -> float:
        frame = legacy if elig is None else legacy[legacy[elig] == 1]
        return float(np.mean(frame[flag]))

    return {
        "onboarding_rate": rate("onboarding_completed", None),
        "trial_rate": float(np.mean(legacy["trial_started"])),
        "paid_rate": float(np.mean(legacy["paid_conversion"])),
        "d1_retention": rate("d1_retained", "d1_eligible"),
        "d7_retention": rate("d7_retained", "d7_eligible"),
        "d30_retention": rate("d30_retained", "d30_eligible"),
    }

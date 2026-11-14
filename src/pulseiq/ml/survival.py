"""Survival analysis of time-to-churn: Kaplan-Meier, log-rank tests and Cox PH.

Churn = no session for 14 consecutive days. A user's churn day is their last active
day before the first such gap. Users whose last activity is within 14 days of the end
of observation are right-censored at their observed horizon.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

CHURN_GAP_DAYS = 14
COLORS = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9"]

_SQL = """
with w as (select data_end from int_data_window),
days as (
    select a.user_id, a.day_n,
           lead(a.day_n) over (partition by a.user_id order by a.day_n) as next_day
    from int_user_day_n_activity a
),
gaps as (
    select user_id, min(day_n) filter (where next_day - day_n > {gap}) as churn_day,
           max(day_n) as last_day
    from days group by user_id
)
select
    u.user_id, u.platform, u.acquisition_channel, u.country_tier, u.device_tier,
    date_diff('second', u.signup_ts, w.data_end) // 86400 as horizon,
    g.churn_day, g.last_day,
    f.reminder_set_72h, f.workout_log_72h, f.active_days_72h, f.sessions_72h, f.onboarding_completed_72h,
    x.variant as onboarding_variant
from dim_users u
cross join w
inner join gaps g using (user_id)
inner join int_user_first_72h f using (user_id)
left join fct_experiment_exposures x on x.user_id = u.user_id and x.experiment_id = 'onboarding_flow_v2'
"""


def churn_durations(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """One row per user: duration (days) and event flag (1 = churned, 0 = censored)."""
    df = con.execute(_SQL.format(gap=CHURN_GAP_DAYS)).df()
    churned_gap = df["churn_day"].notna()
    churned_tail = ~churned_gap & (df["horizon"] - df["last_day"] > CHURN_GAP_DAYS)
    df["event"] = (churned_gap | churned_tail).astype(int)
    df["duration"] = np.where(
        churned_gap, df["churn_day"], np.where(churned_tail, df["last_day"], df["horizon"])
    )
    df["duration"] = df["duration"].astype(float) + 1.0  # day 0 activity = survived 1 day
    return df[df["horizon"] > CHURN_GAP_DAYS].reset_index(drop=True)


def kaplan_meier(durations: pd.DataFrame, by: str, out: Path) -> dict:
    """KM curves per group with a multivariate log-rank test; saves a PNG."""
    from lifelines import KaplanMeierFitter
    from lifelines.statistics import multivariate_logrank_test

    d = durations.dropna(subset=[by])
    fig, ax = plt.subplots(figsize=(7, 4.2))
    medians, s30 = {}, {}
    for (name, g), color in zip(d.groupby(by), COLORS, strict=False):
        km = KaplanMeierFitter().fit(g["duration"], g["event"], label=f"{name} (n={len(g):,})")
        km.plot_survival_function(ax=ax, ci_show=True, color=color, lw=1.6)
        medians[str(name)] = float(km.median_survival_time_)
        s30[str(name)] = float(km.survival_function_at_times(30).iloc[0])
    test = multivariate_logrank_test(d["duration"], d[by], d["event"])
    ax.set(
        xlabel="Days since signup",
        ylabel="P(not yet churned)",
        title=f"Kaplan-Meier by {by} — log-rank p = {test.p_value:.2g}",
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=7)
    fig.tight_layout()
    path = out / f"km_{by}.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return {
        "by": by,
        "logrank_chi2": float(test.test_statistic),
        "logrank_p": float(test.p_value),
        "median_days": medians,
        "survival_at_30d": s30,
        "chart": str(path),
    }


COX_FEATURES = (
    "reminder_set_any",
    "workout_log_72h",
    "active_days_72h",
    "sessions_72h",
    "onboarding_completed_72h",
)


def cox_model(durations: pd.DataFrame) -> list[dict]:
    """Cox proportional-hazards model on key 72 h features; returns hazard ratios."""
    from lifelines import CoxPHFitter

    d = durations.assign(reminder_set_any=(durations["reminder_set_72h"] > 0).astype(int))
    data = d[list(COX_FEATURES) + ["duration", "event"]].astype(float)
    cph = CoxPHFitter(penalizer=0.01).fit(data, duration_col="duration", event_col="event")
    s = cph.summary
    return [
        {
            "feature": f,
            "hazard_ratio": float(s.loc[f, "exp(coef)"]),
            "ci_low": float(s.loc[f, "exp(coef) lower 95%"]),
            "ci_high": float(s.loc[f, "exp(coef) upper 95%"]),
            "p_value": float(s.loc[f, "p"]),
        }
        for f in COX_FEATURES
    ] + [{"feature": "_concordance", "hazard_ratio": float(cph.concordance_index_)}]

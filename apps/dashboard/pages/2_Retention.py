"""Retention: cohort heatmap (immature cells blank), curves by segment, Kaplan-Meier."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from components.filters import sidebar_filters
from components.theme import chart, empty_state, pct, setup

setup("Retention", "🔁")
from pulseiq.services import retention  # noqa: E402

f = sidebar_filters()
st.title("Retention")
st.caption(
    "Exact-day retention: a session in the day-N block after signup, among users whose day-N block is fully observed."
)
st.info(
    "Tip: retention needs time to mature — widen the date range (e.g. the whole data window) to see D14/D30.",
    icon="💡",
)

cm = retention.cohort_matrix(f)
if cm.empty:
    empty_state()
    st.stop()
pivot = cm.pivot(index="cohort_week", columns="day_n", values="retention_rate")
pivot.index = pd.to_datetime(pivot.index).strftime("%Y-%m-%d")
pivot.columns = [f"D{c}" for c in pivot.columns]
fig = px.imshow(
    pivot,
    text_auto=".0%",
    color_continuous_scale="Blues",
    aspect="auto",
    labels={"color": "retention"},
    title="Weekly signup cohort × day N (blank = not yet observable)",
)
fig.update_layout(height=max(300, 28 * len(pivot) + 120), coloraxis_colorbar_tickformat=".0%")
mature = cm.dropna(subset=["retention_rate"])
summ = mature.groupby("day_n")[["retained_users", "eligible_users"]].sum()
summ["rate"] = summ["retained_users"] / summ["eligible_users"]
take = ", ".join(f"D{d} {pct(r)}" for d, r in summ["rate"].items())
chart(fig, f"Pooled over eligible users: {take}.")
if {1, 7} <= set(summ.index):
    d1, d7 = summ.loc[1, "rate"], summ.loc[7, "rate"]
    st.warning(
        f"**D1 → D7 drop:** {pct(d1)} → {pct(d7)} — {pct(1 - d7 / d1)} of day-1 actives are gone by day 7.",
        icon="📉",
    )

st.subheader("Retention curves by segment")
by = st.radio("Segment", ["channel", "platform", "country_tier", "device_tier"], horizontal=True)
curve = retention.retention_curve(f, by)
if curve.empty:
    empty_state()
else:
    curve = curve[curve["day_n"] > 0]
    fig = px.line(
        curve,
        x="day_n",
        y="retention_rate",
        color="segment",
        markers=False,
        title=f"Exact-day retention by {by} (day 1–30)",
    )
    fig.update_layout(yaxis_tickformat=".0%", xaxis_title="days since signup", height=400)
    last = curve[curve["day_n"] == curve["day_n"].max()].sort_values("retention_rate")
    chart(
        fig,
        f"At day {int(curve['day_n'].max())}, {last.iloc[-1]['segment']} retains best "
        f"({pct(last.iloc[-1]['retention_rate'])}) and {last.iloc[0]['segment']} worst ({pct(last.iloc[0]['retention_rate'])}).",
    )

st.subheader("Survival (time to churn)")
surv = retention.survival_summary()
if not surv:
    empty_state("Run `pulseiq survival` to produce Kaplan-Meier curves.")
else:
    st.caption(
        f"Churn = no session for 14 consecutive days · {surv['n_users']:,} users, {surv['churn_events']:,} churn events "
        "(whole data window; not affected by the filters)."
    )
    tabs = st.tabs([k["by"] for k in surv["km"]] + ["Cox model"])
    for tab, km in zip(tabs, surv["km"], strict=False):
        with tab:
            if Path(km["chart"]).exists():
                st.image(km["chart"], use_container_width=True)
            best = max(km["survival_at_30d"], key=km["survival_at_30d"].get)
            st.caption(
                f"**Takeaway:** log-rank p = {km['logrank_p']:.2g}; {best} has the highest share not yet churned "
                f"at day 30 ({pct(km['survival_at_30d'][best])})."
            )
    with tabs[-1]:
        cox = pd.DataFrame([c for c in surv["cox"] if not c["feature"].startswith("_")])
        fig = px.scatter(
            cox,
            x="hazard_ratio",
            y="feature",
            error_x=cox["ci_high"] - cox["hazard_ratio"],
            error_x_minus=cox["hazard_ratio"] - cox["ci_low"],
            title="Cox hazard ratios (< 1 = protective)",
        )
        fig.add_vline(x=1, line_dash="dash")
        fig.update_layout(height=320)
        top = cox.sort_values("hazard_ratio").iloc[0]
        chart(
            fig,
            f"{top['feature']} has the strongest protective effect (HR {top['hazard_ratio']:.2f}).",
        )

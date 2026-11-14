"""PulseIQ dashboard — executive overview (run: streamlit run apps/dashboard/Home.py)."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st
from components.filters import sidebar_filters
from components.kpi_cards import kpi_row
from components.theme import badge, chart, empty_state, num, pct, setup

setup("Overview", "📈")

from pulseiq.services import experiments, funnel, kpis  # noqa: E402

f = sidebar_filters()
st.title("PulseIQ — Product Analytics & Experimentation")
st.caption(
    "Executive overview of a fitness/habit subscription app · synthetic data with known ground truth"
)

summary = kpis.kpi_summary(f)
st.markdown(
    f"**{summary.start[:10]} → {summary.end[:10]}** · deltas vs the previous period of equal length"
)
kpi_row(
    summary.kpis,
    ["Avg DAU", "MAU", "Stickiness", "Trial conversion", "Trial → paid", "Net revenue"],
)

left, right = st.columns([3, 2])
with left:
    trend = kpis.dau_trend(f)
    if trend.empty or trend["dau"].sum() == 0:
        empty_state()
    else:
        fig = go.Figure()
        fig.add_bar(
            x=trend["day"],
            y=trend["new_users"],
            name="new users",
            marker_color="#56B4E9",
            opacity=0.6,
        )
        fig.add_scatter(x=trend["day"], y=trend["dau"], name="DAU", line={"width": 2.5})
        fig.add_scatter(
            x=trend["day"], y=trend["dau_7d_avg"], name="DAU 7-day avg", line={"dash": "dot"}
        )
        fig.update_layout(title="Daily active users and new signups", height=360)
        change = trend["dau_7d_avg"].iloc[-1] / max(trend["dau_7d_avg"].iloc[0], 1) - 1
        chart(fig, f"DAU (7-day avg) changed {change:+.0%} over the selected period.")
with right:
    fu = funnel.funnel(f)
    if fu.stages[0].users == 0:
        empty_state()
    else:
        fig = go.Figure(
            go.Funnel(
                y=[s.stage for s in fu.stages],
                x=[s.users for s in fu.stages],
                textinfo="value+percent initial",
                marker={"color": ["#0072B2", "#56B4E9", "#E69F00", "#009E73"]},
            )
        )
        fig.update_layout(title="Signup-cohort funnel", height=360)
        chart(fig, fu.biggest_drop or "")

st.subheader("Experiments")
for e in experiments.list_experiments():
    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
    c1.markdown(f"**{e['name']}**  \n`{e['experiment_id']}` · {e['start_date']} → {e['end_date']}")
    c2.markdown(badge(e["decision"]), unsafe_allow_html=True)
    c3.markdown(
        f"Primary `{e['primary_metric']}`  \n**{e['primary_lift_abs'] * 100:+.2f} pp** "
        f"[{e['primary_ci'][0] * 100:+.2f}, {e['primary_ci'][1] * 100:+.2f}]"
    )
    c4.markdown(
        f"n = {num(e['n_control'])} / {num(e['n_treatment'])}"
        + ("  \n⚠️ SRM" if e["srm_flagged"] else "")
    )
st.caption(
    "Open **Experiments** for the full readout (SRM, CUPED, sequential, Bayesian, segments)."
)
st.caption(
    f"Onboarding rate in period: {pct(fu.stages[1].overall_conversion)} · paid share of signups: "
    f"{pct(fu.stages[3].overall_conversion)}"
)

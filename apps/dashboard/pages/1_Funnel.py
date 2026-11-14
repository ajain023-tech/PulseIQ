"""Funnel: stages, step conversion, biggest drop, segments, onboarding steps."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from components.filters import sidebar_filters
from components.theme import chart, empty_state, num, pct, setup

setup("Funnel", "🔻")
from pulseiq.services import funnel  # noqa: E402

f = sidebar_filters()
st.title("Funnel")
st.caption(
    "Ordered funnel of users who signed up in the period: a stage counts only if the previous one happened first."
)

fu = funnel.funnel(f)
if fu.stages[0].users == 0:
    empty_state()
    st.stop()
st.warning(f"**Biggest drop:** {fu.biggest_drop}", icon="⚠️")
cols = st.columns(4)
for c, s in zip(cols, fu.stages, strict=True):
    c.metric(
        s.stage,
        num(s.users),
        None if s.step_conversion is None else f"{pct(s.step_conversion)} of previous",
        delta_color="off",
    )

left, right = st.columns(2)
with left:
    fig = go.Figure(
        go.Funnel(
            y=[s.stage for s in fu.stages],
            x=[s.users for s in fu.stages],
            textinfo="value+percent previous",
        )
    )
    fig.update_layout(title="Users at each stage", height=380)
    chart(fig, f"{pct(fu.stages[-1].overall_conversion)} of signups end up paying.")
with right:
    steps = pd.DataFrame(
        [
            {"step": f"{a.stage} → {b.stage}", "conversion": b.step_conversion}
            for a, b in zip(fu.stages, fu.stages[1:], strict=False)
        ]
    )
    fig = px.bar(
        steps, x="step", y="conversion", text=steps["conversion"].map(pct), title="Step conversion"
    )
    fig.update_layout(yaxis_tickformat=".0%", height=380)
    worst = steps.loc[steps["conversion"].idxmin()]
    chart(fig, f"The weakest step is {worst['step']} at {pct(worst['conversion'])}.")

st.subheader("Segment comparison")
by = st.radio("Split by", ["channel", "platform", "country_tier", "device_tier"], horizontal=True)
seg = pd.DataFrame(funnel.funnel(f, by).segments)
if seg.empty:
    empty_state()
else:
    long = seg.melt(
        id_vars="segment",
        value_vars=["onboarding_rate", "trial_rate", "paid_rate"],
        var_name="step",
        value_name="rate",
    )
    long["step"] = long["step"].map(
        {
            "onboarding_rate": "signup → onboarded",
            "trial_rate": "onboarded → trial",
            "paid_rate": "trial → paid",
        }
    )
    fig = px.bar(
        long, x="segment", y="rate", color="step", barmode="group", title=f"Step conversion by {by}"
    )
    fig.update_layout(yaxis_tickformat=".0%", height=400)
    best = seg.loc[seg["signup_to_paid"].idxmax()]
    worst = seg.loc[seg["signup_to_paid"].idxmin()]
    chart(
        fig,
        f"{best['segment']} converts best signup → paid ({pct(best['signup_to_paid'])}); "
        f"{worst['segment']} worst ({pct(worst['signup_to_paid'])}). Descriptive, not causal.",
    )
    st.dataframe(
        seg.style.format(
            {c: "{:.1%}" for c in ("onboarding_rate", "trial_rate", "paid_rate", "signup_to_paid")}
        ),
        use_container_width=True,
        hide_index=True,
    )

st.subheader("Onboarding step drop-off")
steps = funnel.onboarding_steps(f)
if steps.empty:
    empty_state()
else:
    fig = go.Figure()
    fig.add_bar(x=steps["step"].map(lambda s: f"step {s}"), y=steps["viewed"], name="viewed")
    fig.add_bar(x=steps["step"].map(lambda s: f"step {s}"), y=steps["completed"], name="completed")
    fig.update_layout(
        title="Onboarding: users who viewed vs completed each step", barmode="group", height=360
    )
    worst = steps.loc[steps["completion_rate"].idxmin()]
    chart(
        fig,
        f"Step {int(worst['step'])} loses the most viewers ({pct(1 - worst['completion_rate'])} abandon there).",
    )

"""Experiment designer: sample size, MDE and days to run."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from components.theme import chart, num, setup

setup("Experiment Designer", "📐")
from pulseiq.experiments.power import days_to_run, mde, sample_size  # noqa: E402
from pulseiq.services.db import query  # noqa: E402

st.title("Experiment designer")
st.caption(
    "Two-sided two-proportion test, 50/50 split. Plan the sample size before you launch — and don't peek "
    "without a sequential test."
)
daily_signups = float(query("select avg(new_users) from agg_kpis_daily").iloc[0, 0])

c = st.columns(5)
baseline = c[0].number_input("Baseline rate", 0.01, 0.95, 0.20, 0.01, format="%.2f")
mde_rel = c[1].number_input(
    "MDE (relative)",
    0.01,
    1.0,
    0.10,
    0.01,
    format="%.2f",
    help="Smallest relative lift worth detecting, e.g. 0.10 = +10 %",
)
alpha = c[2].selectbox("α", [0.01, 0.05, 0.10], index=1)
power = c[3].selectbox("Power", [0.8, 0.9], index=0)
traffic = c[4].number_input(
    "Eligible users / day (total)",
    10,
    1_000_000,
    int(daily_signups),
    10,
    help="Default: average daily signups in the warehouse",
)
abs_mde = baseline * mde_rel
if baseline + abs_mde >= 1:
    st.error("Baseline + MDE must stay below 100 %.")
    st.stop()
n = sample_size(baseline, abs_mde, alpha, power)
days = days_to_run(n, traffic / 2)
k = st.columns(3)
k[0].metric("Users per arm", num(n))
k[1].metric("Total users", num(2 * n))
k[2].metric("Days to run", f"{days:.1f}")
st.caption(
    f"Detects {baseline:.1%} → {baseline + abs_mde:.1%} (absolute +{abs_mde * 100:.2f} pp) with "
    f"{power:.0%} power at α = {alpha}."
)

grid = np.linspace(0.02, 0.5, 40)
df = pd.DataFrame(
    {
        "relative MDE": grid,
        "users per arm": [
            sample_size(baseline, baseline * g, alpha, power) if baseline * (1 + g) < 1 else np.nan
            for g in grid
        ],
    }
)
df["days"] = df["users per arm"] / (traffic / 2)
fig = px.line(
    df,
    x="relative MDE",
    y="users per arm",
    log_y=True,
    title="Sample size per arm vs MDE (log scale)",
    hover_data={"days": ":.1f"},
)
fig.add_vline(x=mde_rel, line_dash="dash")
fig.update_layout(xaxis_tickformat=".0%", height=380)
chart(
    fig,
    "Halving the MDE roughly quadruples the sample size — be realistic about the effect you can expect.",
)

st.subheader("What can I detect with a fixed budget?")
budget = st.slider("Users per arm available", 500, 50_000, 10_000, 500)
m = mde(budget, baseline, alpha, power)
st.metric("Minimum detectable effect", f"+{m * 100:.2f} pp ({m / baseline:+.1%} relative)")

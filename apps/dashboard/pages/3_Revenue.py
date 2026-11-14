"""Revenue: net revenue & MRR, ARPPU, refunds, plan mix, revenue by country tier."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from components.filters import sidebar_filters
from components.theme import chart, empty_state, pct, setup, usd

setup("Revenue", "💵")
from pulseiq.services import revenue  # noqa: E402

f = sidebar_filters()
st.title("Revenue")
st.caption(
    "Cash revenue (charges − refunds), MRR (annual plans counted as price / 12) and ARPPU. Revenue ≠ profit."
)

daily = revenue.revenue_daily(f)
br = revenue.revenue_breakdown(f)
if daily.empty or daily["gross_usd"].sum() == 0:
    empty_state()
    st.stop()
c = st.columns(4)
c[0].metric("Net revenue", usd(daily["net_usd"].sum()))
c[1].metric("MRR (end of period)", usd(daily["mrr_usd"].iloc[-1]))
c[2].metric("ARPPU / month", usd(daily["arppu_usd"].iloc[-1], 2))
c[3].metric("Refund rate", pct(br["refund_rate"]))

fig = go.Figure()
fig.add_bar(x=daily["day"], y=daily["net_usd"], name="net revenue / day", marker_color="#56B4E9")
fig.add_scatter(
    x=daily["day"],
    y=daily["mrr_usd"],
    name="MRR",
    yaxis="y2",
    line={"width": 2.5, "color": "#0072B2"},
)
fig.update_layout(
    title="Daily net revenue and MRR",
    height=380,
    yaxis={"title": "net / day", "tickprefix": "$"},
    yaxis2={
        "title": "MRR",
        "overlaying": "y",
        "side": "right",
        "tickprefix": "$",
        "showgrid": False,
    },
)
growth = daily["mrr_usd"].iloc[-1] / max(daily["mrr_usd"].iloc[0], 1) - 1
chart(fig, f"MRR moved {growth:+.0%} over the period to {usd(daily['mrr_usd'].iloc[-1])}.")

left, right = st.columns(2)
with left:
    plan = pd.DataFrame(br["plan_mix"])
    if plan.empty:
        empty_state("No new paid subscriptions in this period.")
    else:
        fig = px.pie(
            plan,
            names="plan",
            values="subscriptions",
            hole=0.5,
            title="Plan mix of new paid subscriptions",
        )
        fig.update_layout(height=340)
        share = plan.set_index("plan")["subscriptions"] / plan["subscriptions"].sum()
        chart(fig, f"Annual plans are {pct(share.get('annual', 0))} of new paid subscriptions.")
with right:
    tier = pd.DataFrame(br["by_country_tier"])
    if tier.empty:
        empty_state()
    else:
        fig = px.bar(
            tier,
            x="country_tier",
            y="net_usd",
            text=tier["net_usd"].map(usd),
            title="Net revenue by country tier",
            category_orders={"country_tier": ["high", "mid", "low"]},
        )
        fig.update_layout(height=340, yaxis_tickprefix="$")
        top = tier.loc[tier["net_usd"].idxmax()]
        chart(
            fig,
            f"The {top['country_tier']} tier earns the most ({usd(top['net_usd'])}; "
            f"{usd(top['net_per_payer_usd'], 2)} per payer) — PPP pricing makes per-payer value differ ~2.5×.",
        )
fig = px.line(daily, x="day", y="arppu_usd", title="ARPPU (MRR / active subscriptions)")
fig.update_layout(height=300, yaxis_tickprefix="$")
chart(fig, "ARPPU is stable when price mix is stable; shifts reflect plan and country mix.")

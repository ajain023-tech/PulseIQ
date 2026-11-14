"""Retention model: metrics vs baselines, curves, threshold trade-off, user scoring, at-risk list."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from components.theme import chart, empty_state, pct, setup

setup("Retention Model", "🤖")
from pulseiq.services import predictions  # noqa: E402

st.title("D30 retention model")
try:
    meta = predictions.model_meta()
except FileNotFoundError:
    empty_state("No model yet — run `pulseiq train`.")
    st.stop()
st.caption(
    f"Predicts at 72 h after signup whether a user is active on day 30 · model `{meta['model']}` + isotonic "
    f"calibration · time-based split · features from the first 72 h only (leakage-tested)."
)

m = pd.DataFrame(meta["metrics_test"]).T
m.index.name = "model"
show = m[
    [
        "pr_auc",
        "roc_auc",
        "brier",
        "recall",
        "precision",
        "f1",
        "recall_at_top20",
        "lift_at_top_decile",
        "accuracy",
    ]
]
st.subheader("Test-set metrics vs baselines")
st.dataframe(
    show.astype(float)
    .style.format("{:.3f}")
    .highlight_max(subset=["pr_auc", "roc_auc", "f1"], color="#D6EAF8"),
    use_container_width=True,
)
best = m.loc[meta["model"]]
st.caption(
    f"**Takeaway:** PR-AUC {best['pr_auc']:.3f} vs {m.loc['majority_baseline', 'pr_auc']:.3f} for the "
    f"'nobody is retained' baseline — which still scores {m.loc['majority_baseline', 'accuracy']:.0%} accuracy. "
    "That is why v1's 85 % accuracy meant nothing."
)

charts = meta["charts"]
tabs = st.tabs(["PR curve", "Calibration", "Feature importance", "SHAP", "Gain"])
for tab, key, note in zip(
    tabs,
    ["pr_curve", "calibration", "permutation_importance", "shap_summary", "gain_chart"],
    [
        "The model's curve sits far above the baselines across all recall levels.",
        "Class weighting inflates raw probabilities; isotonic calibration on validation fixes it (lower Brier).",
        "Top drivers are workout logs, early active days and reminders — exactly the drivers planted in the simulation.",
        "High early engagement (red) pushes predictions up; missing habits push them down.",
        f"Contacting the top 20 % by score captures {pct(best['recall_at_top20'])} of retained users.",
    ],
    strict=True,
):
    with tab:
        if key in charts and Path(charts[key]).exists():
            st.image(charts[key], use_container_width=True)
            st.caption(f"**Takeaway:** {note}")
        else:
            empty_state("Chart not available.")

st.subheader("Threshold trade-off")
tt = predictions.threshold_table()
t = st.slider(
    "Classify as 'will retain' when P(retained) ≥",
    float(tt["threshold"].min()),
    float(tt["threshold"].max()),
    float(round(meta["threshold"], 2)),
    0.01,
)
row = tt.iloc[(tt["threshold"] - t).abs().argmin()]
c = st.columns(4)
c[0].metric("Precision (retained)", pct(row["precision"]))
c[1].metric("Recall (retained)", pct(row["recall"]))
c[2].metric("Flagged at-risk", pct(row["at_risk_share"]))
c[3].metric("Churners caught", pct(row["churners_caught"]))
long = tt.melt(
    id_vars="threshold", value_vars=["precision", "recall", "at_risk_share"], var_name="measure"
)
fig = px.line(
    long,
    x="threshold",
    y="value",
    color="measure",
    title="Precision / recall / users flagged vs threshold",
)
fig.add_vline(x=t, line_dash="dash")
fig.update_layout(yaxis_tickformat=".0%", height=340)
chart(
    fig,
    f"Validation-chosen threshold {meta['threshold']:.3f} maximises F1; lower it to reach more users at "
    "the cost of precision.",
)

st.subheader("Score a user")
uid = st.text_input("user_id", placeholder="e.g. u055117")
if uid:
    res = predictions.score_user(uid.strip())
    if res is None:
        st.error("Unknown user_id.")
    else:
        a, b = st.columns([1, 2])
        a.metric(
            "P(active on day 30)",
            pct(res["p_retained_d30"]),
            f"risk: {res['risk_band']}",
            delta_color="off",
        )
        contrib = pd.DataFrame(res["top_contributions"])
        if not contrib.empty:
            fig = px.bar(
                contrib,
                x="effect",
                y="feature",
                orientation="h",
                title="What moved this user's score",
                color=contrib["effect"] > 0,
                color_discrete_map={True: "#009E73", False: "#D55E00"},
            )
            fig.update_layout(showlegend=False, height=260, xaxis_tickformat="+.1%")
            b.plotly_chart(fig, use_container_width=True)

st.subheader("Top at-risk recent signups")
risk = predictions.at_risk(200)
if risk.empty:
    empty_state("No recent signups with complete 72 h features.")
else:
    st.dataframe(
        risk.head(50).style.format({"p_retained_d30": "{:.1%}"}),
        use_container_width=True,
        hide_index=True,
    )
    st.download_button(
        "Download at-risk list (CSV)", risk.to_csv(index=False), "pulseiq_at_risk.csv", "text/csv"
    )

with st.expander("Model card summary"):
    fair = pd.DataFrame(meta["fairness"]["platform"])
    st.markdown(
        f"- **Intended use:** rank new users for an early retention campaign (bottom 20 % = high risk).\n"
        f"- **Training window:** {meta['split']['train'][0][:10]} → {meta['split']['train'][1][:10]}; "
        f"test {meta['split']['test'][0][:10]} → {meta['split']['test'][1][:10]}.\n"
        f"- **Caveats:** synthetic data; exact-day D30 is noisy; retrain monthly.\n"
        f"- Full card: `docs/MODEL_CARD.md`."
    )
    st.dataframe(
        fair.style.format({"positive_rate": "{:.1%}", "recall": "{:.3f}", "precision": "{:.3f}"}),
        hide_index=True,
    )

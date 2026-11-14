"""Experiments: decision, SRM, metrics (raw vs CUPED), forest, sequential, Bayesian, segments, peeking."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from components.theme import badge, chart, empty_state, setup

setup("Experiments", "🧪")
from pulseiq.config import get_settings  # noqa: E402
from pulseiq.services import experiments  # noqa: E402

st.title("Experiments")
st.caption(
    "Validated readouts: SRM check → frequentist (Newcombe/Welch) → CUPED → Holm/BH → mSPRT → Bayesian → decision."
)

rows = experiments.list_experiments()
labels = {r["experiment_id"]: f"{r['name']} ({r['experiment_id']})" for r in rows}
exp_id = st.selectbox("Experiment", list(labels), format_func=labels.get)
rep = experiments.get_report(exp_id)

c1, c2 = st.columns([1, 3])
c1.markdown(badge(rep.decision), unsafe_allow_html=True)
c1.caption(
    f"{rep.start_date} → {rep.end_date}  \ncontrol {rep.n_control:,} · treatment {rep.n_treatment:,}"
)
with c2:
    st.markdown(f"**Hypothesis:** {rep.hypothesis}")
    for r in rep.reasons:
        st.markdown(f"- {r}")

st.subheader("Sample ratio mismatch")
if rep.srm.flagged:
    causes = (
        ", ".join(f"{c['segment_type']}={c['segment_value']}" for c in rep.srm.likely_causes)
        or "not localised"
    )
    st.error(
        f"SRM detected: p = {rep.srm.p_value:.2g}, treatment share {rep.srm.treatment_share:.1%} "
        f"(intended {rep.srm.allocation:.0%}). Likely cause: **{causes}**. Metric readouts below are not trustworthy."
    )
else:
    st.success(f"No SRM: p = {rep.srm.p_value:.3g}, treatment share {rep.srm.treatment_share:.1%}.")
seg = pd.DataFrame(rep.srm.segments)
if not seg.empty:
    fig = px.bar(
        seg,
        x="segment_value",
        y="treatment_share",
        color="flagged",
        facet_col="segment_type",
        color_discrete_map={True: "#D55E00", False: "#0072B2"},
        title="Treatment share by segment",
    )
    fig.add_hline(y=rep.srm.allocation, line_dash="dash")
    lo = min(rep.srm.allocation - 0.03, seg["treatment_share"].min() - 0.01)
    hi = max(rep.srm.allocation + 0.03, seg["treatment_share"].max() + 0.01)
    fig.update_layout(height=300, yaxis_tickformat=".1%", yaxis_range=[lo, hi])
    fig.for_each_xaxis(lambda a: a.update(matches=None))
    chart(
        fig,
        "Each bar should sit on the dashed line; a flagged bar points at where assignment or logging broke.",
    )

st.subheader("Metrics")
st.caption(
    f"CUPED: {rep.cuped_status}. Holm-adjusted p for primary + guardrails; BH for secondaries."
)
tbl = pd.DataFrame(
    [
        {
            "metric": m.label,
            "role": m.role,
            "control": m.value_control,
            "treatment": m.value_treatment,
            "diff (raw)": m.abs_diff,
            "CI raw": f"[{m.ci_low:+.4f}, {m.ci_high:+.4f}]",
            "diff (decision)": m.decision_diff,
            "CI decision": f"[{m.decision_ci[0]:+.4f}, {m.decision_ci[1]:+.4f}]",
            "CUPED": "yes" if m.cuped_used else "",
            "p": m.decision_p,
            "adj p": m.p_adjusted,
            "significant": "✔" if m.significant else "",
        }
        for m in rep.metrics
    ]
)
st.dataframe(
    tbl.style.format(
        {
            "control": "{:.4f}",
            "treatment": "{:.4f}",
            "diff (raw)": "{:+.4f}",
            "diff (decision)": "{:+.4f}",
            "p": "{:.3g}",
            "adj p": "{:.3g}",
        }
    ),
    use_container_width=True,
    hide_index=True,
)
cup = [m for m in rep.metrics if m.cuped]
if cup:
    p = cup[0]
    st.info(
        f"CUPED on **{p.label}**: θ = {p.cuped.theta:.4f}, corr = {p.cuped.correlation:.2f}, variance "
        f"−{p.cuped.variance_reduction:.0%}, CI width {p.cuped.ci_width_raw:.4f} → {p.cuped.ci_width_cuped:.4f} "
        f"(**−{p.cuped.ci_width_reduction:.0%}**).",
        icon="✂️",
    )

forest = pd.DataFrame(
    [
        {
            "metric": m.label + (" (CUPED)" if m.cuped_used else ""),
            "role": m.role,
            "lift": m.decision_diff / m.value_control * 100 if m.value_control else np.nan,
            "lo": m.decision_ci[0] / m.value_control * 100 if m.value_control else np.nan,
            "hi": m.decision_ci[1] / m.value_control * 100 if m.value_control else np.nan,
        }
        for m in rep.metrics
    ]
).dropna()
fig = px.scatter(
    forest,
    x="lift",
    y="metric",
    color="role",
    error_x=forest["hi"] - forest["lift"],
    error_x_minus=forest["lift"] - forest["lo"],
    title="Relative lift vs control with 95 % CI (%)",
    color_discrete_map={"primary": "#0072B2", "guardrail": "#E69F00", "secondary": "#7F7F7F"},
)
fig.add_vline(x=0, line_color="black")
fig.update_layout(height=60 * len(forest) + 140)
prim = rep.metrics[0]
chart(
    fig,
    f"Primary {prim.label}: {prim.decision_diff / prim.value_control:+.1%} relative "
    f"({'significant' if prim.significant else 'not significant'} after correction).",
)

left, right = st.columns(2)
with left:
    s = rep.sequential
    if s and s.get("applicable"):
        x = s["looks"]
        fig = go.Figure()
        fig.add_scatter(x=x, y=s["cs_high"], line={"width": 0}, showlegend=False, hoverinfo="skip")
        fig.add_scatter(
            x=x,
            y=s["cs_low"],
            fill="tonexty",
            line={"width": 0},
            name="always-valid 95 % CS",
            fillcolor="rgba(0,114,178,0.15)",
        )
        fig.add_scatter(
            x=x, y=s["naive_ci_low"], line={"dash": "dash", "color": "#E69F00"}, name="naive CI"
        )
        fig.add_scatter(
            x=x, y=s["naive_ci_high"], line={"dash": "dash", "color": "#E69F00"}, showlegend=False
        )
        fig.add_scatter(
            x=x, y=s["diff"], line={"color": "#0072B2", "width": 2.5}, name="cumulative lift"
        )
        fig.add_hline(y=0, line_color="black")
        lo, hi = np.nanpercentile(s["cs_low"], 10), np.nanpercentile(s["cs_high"], 90)
        fig.update_layout(
            title="Cumulative lift over daily looks", height=360, yaxis_range=[lo, hi]
        )
        cross = s["first_crossing_look"]
        chart(
            fig,
            "The always-valid sequence never excludes 0"
            if cross is None
            else f"mSPRT boundary first crossed on {s['looks'][cross]} (look {cross + 1}); safe to stop there despite peeking.",
        )
    else:
        empty_state((s or {}).get("reason", "Sequential monitoring not available."))
with right:
    b = prim.bayesian
    if b:
        from scipy import stats

        (ac, bc), (at, bt) = b["posterior_control"], b["posterior_treatment"]
        lo = min(stats.beta.ppf(0.0005, ac, bc), stats.beta.ppf(0.0005, at, bt))
        hi = max(stats.beta.ppf(0.9995, ac, bc), stats.beta.ppf(0.9995, at, bt))
        xs = np.linspace(lo, hi, 300)
        fig = go.Figure()
        fig.add_scatter(
            x=xs, y=stats.beta.pdf(xs, ac, bc), name="control", line={"color": "#7F7F7F"}
        )
        fig.add_scatter(
            x=xs, y=stats.beta.pdf(xs, at, bt), name="treatment", line={"color": "#0072B2"}
        )
        fig.update_layout(title=f"Posterior of {prim.metric}", height=360)
        chart(
            fig,
            f"P(treatment > control) = {b['prob_treatment_better']:.3f}; expected loss if we ship "
            f"treatment = {b['expected_loss_ship_treatment']:.5f}.",
        )

st.subheader("Segments (exploratory)")
st.warning(
    "Exploratory only — slicing many ways finds 'winners' by chance. BH-corrected; underpowered segments flagged.",
    icon="🧭",
)
segs = pd.DataFrame(rep.segments)
if segs.empty:
    empty_state()
else:
    segs["label"] = segs["segment_type"] + "=" + segs["segment_value"]
    fig = px.scatter(
        segs,
        x="abs_diff",
        y="label",
        color="underpowered",
        error_x=segs["ci_high"] - segs["abs_diff"],
        error_x_minus=segs["abs_diff"] - segs["ci_low"],
        title=f"Effect on {rep.primary_metric} by segment",
        color_discrete_map={True: "#E69F00", False: "#0072B2"},
    )
    fig.add_vline(x=0, line_color="black")
    fig.update_layout(height=40 * len(segs) + 140)
    n_sig = int(segs["significant_bh"].sum())
    chart(fig, f"{n_sig} of {len(segs)} segment effects survive BH correction.")

st.subheader("Why peeking is dangerous")
pk = get_settings().artifacts_dir / "experiments" / "peeking_simulation.json"
if pk.exists():
    sim = json.loads(pk.read_text())
    x = list(range(1, sim["looks"] + 1))
    fig = go.Figure()
    fig.add_scatter(
        x=x,
        y=np.array(sim["cum_fpr_naive_by_look"]) * 100,
        name="naive p < 0.05 at any look",
        line={"color": "#D55E00", "width": 2.5},
    )
    fig.add_scatter(
        x=x,
        y=np.array(sim["cum_fpr_sequential_by_look"]) * 100,
        name="mSPRT (always valid)",
        line={"color": "#0072B2", "width": 2.5},
    )
    fig.add_hline(y=5, line_dash="dash", annotation_text="α = 5 %")
    fig.update_layout(
        title=f"A/A simulation, {sim['n_sims']:,} tests: false-positive rate vs number of looks",
        height=360,
        xaxis_title="daily looks",
        yaxis_title="false positives (%)",
    )
    chart(
        fig,
        f"Stopping at the first p < 0.05 gives {sim['fpr_naive_peeking']:.0%} false positives; the sequential "
        f"test stays at {sim['fpr_sequential']:.1%}.",
    )
else:
    empty_state("Run `pulseiq analyze --all` to produce the peeking simulation.")

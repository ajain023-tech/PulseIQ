"""Data & methods: architecture, event schema, warehouse lineage, metric definitions, synthetic-data note."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st
from components.theme import setup

setup("Data & Methods", "📚")
from pulseiq.ai.catalog import METRIC_DEFINITIONS, catalog  # noqa: E402
from pulseiq.config import get_settings  # noqa: E402

st.title("Data & methods")
st.warning(
    "**All data is synthetic.** PulseIQ simulates a fitness/habit subscription app with *known ground truth*: "
    "experiment effects, an SRM bug and retention drivers are planted on purpose so every method can be "
    "validated against the truth. Numbers describe the simulation, not a real product.",
    icon="🧪",
)

st.subheader("Architecture")
st.graphviz_chart("""
digraph {
  rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#EAF2FB", color="#0072B2", fontname="Helvetica"];
  G [label="Event generator\\nseeded · ground truth"]; R [label="raw parquet"];
  W [label="DuckDB warehouse\\ndbt: staging → intermediate → marts"]; T [label="dbt + pytest\\ndata tests"];
  E [label="Experimentation engine\\nSRM · CUPED · mSPRT · Bayesian"]; M [label="Retention ML\\n+ survival"];
  A [label="AI analyst\\nNL → guarded SQL"]; API [label="FastAPI"]; D [label="Streamlit dashboard"];
  G -> R -> W -> T; W -> E; W -> M; W -> A; E -> API; M -> API; A -> API; E -> D; M -> D; A -> D;
}""")
st.caption(
    "The dashboard and the API call the same service layer (`src/pulseiq/services`). No SQL lives in pages."
)

st.subheader("Warehouse lineage")
st.graphviz_chart("""
digraph {
  rankdir=LR; node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10];
  subgraph cluster_s { label="staging"; color="#56B4E9"; node [fillcolor="#EAF6FD"];
    su [label=stg_users]; se [label=stg_events]; ss [label=stg_sessions]; sa [label=stg_assignments];
    sb [label=stg_subscriptions]; si [label=stg_invoices]; sx [label=stg_experiments]; }
  subgraph cluster_i { label="intermediate"; color="#E69F00"; node [fillcolor="#FDF3E1"];
    f72 [label=int_user_first_72h]; da [label=int_user_daily_activity]; dn [label=int_user_day_n_activity];
    ob [label=int_onboarding_steps]; sp [label=int_subscription_periods]; }
  subgraph cluster_m { label="marts"; color="#009E73"; node [fillcolor="#E3F5EF"];
    du [label=dim_users]; fe [label=fct_events]; ff [label=fct_funnel_user]; afs [label="agg_funnel_*"];
    rc [label=agg_retention_cohorts]; rd [label=fct_revenue_daily]; k [label=agg_kpis_daily];
    xe [label=fct_experiment_exposures]; }
  se -> f72; su -> f72; ss -> da; ss -> dn; se -> ob; si -> sp; sb -> sp;
  su -> du; se -> du; sb -> du; ss -> du; si -> du; se -> fe; du -> ff -> afs; dn -> rc; si -> rd; sp -> rd; da -> rd;
  da -> k; rd -> k; sa -> xe; sx -> xe; du -> xe; ss -> xe; sb -> xe; si -> xe; dn -> xe;
}""")

st.subheader("Metric definitions")
st.dataframe(
    pd.DataFrame([{"metric": k, "definition": v} for k, v in METRIC_DEFINITIONS.items()]),
    use_container_width=True,
    hide_index=True,
)
st.markdown(
    "- **Day N** = the 24 h block `[signup + N·24h, signup + (N+1)·24h)`; a user is in the day-N denominator "
    "only once that block is fully observed (immature cohort cells are blank, not zero).\n"
    "- **Ordered funnel**: a stage counts only if the previous stage happened first.\n"
    "- **Churn** (survival): no session for 14 consecutive days."
)

st.subheader("Event schema")
events = pd.DataFrame(
    [
        ("app_install / signup", "signup session", "source"),
        ("onboarding_step_viewed / _completed", "signup session", "step 1–5"),
        ("onboarding_completed", "signup session", "–"),
        ("session_start / session_end", "every session", "–"),
        (
            "feature_used",
            "sessions",
            "feature: workout_log, plan_view, progress_chart, social_share, reminder_set",
        ),
        ("paywall_viewed", "onboarding / feature gate / campaign", "source, paywall_variant"),
        ("trial_started", "in-session", "plan"),
        ("subscription_started / renewed / canceled", "server", "plan, price_usd, reason"),
        ("refund_issued", "server", "amount_usd"),
        ("push_received / push_opened", "before sessions", "campaign"),
    ],
    columns=["event", "where", "properties"],
)
st.dataframe(events, use_container_width=True, hide_index=True)

with st.expander("Mart columns (what the AI analyst can query)"):
    for name, t in catalog().items():
        st.markdown(f"**{name}** — {t['description']}")
        st.caption(", ".join(t["columns"]))

st.subheader("Methods")
st.markdown("""
| Area | Method | Doc |
|---|---|---|
| Experiments | SRM (χ², p < 0.001, root-cause localisation), Newcombe / Welch / bootstrap, CUPED, Holm + BH, mSPRT, Beta-Binomial, power | `docs/EXPERIMENTATION.md` |
| Retention ML | 72 h features, time split, LR + gradient boosting, isotonic calibration, PR-AUC, permutation importance + SHAP | `docs/ML_RETENTION.md`, `docs/MODEL_CARD.md` |
| Survival | Kaplan-Meier, log-rank, Cox PH | `docs/ML_RETENTION.md` |
| AI analyst | NL → JSON plan → sqlglot guard → read-only execution → grounded answer; 25-question eval | `docs/AI_ANALYST.md` |
| Warehouse | dbt on DuckDB, 70 data tests | `docs/WAREHOUSE.md` |
""")
val = get_settings().artifacts_dir / "reports" / "experiment_validation.json"
if val.exists():
    v = json.loads(val.read_text())
    st.success(
        f"Validation: {v['n_covered']}/{v['n_effects']} planted experiment effects inside the engine's 95 % CI · "
        f"SRM flagged only where planted · CUPED cut CI width by {v['cuped_ci_width_reduction_paywall']:.0%}."
    )
st.caption(
    "Future work: real event ingestion (Kafka/Redpanda), dbt on BigQuery/Snowflake, auth, a React frontend, "
    "uplift modelling."
)

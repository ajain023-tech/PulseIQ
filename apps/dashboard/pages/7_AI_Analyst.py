"""AI Product Analyst: chat UI over guarded SQL (offline mode without an API key)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from components.theme import setup

setup("AI Analyst", "💬")
from pulseiq.ai.agent import ask  # noqa: E402
from pulseiq.ai.llm import get_client  # noqa: E402
from pulseiq.ai.offline import SUGGESTED_QUESTIONS  # noqa: E402

st.title("AI Product Analyst")
client = get_client()
if client is None:
    st.info(
        "**Offline mode** — no LLM API key configured, so answers come from ~20 deterministic question templates "
        "over the same guarded SQL path. Set `PULSEIQ_LLM_PROVIDER` and a key (see docs/AI_ANALYST.md) for free-form "
        "questions.",
        icon="🔌",
    )
st.caption(
    "Every query is parsed and validated (single read-only SELECT, marts only, LIMIT 1000, 5 s timeout) and "
    "runs on a read-only connection. Experiment questions are answered by the validated stats engine."
)

st.session_state.setdefault("chat", [])


def render_chart(rows: list[dict], spec: dict) -> None:
    if not rows or not spec:
        return
    df = pd.DataFrame(rows)
    x, y, kind = spec.get("x"), spec.get("y"), spec.get("type")
    if kind in ("bar", "line") and x in df.columns and y in df.columns and len(df) > 1:
        fig = (px.bar if kind == "bar" else px.line)(df, x=x, y=y, title=f"{y} by {x}")
        if any(k in y for k in ("rate", "retention", "stickiness")):
            fig.update_layout(yaxis_tickformat=".0%")
        fig.update_layout(height=320)
        st.plotly_chart(fig, use_container_width=True)


def show(resp: dict) -> None:
    (st.warning if resp["refused"] else st.markdown)(resp["answer"])
    if resp.get("sql"):
        with st.expander("SQL used"):
            st.code(resp["sql"], language="sql")
    if resp.get("rows"):
        render_chart(resp["rows"], resp.get("chart_spec") or {})
        with st.expander(f"Result rows ({len(resp['rows'])})"):
            st.dataframe(pd.DataFrame(resp["rows"]), use_container_width=True, hide_index=True)
    if resp.get("caveats"):
        st.caption("Caveats: " + " · ".join(resp["caveats"]))
    st.caption(
        f"provider `{resp['provider']}` · {resp['latency_ms']:.0f} ms"
        + (" · retried once" if resp.get("retried") else "")
    )


for turn in st.session_state["chat"]:
    with st.chat_message("user"):
        st.markdown(turn["question"])
    with st.chat_message("assistant"):
        show(turn)

st.markdown("**Try:**")
cols = st.columns(3)
clicked = None
for i, q in enumerate([*SUGGESTED_QUESTIONS, "Delete the users table"]):
    if cols[i % 3].button(q, key=f"sugg{i}", use_container_width=True):
        clicked = q
question = (
    st.chat_input("Ask about funnel, retention, revenue, engagement or an experiment…") or clicked
)
if question:
    with st.spinner("Thinking…"):
        resp = ask(question).model_dump()
    st.session_state["chat"].append(resp)
    st.rerun()
if st.session_state["chat"] and st.button("Clear conversation"):
    st.session_state["chat"] = []
    st.rerun()

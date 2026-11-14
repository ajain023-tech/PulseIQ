"""Page setup, colour-blind-safe plotly theme and number formatting."""

from __future__ import annotations

import math

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# Okabe-Ito (colour-blind safe)
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#000000"]
DECISION_COLORS = {
    "SHIP": "#009E73",
    "DON'T SHIP": "#D55E00",
    "KEEP RUNNING": "#E69F00",
    "INVESTIGATE": "#CC79A7",
}

pio.templates["pulseiq"] = go.layout.Template(
    layout=go.Layout(
        colorway=PALETTE,
        font={"family": "Inter, Segoe UI, sans-serif", "size": 13, "color": "#1F2937"},
        title={"font": {"size": 15}, "x": 0.0, "xanchor": "left"},
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis={"gridcolor": "#EEF2F7", "zeroline": False},
        yaxis={"gridcolor": "#EEF2F7", "zeroline": False},
        margin={"l": 10, "r": 10, "t": 50, "b": 10},
        legend={"orientation": "h", "y": -0.18},
        hoverlabel={"bgcolor": "white"},
    )
)
pio.templates.default = "pulseiq"


def setup(title: str, icon: str = "📊") -> None:
    """Common page config + bootstrap + sidebar filters header."""
    st.set_page_config(page_title=f"{title} · PulseIQ", page_icon=icon, layout="wide")
    from .bootstrap import ensure_data

    ensure_data()


def pct(v, digits: int = 1) -> str:
    """0.1234 -> '12.3%'."""
    return (
        "–" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v * 100:.{digits}f}%"
    )


def usd(v, digits: int = 0) -> str:
    """1234.5 -> '$1,235'."""
    return "–" if v is None or (isinstance(v, float) and math.isnan(v)) else f"${v:,.{digits}f}"


def num(v) -> str:
    """12345.6 -> '12,346'."""
    return "–" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:,.0f}"


def chart(fig, takeaway: str) -> None:
    """Render a plotly figure followed by its one-line takeaway."""
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"**Takeaway:** {takeaway}")


def badge(decision: str) -> str:
    """HTML badge for an experiment decision."""
    c = DECISION_COLORS.get(decision, "#7F7F7F")
    return (
        f"<span style='background:{c};color:white;padding:3px 10px;border-radius:12px;"
        f"font-weight:600;font-size:0.85rem'>{decision}</span>"
    )


def empty_state(
    msg: str = "No data for these filters. Widen the date range or clear a filter.",
) -> None:
    """Friendly empty state."""
    st.info(msg, icon="🔎")

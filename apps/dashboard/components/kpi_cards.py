"""KPI cards with period-over-period deltas."""

from __future__ import annotations

import streamlit as st

from .theme import num, pct, usd


def _value(k) -> str:
    return {"ratio": pct, "usd": usd}.get(k.unit, num)(k.value)


def _delta(k) -> str | None:
    if k.delta is None:
        return None
    return f"{k.delta * 100:+.1f} pp" if k.unit == "ratio" else f"{k.delta * 100:+.1f}%"


def kpi_row(kpis, names: list[str]) -> None:
    """Render the named KPIs as metric cards."""
    chosen = [k for k in kpis if k.name in names]
    cols = st.columns(len(chosen))
    for col, k in zip(cols, chosen, strict=True):
        col.metric(
            k.name,
            _value(k),
            _delta(k),
            help=k.definition + " · delta vs previous period of equal length",
        )

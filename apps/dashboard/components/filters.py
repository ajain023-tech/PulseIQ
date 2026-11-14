"""Global sidebar filters shared across pages via st.session_state."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from pulseiq.services.filters import CHANNELS, COUNTRY_TIERS, PLATFORMS, Filters
from pulseiq.services.meta import build_info, data_window

ALL = "All"


def _persist(key: str) -> None:
    st.session_state[f"g_{key}"] = st.session_state[f"w_{key}"]


def sidebar_filters(show_dates: bool = True) -> Filters:
    """Render the shared filters and return the active ``Filters``."""
    first, last = data_window()
    st.session_state.setdefault("g_dates", (max(first, last - timedelta(days=27)), last))
    for k in ("platform", "channel", "tier"):
        st.session_state.setdefault(f"g_{k}", ALL)
    with st.sidebar:
        st.markdown("### Filters")
        if show_dates:
            st.session_state["w_dates"] = st.session_state["g_dates"]
            st.date_input(
                "Date range",
                min_value=first,
                max_value=last,
                key="w_dates",
                on_change=_persist,
                args=("dates",),
            )
        for key, label, options in (
            ("platform", "Platform", PLATFORMS),
            ("channel", "Channel", CHANNELS),
            ("tier", "Country tier", COUNTRY_TIERS),
        ):
            st.session_state[f"w_{key}"] = st.session_state[f"g_{key}"]
            st.selectbox(label, (ALL, *options), key=f"w_{key}", on_change=_persist, args=(key,))
        if st.button("Reset filters", use_container_width=True):
            st.session_state["g_dates"] = (max(first, last - timedelta(days=27)), last)
            for k in ("platform", "channel", "tier"):
                st.session_state[f"g_{k}"] = ALL
            st.rerun()
        info = build_info()
        st.caption(
            f"Data {first} → {last} · warehouse built {str(info['warehouse_built_at'])[:16].replace('T', ' ')} UTC"
        )
        st.caption("Synthetic data — see *Data & Methods*.")
    dates = st.session_state["g_dates"]
    start, end = (
        (dates if isinstance(dates, tuple | list) and len(dates) == 2 else (dates[0], dates[0]))
        if isinstance(dates, tuple | list)
        else (dates, dates)
    )
    pick = lambda k: None if st.session_state[f"g_{k}"] == ALL else st.session_state[f"g_{k}"]  # noqa: E731
    return Filters(
        start if isinstance(start, date) else None,
        end if isinstance(end, date) else None,
        pick("platform"),
        pick("channel"),
        pick("tier"),
    )

"""Cold-start bootstrap: build a small warehouse + artifacts if none exist (cloud deploys)."""

from __future__ import annotations

import os

import streamlit as st

from pulseiq.config import get_settings


@st.cache_resource(show_spinner=False)
def _bootstrap() -> str:
    from pulseiq.experiments import analyze_experiment, save_report
    from pulseiq.experiments.data import list_experiments
    from pulseiq.generator import generate
    from pulseiq.generator.write import write_result
    from pulseiq.ml.pipeline import run_survival, run_training
    from pulseiq.services import db
    from pulseiq.warehouse import build_warehouse, connect

    s = get_settings()
    if not s.warehouse_path.exists():
        size = os.environ.get("PULSEIQ_SIZE", "small")
        write_result(generate(size, s.seed), s.raw_dir)
        res = build_warehouse(s)
        if not res.success:
            raise RuntimeError("Warehouse build failed: " + "; ".join(res.failures[:3]))
    with connect() as con:
        for exp_id in list_experiments(con):
            if not (s.artifacts_dir / "experiments" / exp_id / "report.json").exists():
                save_report(
                    analyze_experiment(con, exp_id), s.artifacts_dir / "experiments" / exp_id
                )
        if not (s.artifacts_dir / "ml" / "model.joblib").exists():
            run_training(con, s.artifacts_dir / "ml")
        if not (s.artifacts_dir / "ml" / "survival.json").exists():
            run_survival(con, s.artifacts_dir / "ml")
    db.reset()
    return str(s.warehouse_path)


def ensure_data() -> None:
    """Run the bootstrap once per process (fast no-op when everything exists)."""
    s = get_settings()
    ready = s.warehouse_path.exists() and (s.artifacts_dir / "ml" / "model.joblib").exists()
    if ready:
        _bootstrap()
        return
    with st.spinner(
        "First start: generating data, building the warehouse and training the model (~30 s)…"
    ):
        _bootstrap()

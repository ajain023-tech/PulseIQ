"""Smoke test: every dashboard page renders without exceptions (default + narrow filters)."""

from __future__ import annotations

from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "apps" / "dashboard"
PAGES = ["Home.py", *sorted(p.name for p in (APP_DIR / "pages").glob("*.py"))]


@pytest.fixture(scope="module")
def ready(small_env):
    import duckdb

    from pulseiq.config import get_settings
    from pulseiq.experiments import analyze_experiment, save_report
    from pulseiq.experiments.data import list_experiments
    from pulseiq.ml.pipeline import run_survival, run_training
    from pulseiq.services import db

    s = get_settings()
    with duckdb.connect(str(s.warehouse_path), read_only=True) as con:
        for e in list_experiments(con):
            save_report(
                analyze_experiment(con, e), s.artifacts_dir / "experiments" / e, charts=False
            )
        if not (s.artifacts_dir / "ml" / "model.joblib").exists():
            run_training(con, s.artifacts_dir / "ml")
        run_survival(con, s.artifacts_dir / "ml")
    db.reset()
    yield
    db.reset()


def _run(page: str, state: dict | None = None):
    from streamlit.testing.v1 import AppTest

    path = APP_DIR / page if page == "Home.py" else APP_DIR / "pages" / page
    at = AppTest.from_file(str(path), default_timeout=60)
    for k, v in (state or {}).items():
        at.session_state[k] = v
    at.run()
    return at


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(ready, page):
    at = _run(page)
    assert not at.exception, [e.value for e in at.exception]
    assert at.title, page


@pytest.mark.parametrize("page", ["Home.py", "1_Funnel.py", "2_Retention.py", "3_Revenue.py"])
def test_page_narrow_filters(ready, page):
    from datetime import date

    state = {
        "g_platform": "web",
        "g_channel": "influencer",
        "g_tier": "mid",
        "g_dates": (date(2025, 1, 10), date(2025, 1, 12)),
    }
    at = _run(page, state)
    assert not at.exception, [e.value for e in at.exception]


def test_ai_page_question(ready):
    at = _run("7_AI_Analyst.py")
    at.button(key="sugg0").click().run()
    assert not at.exception
    assert len(at.session_state["chat"]) == 1

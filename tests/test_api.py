"""Every API endpoint against the small warehouse."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(small_env, tmp_path_factory):
    from pulseiq.ml.pipeline import run_training
    from pulseiq.services import db

    db.reset()
    import duckdb

    from pulseiq.config import get_settings

    s = get_settings()
    with duckdb.connect(str(s.warehouse_path), read_only=True) as con:
        run_training(con, s.artifacts_dir / "ml")
    db.reset()
    from pulseiq.api.app import app

    yield TestClient(app)
    db.reset()


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["model_version"]


def test_kpis_and_filters(client):
    r = client.get("/api/v1/kpis")
    assert r.status_code == 200
    names = [k["name"] for k in r.json()["kpis"]]
    assert {"Avg DAU", "MAU", "Stickiness", "Net revenue"} <= set(names)
    assert (
        client.get("/api/v1/kpis?platform=ios&channel=referral&country_tier=high").status_code
        == 200
    )
    assert client.get("/api/v1/kpis?platform=xbox").status_code == 422
    assert client.get("/api/v1/kpis?start=2025-02-10&end=2025-02-01").status_code == 422


def test_funnel(client):
    r = client.get("/api/v1/funnel?by=channel")
    assert r.status_code == 200
    stages = r.json()["stages"]
    assert [s["stage"] for s in stages] == ["Signed up", "Onboarded", "Trial", "Paid"]
    assert stages[0]["users"] >= stages[-1]["users"]
    assert r.json()["biggest_drop"]
    assert len(r.json()["segments"]) == 5


def test_retention_and_revenue(client):
    cells = client.get("/api/v1/retention/cohorts").json()["cells"]
    assert cells and all(
        c["retention_rate"] is None or 0 <= c["retention_rate"] <= 1 for c in cells
    )
    rows = client.get("/api/v1/revenue/daily").json()["rows"]
    assert rows and {"net_usd", "mrr_usd", "arppu_usd"} <= set(rows[0])


def test_experiments(client):
    lst = client.get("/api/v1/experiments").json()
    assert {e["experiment_id"] for e in lst} == {
        "onboarding_flow_v2",
        "paywall_redesign",
        "streak_reminder",
    }
    rep = client.get("/api/v1/experiments/paywall_redesign").json()
    assert rep["decision"] in ("SHIP", "DON'T SHIP", "KEEP RUNNING", "INVESTIGATE")
    assert client.get("/api/v1/experiments/nope").status_code == 404
    r = client.post(
        "/api/v1/experiments/paywall_redesign/analyze", json={"cuped": False, "bayesian": False}
    )
    assert r.status_code == 200 and r.json()["cuped_status"] == "disabled by option"


def test_power(client):
    r = client.post("/api/v1/power", json={"baseline": 0.1, "mde": 0.02})
    assert r.status_code == 200 and 3800 <= r.json()["n_per_arm"] <= 3900
    r = client.post("/api/v1/power", json={"baseline": 0.1, "n_per_arm": 3841})
    assert abs(r.json()["mde"] - 0.02) < 0.001
    assert client.post("/api/v1/power", json={"baseline": 0.1}).status_code == 422
    assert client.post("/api/v1/power", json={"baseline": 1.5, "mde": 0.1}).status_code == 422


def test_predictions(client, small_con):
    uid = small_con.execute(
        "select user_id from dim_users order by signup_ts desc limit 1"
    ).fetchone()[0]
    r = client.get(f"/api/v1/predictions/users/{uid}")
    assert r.status_code == 200 and 0 <= r.json()["p_retained_d30"] <= 1
    assert client.get("/api/v1/predictions/users/u_missing").status_code == 404
    risk = client.get("/api/v1/predictions/at-risk?limit=10").json()
    assert len(risk) <= 10


def test_ask(client):
    r = client.post(
        "/api/v1/ask", json={"question": "How many users signed up?", "provider": "offline"}
    )
    assert r.status_code == 200 and r.json()["rows"]
    bad = client.post(
        "/api/v1/ask", json={"question": "delete the users table", "provider": "mock"}
    ).json()
    assert bad["refused"]
    assert client.post("/api/v1/ask", json={"question": "x"}).status_code == 422

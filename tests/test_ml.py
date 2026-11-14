"""Retention ML pipeline on the small warehouse (+ full-size driver recovery)."""

from __future__ import annotations

import json

import duckdb
import pytest

from pulseiq.ml.pipeline import run_survival, run_training
from pulseiq.ml.predict import load_model, predict_user, score_recent
from pulseiq.ml.split import time_split


@pytest.fixture(scope="module")
def trained(small_con, tmp_path_factory):
    out = tmp_path_factory.mktemp("ml")
    meta = run_training(small_con, out)
    return out, meta


def test_model_beats_baselines(trained):
    _, meta = trained
    m = meta["metrics_test"]
    best = m[meta["model"]]
    assert best["pr_auc"] > m["majority_baseline"]["pr_auc"]
    assert best["pr_auc"] > m["active_days_heuristic"]["pr_auc"]
    assert best["recall"] > 0
    assert m["majority_baseline"]["recall"] == 0  # the v1 failure mode, reproduced


def test_time_split_is_ordered(small_con):
    from pulseiq.ml.features import load_feature_frame

    f = load_feature_frame(small_con)
    s = time_split(f)
    assert f.loc[s.train, "signup_ts"].max() <= f.loc[s.valid, "signup_ts"].min()
    assert f.loc[s.valid, "signup_ts"].max() <= f.loc[s.test, "signup_ts"].min()


def test_artifacts_and_predict(trained, small_con):
    out, meta = trained
    for f in (
        "model.joblib",
        "model_meta.json",
        "threshold_table.json",
        "permutation_importance.csv",
    ):
        assert (out / f).exists()
    assert {"git_sha", "sklearn_version", "threshold", "features", "split"} <= set(meta)
    load_model.cache_clear()
    uid = small_con.execute("select user_id from dim_users limit 1").fetchone()[0]
    pred = predict_user(small_con, uid, out)
    assert 0 <= pred["p_retained_d30"] <= 1
    assert pred["risk_band"] in ("high", "medium", "low")
    assert predict_user(small_con, "nope", out) is None
    recent = score_recent(small_con, out)
    assert not recent.empty


def test_survival_runs(small_con, tmp_path):
    res = run_survival(small_con, tmp_path)
    assert res["churn_events"] > 0
    hr = {c["feature"]: c["hazard_ratio"] for c in res["cox"]}
    assert hr["reminder_set_any"] < 1  # reminders protect against churn


@pytest.mark.slow
def test_full_size_drivers_recovered(full_env, tmp_path):
    from pulseiq.validation import write_ml_validation

    truth = json.loads((full_env / "raw" / "ground_truth.json").read_text())
    with duckdb.connect(str(full_env / "warehouse" / "pulseiq.duckdb"), read_only=True) as con:
        meta = run_training(con, tmp_path)
    summary = write_ml_validation(meta, truth, tmp_path / "ml_validation.md")
    assert summary["beats_baselines"]
    assert summary["all_explicit_drivers_recovered"], summary["top5_features"]

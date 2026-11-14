"""Score users with the saved retention model (used by API and dashboard)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd

from .explain import contributions
from .features import load_feature_frame, to_matrix


@lru_cache(maxsize=4)
def load_model(ml_dir: str) -> tuple[object, dict]:
    """Load (model, meta) from ``artifacts/ml`` (cached per process)."""
    path = Path(ml_dir)
    meta = json.loads((path / "model_meta.json").read_text())
    return joblib.load(path / "model.joblib"), meta


def raw_scores(model, X) -> np.ndarray:
    """Uncalibrated ranking score (the calibrated model wraps a ``base`` estimator)."""
    base = getattr(model, "base", model)
    return base.predict_proba(X)[:, 1]


def risk_band(p: float, raw: float, meta: dict) -> str:
    """'high' risk (bottom 20 % by score), 'low' (P >= F1 threshold) or 'medium'."""
    if raw < meta["risk_cut"]:
        return "high"
    if p >= meta["threshold"]:
        return "low"
    return "medium"


def predict_user(con: duckdb.DuckDBPyConnection, user_id: str, ml_dir: Path) -> dict | None:
    """P(D30 retained), risk band and top contributing features for one user."""
    model, meta = load_model(str(ml_dir))
    frame = load_feature_frame(con, [user_id], eligible_only=False)
    if frame.empty:
        return None
    X = to_matrix(frame, meta["features"])
    p = float(model.predict_proba(X)[:, 1][0])
    raw = float(raw_scores(model, X)[0])
    bg = pd.Series(meta["background_mean"]).reindex(X.columns).fillna(0.0)
    return {
        "user_id": user_id,
        "signup_ts": str(frame["signup_ts"].iloc[0]),
        "p_retained_d30": p,
        "risk_band": risk_band(p, raw, meta),
        "threshold": meta["threshold"],
        "risk_cut": meta["risk_cut"],
        "top_contributions": contributions(model, X, bg),
        "model": meta["model"],
    }


def score_recent(con: duckdb.DuckDBPyConnection, ml_dir: Path, days: int = 14) -> pd.DataFrame:
    """Score every user who signed up in the last ``days`` days (72 h features complete)."""
    model, meta = load_model(str(ml_dir))
    ids = [
        r[0]
        for r in con.execute(
            "select user_id from dim_users, int_data_window w "
            "where signup_ts >= w.data_end - to_days(?) and signup_ts + interval 72 hour <= w.data_end",
            [days],
        ).fetchall()
    ]
    if not ids:
        return pd.DataFrame()
    frame = load_feature_frame(con, ids, eligible_only=False)
    X = to_matrix(frame, meta["features"])
    frame["p_retained_d30"] = model.predict_proba(X)[:, 1]
    raw = raw_scores(model, X)
    frame["risk_band"] = [
        risk_band(p, r, meta) for p, r in zip(frame["p_retained_d30"], raw, strict=True)
    ]
    cols = [
        "user_id",
        "signup_ts",
        "platform",
        "acquisition_channel",
        "country_tier",
        "active_days_72h",
        "sessions_72h",
        "reminder_set_72h",
        "workout_log_72h",
        "p_retained_d30",
        "risk_band",
    ]
    return frame[cols].sort_values("p_retained_d30").reset_index(drop=True)

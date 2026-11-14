"""Retention-model scoring for single users and the at-risk list."""

from __future__ import annotations

import json

import pandas as pd

from pulseiq.config import get_settings
from pulseiq.ml.predict import predict_user, score_recent

from .db import cached, cursor


def _ml_dir():
    d = get_settings().artifacts_dir / "ml"
    if not (d / "model.joblib").exists():
        raise FileNotFoundError("No trained model; run `pulseiq train`.")
    return d


def model_meta() -> dict:
    """Saved model metadata (metrics, threshold, features, charts)."""
    return json.loads((_ml_dir() / "model_meta.json").read_text())


def threshold_table() -> pd.DataFrame:
    """Precomputed precision / recall / contacted share by threshold (test set)."""
    return pd.read_json(_ml_dir() / "threshold_table.json")


def score_user(user_id: str) -> dict | None:
    """Probability of D30 retention, risk band and top contributions (None if unknown)."""
    with cursor() as cur:
        return predict_user(cur, user_id, _ml_dir())


@cached
def at_risk(limit: int = 100, days: int = 14) -> pd.DataFrame:
    """Highest-risk recent signups (lowest P(retained))."""
    with cursor() as cur:
        df = score_recent(cur, _ml_dir(), days=days)
    return df.head(limit)

"""Model zoo: baselines, logistic regression and gradient boosting (+ calibration)."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SEED = 42


class MajorityBaseline:
    """Predicts the training positive rate for everyone (always 'not retained')."""

    def fit(self, X, y):  # noqa: ARG002
        self.rate_ = float(np.mean(y))
        return self

    def predict_proba(self, X):
        p = np.full(len(X), self.rate_)
        return np.column_stack([1 - p, p])


class ActiveDaysHeuristic:
    """One-rule heuristic: retained if active on >= 2 of the first 3 days.

    Scores are the training retention rate of each active-days level, so the rule can
    also be ranked (for PR-AUC); the hard rule is score >= rate at 2 days.
    """

    feature = "active_days_72h"

    def fit(self, X, y):
        df = pd.DataFrame({"d": X[self.feature].to_numpy(), "y": np.asarray(y)})
        self.rates_ = df.groupby("d")["y"].mean().to_dict()
        self.default_ = float(np.mean(y))
        return self

    def predict_proba(self, X):
        p = np.array([self.rates_.get(d, self.default_) for d in X[self.feature].to_numpy()])
        return np.column_stack([1 - p, p])

    def predict(self, X):
        return (X[self.feature].to_numpy() >= 2).astype(int)


class CalibratedModel:
    """A fitted classifier followed by isotonic calibration fitted on validation."""

    def __init__(self, base, iso: IsotonicRegression):
        self.base = base
        self.iso = iso

    def predict_proba(self, X):
        p = self.iso.predict(self.base.predict_proba(X)[:, 1])
        return np.column_stack([1 - p, p])


@dataclass
class TrainedModel:
    """A tuned model with its validation search log."""

    name: str
    model: object
    params: dict
    valid_pr_auc: float
    search: list[dict] = field(default_factory=list)


def _pr_auc(model, X, y) -> float:
    return float(average_precision_score(y, model.predict_proba(X)[:, 1]))


def train_logistic(X_tr, y_tr, X_va, y_va) -> TrainedModel:
    """Standardised, class-balanced logistic regression; C tuned on validation PR-AUC."""
    search, best = [], None
    for c in (0.01, 0.1, 1.0, 10.0):
        m = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=c, class_weight="balanced", max_iter=2000, random_state=SEED),
        ).fit(X_tr, y_tr)
        score = _pr_auc(m, X_va, y_va)
        search.append({"C": c, "valid_pr_auc": score})
        if best is None or score > best[0]:
            best = (score, m, {"C": c})
    return TrainedModel("logistic_regression", best[1], best[2], best[0], search)


def train_hgb(X_tr, y_tr, X_va, y_va) -> TrainedModel:
    """HistGradientBoosting with balanced class weights; small grid on validation PR-AUC."""
    grid = list(product((0.05, 0.1), (3, 6), (15, 31), (0.0, 1.0)))
    search, best = [], None
    for lr, depth, leaves, l2 in grid:
        m = HistGradientBoostingClassifier(
            learning_rate=lr,
            max_depth=depth,
            max_leaf_nodes=leaves,
            l2_regularization=l2,
            max_iter=300,
            early_stopping=True,
            validation_fraction=0.1,
            class_weight="balanced",
            random_state=SEED,
        ).fit(X_tr, y_tr)
        score = _pr_auc(m, X_va, y_va)
        params = {
            "learning_rate": lr,
            "max_depth": depth,
            "max_leaf_nodes": leaves,
            "l2_regularization": l2,
        }
        search.append({**params, "valid_pr_auc": score})
        if best is None or score > best[0]:
            best = (score, m, params)
    return TrainedModel("hist_gradient_boosting", best[1], best[2], best[0], search)


def calibrate(model, X_va, y_va) -> CalibratedModel:
    """Isotonic calibration on validation (class weighting distorts raw probabilities)."""
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.001, y_max=0.999)
    iso.fit(model.predict_proba(X_va)[:, 1], y_va)
    return CalibratedModel(model, iso)

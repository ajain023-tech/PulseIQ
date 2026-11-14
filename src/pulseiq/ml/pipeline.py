"""End-to-end training and survival pipelines (``pulseiq train`` / ``pulseiq survival``)."""

from __future__ import annotations

import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
import sklearn

from . import evaluate as ev
from .explain import permutation_importances, plot_importance, shap_summary
from .features import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET,
    TARGET_DEFINITION,
    load_feature_frame,
    to_matrix,
)
from .split import class_balance, time_split
from .survival import churn_durations, cox_model, kaplan_meier
from .train import ActiveDaysHeuristic, MajorityBaseline, calibrate, train_hgb, train_logistic


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _fairness(y: np.ndarray, prob: np.ndarray, threshold: float, groups: pd.Series) -> list[dict]:
    rows = []
    for g in sorted(groups.unique()):
        m = (groups == g).to_numpy()
        pos = y[m] == 1
        pred = prob[m] >= threshold
        rows.append(
            {
                "group": str(g),
                "n": int(m.sum()),
                "positive_rate": float(y[m].mean()),
                "recall": float(pred[pos].mean()) if pos.any() else float("nan"),
                "precision": float(y[m][pred].mean()) if pred.any() else float("nan"),
            }
        )
    return rows


def run_training(con: duckdb.DuckDBPyConnection, out: Path) -> dict:
    """Features -> time split -> train -> calibrate -> evaluate -> explain -> save."""
    out.mkdir(parents=True, exist_ok=True)
    frame = load_feature_frame(con)
    split = time_split(frame)
    X = to_matrix(frame)
    y = frame[TARGET].to_numpy()
    Xtr, Xva, Xte = X.loc[split.train], X.loc[split.valid], X.loc[split.test]
    ytr, yva, yte = y[split.train], y[split.valid], y[split.test]

    majority = MajorityBaseline().fit(Xtr, ytr)
    heuristic = ActiveDaysHeuristic().fit(Xtr, ytr)
    lr = train_logistic(Xtr, ytr, Xva, yva)
    hgb = train_hgb(Xtr, ytr, Xva, yva)
    best = max((lr, hgb), key=lambda m: m.valid_pr_auc)
    calibrated = {m.name: calibrate(m.model, Xva, yva) for m in (lr, hgb)}

    thresholds, risk_cuts, results, test_scores = {}, {}, {}, {}
    for name, rank_model, prob_model in (
        ("majority_baseline", majority, majority),
        ("active_days_heuristic", heuristic, heuristic),
        ("logistic_regression", lr.model, calibrated["logistic_regression"]),
        ("hist_gradient_boosting", hgb.model, calibrated["hist_gradient_boosting"]),
    ):
        p_va = prob_model.predict_proba(Xva)[:, 1]
        if name == "majority_baseline":
            thr = 0.5
        elif name == "active_days_heuristic":
            thr = heuristic.rates_.get(2, 0.5)
        else:
            thr = ev.best_f1_threshold(yva, p_va)
        thresholds[name] = thr
        risk_cuts[name] = float(np.quantile(rank_model.predict_proba(Xva)[:, 1], ev.CAMPAIGN_SHARE))
        rank = rank_model.predict_proba(Xte)[:, 1]
        prob = prob_model.predict_proba(Xte)[:, 1]
        test_scores[name] = rank
        res = ev.evaluate_scores(yte, rank, prob, thr, risk_cuts[name])
        res["accuracy"] = float(((prob >= thr).astype(int) == yte).mean())
        res["valid_pr_auc"] = float(
            ev.average_precision_score(yva, rank_model.predict_proba(Xva)[:, 1])
        )
        results[name] = res

    best_cal = calibrated[best.name]
    p_te = best_cal.predict_proba(Xte)[:, 1]
    charts = ev.plot_pr_roc(yte, test_scores, out)
    charts["calibration"] = ev.plot_calibration(yte, best.model.predict_proba(Xte)[:, 1], p_te, out)
    charts["confusion_matrix"] = ev.plot_confusion(
        results[best.name]["confusion"], thresholds[best.name], out
    )
    charts["gain_chart"] = ev.plot_gain(yte, test_scores[best.name], out)

    imp = permutation_importances(best.model, Xte, yte)
    imp.to_csv(out / "permutation_importance.csv", index=False)
    charts["permutation_importance"] = plot_importance(imp, out)
    shap_path = (
        shap_summary(best.model, Xte, out) if best.name == "hist_gradient_boosting" else None
    )
    if shap_path:
        charts["shap_summary"] = shap_path

    test_frame = frame.loc[split.test]
    fairness = {
        dim: _fairness(yte, p_te, thresholds[best.name], test_frame[dim])
        for dim in ("platform", "country_tier")
    }
    (out / "threshold_table.json").write_text(json.dumps(ev.threshold_table(yte, p_te), indent=2))

    joblib.dump(best_cal, out / "model.joblib")
    meta = {
        "model": best.name,
        "params": best.params,
        "calibration": "isotonic (fitted on validation)",
        "features": list(X.columns),
        "numeric_features": list(NUMERIC_FEATURES) + ["reminder_set_any_72h"],
        "categorical_features": list(CATEGORICAL_FEATURES),
        "target": TARGET,
        "target_definition": TARGET_DEFINITION,
        "threshold": thresholds[best.name],
        "threshold_rule": "maximises F1 for the retained class on validation",
        "risk_cut": risk_cuts[best.name],
        "risk_cut_rule": "20th percentile of the uncalibrated validation score: users below it form the at-risk campaign band",
        "split": split.boundaries,
        "class_balance": class_balance(frame, split, TARGET),
        "metrics_test": results,
        "search": {"logistic_regression": lr.search, "hist_gradient_boosting": hgb.search},
        "fairness": fairness,
        "top_features": imp.head(10).to_dict(orient="records"),
        "charts": charts,
        "background_mean": X.loc[split.train].mean().to_dict(),
        "git_sha": _git_sha(),
        "sklearn_version": sklearn.__version__,
        "python_version": platform.python_version(),
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (out / "model_meta.json").write_text(json.dumps(meta, indent=2, default=float))
    (out / "metrics.json").write_text(json.dumps(results, indent=2))
    return meta


def run_survival(con: duckdb.DuckDBPyConnection, out: Path) -> dict:
    """Kaplan-Meier by segment, log-rank tests and a Cox model."""
    out.mkdir(parents=True, exist_ok=True)
    d = churn_durations(con)
    result = {
        "churn_definition": "no session for 14 consecutive days; churn day = last active day before the gap",
        "n_users": int(len(d)),
        "churn_events": int(d["event"].sum()),
        "censored": int((d["event"] == 0).sum()),
        "km": [
            kaplan_meier(d, by, out)
            for by in ("acquisition_channel", "platform", "onboarding_variant")
        ],
        "cox": cox_model(d),
    }
    (out / "survival.json").write_text(json.dumps(result, indent=2))
    return result

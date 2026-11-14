"""Explainability: permutation importance (always) and SHAP (if installed)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402


def permutation_importances(
    model, X: pd.DataFrame, y: np.ndarray, seed: int = 42, max_rows: int = 6000
) -> pd.DataFrame:
    """Drop in test PR-AUC when each feature is shuffled (mean ± std over 5 repeats)."""
    if len(X) > max_rows:
        idx = np.random.default_rng(seed).choice(len(X), max_rows, replace=False)
        X, y = X.iloc[idx], y[idx]
    r = permutation_importance(
        model, X, y, scoring="average_precision", n_repeats=5, random_state=seed, n_jobs=1
    )
    return (
        pd.DataFrame(
            {"feature": X.columns, "importance": r.importances_mean, "std": r.importances_std}
        )
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )


def plot_importance(imp: pd.DataFrame, out: Path, top: int = 15) -> str:
    """Horizontal bar chart of the top permutation importances."""
    d = imp.head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 0.32 * len(d) + 1.2))
    ax.barh(d["feature"], d["importance"], xerr=d["std"], color="#0072B2")
    ax.set_xlabel("Drop in PR-AUC when shuffled")
    ax.set_title("Permutation importance (test)", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    path = out / "permutation_importance.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path)


def shap_summary(
    model, X: pd.DataFrame, out: Path, seed: int = 42, max_rows: int = 2000
) -> str | None:
    """SHAP beeswarm for tree models; returns None if SHAP is unavailable or fails."""
    try:
        import shap
    except ImportError:
        return None
    try:
        sample = X.sample(min(max_rows, len(X)), random_state=seed)
        explainer = shap.TreeExplainer(model)
        values = explainer.shap_values(sample)
        if isinstance(values, list):
            values = values[1]
        shap.summary_plot(values, sample, show=False, max_display=15)
        path = out / "shap_summary.png"
        plt.gcf().set_size_inches(8, 6)
        plt.tight_layout()
        plt.savefig(path, dpi=150)
        plt.close("all")
        return str(path)
    except Exception:  # noqa: BLE001 - optional explainer; never fail training
        plt.close("all")
        return None


def contributions(model, x_row: pd.DataFrame, background: pd.Series, top: int = 5) -> list[dict]:
    """Model-agnostic local explanation for one user (occlusion against the mean user).

    For each feature, replace the user's value with the population mean and measure how
    much the predicted probability changes. Positive = the feature raises P(retained).
    """
    base = float(model.predict_proba(x_row)[:, 1][0])
    rows = []
    for col in x_row.columns:
        if x_row[col].iloc[0] == background[col]:
            continue
        alt = x_row.copy()
        alt[col] = background[col]
        delta = base - float(model.predict_proba(alt)[:, 1][0])
        if delta != 0:
            rows.append({"feature": col, "value": float(x_row[col].iloc[0]), "effect": delta})
    rows.sort(key=lambda r: -abs(r["effect"]))
    return rows[:top]

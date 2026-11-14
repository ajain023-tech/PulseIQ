"""Metrics, threshold selection and evaluation charts for the retention model."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.calibration import calibration_curve  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)

BLUE, ORANGE, GREEN, VERMILLION, GREY, PURPLE = (
    "#0072B2",
    "#E69F00",
    "#009E73",
    "#D55E00",
    "#7F7F7F",
    "#CC79A7",
)
CAMPAIGN_SHARE = 0.20


def recall_at_top(y: np.ndarray, score: np.ndarray, share: float) -> float:
    """Share of all positives found in the top ``share`` of scores."""
    k = max(1, int(round(share * len(y))))
    top = np.argsort(-score, kind="mergesort")[:k]
    return float(y[top].sum() / max(y.sum(), 1))


def lift_at_top(y: np.ndarray, score: np.ndarray, share: float = 0.10) -> float:
    """Positive rate in the top ``share`` divided by the overall positive rate."""
    k = max(1, int(round(share * len(y))))
    top = np.argsort(-score, kind="mergesort")[:k]
    return float(y[top].mean() / max(y.mean(), 1e-12))


def best_f1_threshold(y: np.ndarray, p: np.ndarray) -> float:
    """Probability threshold that maximises F1 for the positive class (on validation)."""
    prec, rec, thr = precision_recall_curve(y, p)
    f1 = 2 * prec[:-1] * rec[:-1] / np.maximum(prec[:-1] + rec[:-1], 1e-12)
    return float(thr[int(np.argmax(f1))])


def evaluate_scores(
    y: np.ndarray, rank_score: np.ndarray, prob: np.ndarray, threshold: float, risk_cut: float
) -> dict:
    """All test metrics for one model.

    ``rank_score`` drives ranking metrics (PR-AUC, ROC-AUC, recall@k, lift);
    ``prob`` are calibrated probabilities (Brier, thresholded metrics).
    ``risk_cut`` is the *ranking score* below which a user is in the campaign's at-risk
    band (ranking scores avoid the ties isotonic calibration creates).
    """
    pred = (prob >= threshold).astype(int)
    at_risk = rank_score < risk_cut
    churn = 1 - y
    return {
        "pr_auc": float(average_precision_score(y, rank_score)),
        "roc_auc": float(roc_auc_score(y, rank_score)) if len(np.unique(rank_score)) > 1 else 0.5,
        "brier": float(brier_score_loss(y, prob)),
        "threshold": float(threshold),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "recall_at_top20": recall_at_top(y, rank_score, CAMPAIGN_SHARE),
        "lift_at_top_decile": lift_at_top(y, rank_score, 0.10),
        "campaign_contacted_share": float(at_risk.mean()),
        "campaign_churn_rate_contacted": float(churn[at_risk].mean())
        if at_risk.any()
        else float("nan"),
        "campaign_churners_caught": float(churn[at_risk].sum() / max(churn.sum(), 1)),
        "confusion": confusion_matrix(y, pred, labels=[0, 1]).tolist(),
    }


def _save(fig, path: Path) -> str:
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path)


def plot_pr_roc(y: np.ndarray, scores: dict[str, np.ndarray], out: Path) -> dict[str, str]:
    """PR and ROC curves for every model on test."""
    colors = [GREY, ORANGE, BLUE, GREEN, PURPLE]
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    for (name, s), c in zip(scores.items(), colors, strict=False):
        prec, rec, _ = precision_recall_curve(y, s)
        # Drop sklearn's artificial (recall=0, precision=1) end point: for constant or
        # few-valued scores it draws a misleading straight line to the top-left corner.
        prec, rec = prec[:-1], rec[:-1]
        label = f"{name} (AP {average_precision_score(y, s):.3f})"
        if len(rec) <= 2:
            ax.plot(rec, prec, "o", color=c, ms=7, label=label)
        else:
            ax.step(rec, prec, where="post", color=c, lw=1.8, label=label)
    ax.axhline(y.mean(), color="black", ls=":", lw=1, label=f"prevalence {y.mean():.3f}")
    ax.set(
        xlabel="Recall (retained users found)",
        ylabel="Precision",
        title="Precision-recall on test (D30 retention)",
    )
    ax.legend(fontsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    pr = _save(fig, out / "pr_curve.png")
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    for (name, s), c in zip(scores.items(), colors, strict=False):
        fpr, tpr, _ = roc_curve(y, s)
        ax.plot(fpr, tpr, color=c, lw=1.8, label=f"{name} (AUC {roc_auc_score(y, s):.3f})")
    ax.plot([0, 1], [0, 1], color="black", ls=":", lw=1)
    ax.set(xlabel="False positive rate", ylabel="True positive rate", title="ROC on test")
    ax.legend(fontsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    roc = _save(fig, out / "roc_curve.png")
    return {"pr_curve": pr, "roc_curve": roc}


def plot_calibration(y: np.ndarray, raw: np.ndarray, cal: np.ndarray, out: Path) -> str:
    """Reliability diagram before and after isotonic calibration."""
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    for p, c, lab in ((raw, ORANGE, "raw (class-weighted)"), (cal, BLUE, "isotonic-calibrated")):
        frac, mean = calibration_curve(y, p, n_bins=10, strategy="quantile")
        ax.plot(mean, frac, "o-", color=c, label=f"{lab} — Brier {brier_score_loss(y, p):.4f}")
    ax.plot([0, 1], [0, 1], color="black", ls=":", lw=1)
    ax.set(
        xlabel="Predicted probability", ylabel="Observed D30 retention", title="Calibration on test"
    )
    ax.legend(fontsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    return _save(fig, out / "calibration.png")


def plot_confusion(cm: list[list[int]], threshold: float, out: Path) -> str:
    """Confusion matrix at the chosen threshold."""
    cm_ = np.array(cm)
    fig, ax = plt.subplots(figsize=(4.2, 3.8))
    ax.imshow(cm_, cmap="Blues")
    for (i, j), v in np.ndenumerate(cm_):
        ax.text(j, i, f"{v:,}", ha="center", va="center", color="black", fontsize=11)
    ax.set_xticks([0, 1], ["pred churned", "pred retained"])
    ax.set_yticks([0, 1], ["churned", "retained"])
    ax.set_title(f"Confusion matrix (threshold {threshold:.3f})", fontsize=10)
    return _save(fig, out / "confusion_matrix.png")


def plot_gain(y: np.ndarray, score: np.ndarray, out: Path) -> str:
    """Cumulative gain: share of retained users captured vs share of users contacted."""
    order = np.argsort(-score, kind="mergesort")
    gain = np.concatenate([[0], np.cumsum(y[order]) / max(y.sum(), 1)])
    x = np.linspace(0, 1, len(gain))
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    ax.plot(x, gain, color=BLUE, lw=2, label="model")
    ax.plot([0, 1], [0, 1], color="black", ls=":", lw=1, label="random")
    ax.axvline(CAMPAIGN_SHARE, color=ORANGE, ls="--", lw=1, label="20 % contacted")
    ax.set(
        xlabel="Share of users (ranked by P(retained))",
        ylabel="Share of retained users captured",
        title="Cumulative gain on test",
    )
    ax.legend(fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    return _save(fig, out / "gain_chart.png")


def threshold_table(y: np.ndarray, prob: np.ndarray) -> list[dict]:
    """Precision / recall / contacted share across thresholds (for the dashboard slider)."""
    rows = []
    churn = 1 - y
    for t in np.round(np.linspace(0.02, 0.6, 59), 3):
        pred = prob >= t
        at_risk = ~pred
        rows.append(
            {
                "threshold": float(t),
                "precision": float(y[pred].mean()) if pred.any() else float("nan"),
                "recall": float(y[pred].sum() / max(y.sum(), 1)),
                "predicted_retained_share": float(pred.mean()),
                "at_risk_share": float(at_risk.mean()),
                "churners_caught": float(churn[at_risk].sum() / max(churn.sum(), 1)),
                "churn_rate_in_at_risk": float(churn[at_risk].mean())
                if at_risk.any()
                else float("nan"),
            }
        )
    return rows

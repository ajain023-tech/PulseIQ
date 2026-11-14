"""Static PNG charts for experiment reports (matplotlib, colour-blind-safe)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy import stats  # noqa: E402

if TYPE_CHECKING:
    from .report import ExperimentReport

# Okabe-Ito palette
BLUE, ORANGE, GREEN, VERMILLION, GREY = "#0072B2", "#E69F00", "#009E73", "#D55E00", "#7F7F7F"


def _style(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=0.25)


def forest_plot(r: ExperimentReport, path: Path) -> Path:
    """Relative lift with 95 % CI per metric (decision estimate)."""
    rows = []
    for m in r.metrics:
        base = m.value_control if m.value_control else np.nan
        if not base or np.isnan(base):
            continue
        lo, hi = m.decision_ci
        rows.append(
            (
                m.label + (" (CUPED)" if m.cuped_used else ""),
                m.decision_diff / base,
                lo / base,
                hi / base,
                m.role,
            )
        )
    fig, ax = plt.subplots(figsize=(8, 0.5 * len(rows) + 1.4))
    for i, (_label, est, lo, hi, role) in enumerate(rows[::-1]):
        color = {"primary": BLUE, "guardrail": ORANGE}.get(role, GREY)
        ax.errorbar(
            est * 100,
            i,
            xerr=[[100 * (est - lo)], [100 * (hi - est)]],
            fmt="o",
            color=color,
            capsize=3,
        )
    ax.set_yticks(range(len(rows)), [r_[0] + f"  [{r_[4]}]" for r_ in rows[::-1]], fontsize=8)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("Relative lift vs control (%) with 95 % CI")
    ax.set_title(f"{r.experiment_id}: metric lifts — decision {r.decision}", fontsize=10)
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def sequential_plot(r: ExperimentReport, path: Path) -> Path | None:
    """Cumulative lift with naive CI vs always-valid confidence sequence, and log Λ."""
    s = r.sequential
    if not s or not s.get("applicable"):
        return None
    x = np.arange(len(s["looks"]))
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
    a1.fill_between(
        x, s["cs_low"], s["cs_high"], color=BLUE, alpha=0.15, label="always-valid 95 % CS"
    )
    a1.plot(x, s["naive_ci_low"], color=ORANGE, lw=1, ls="--", label="naive 95 % CI")
    a1.plot(x, s["naive_ci_high"], color=ORANGE, lw=1, ls="--")
    a1.plot(x, s["diff"], color=BLUE, lw=1.8, label="cumulative lift")
    a1.axhline(0, color="black", lw=0.8)
    a1.set_ylabel(f"Δ {s['metric']}")
    a1.set_ylim(np.nanpercentile(s["cs_low"], 10), np.nanpercentile(s["cs_high"], 90))
    a1.legend(fontsize=8, loc="upper right")
    a1.set_title(f"{r.experiment_id}: cumulative lift over daily looks", fontsize=10)
    a2.plot(x, s["log_lambda"], color=GREEN, lw=1.8, label="log Λ (mSPRT)")
    a2.axhline(s["threshold_log"], color=VERMILLION, ls="--", label="reject boundary log(1/α)")
    a2.set_ylabel("log Λ")
    a2.set_xlabel("Look (assignment day)")
    a2.legend(fontsize=8, loc="upper left")
    for a in (a1, a2):
        a.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def posterior_plot(r: ExperimentReport, path: Path) -> Path | None:
    """Beta posteriors of the primary metric in each arm."""
    m = r.metrics[0]
    if not m.bayesian:
        return None
    (ac, bc), (at, bt) = m.bayesian["posterior_control"], m.bayesian["posterior_treatment"]
    lo = min(stats.beta.ppf(0.0005, ac, bc), stats.beta.ppf(0.0005, at, bt))
    hi = max(stats.beta.ppf(0.9995, ac, bc), stats.beta.ppf(0.9995, at, bt))
    xs = np.linspace(lo, hi, 400)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.plot(xs, stats.beta.pdf(xs, ac, bc), color=GREY, lw=2, label="control")
    ax.plot(xs, stats.beta.pdf(xs, at, bt), color=BLUE, lw=2, label="treatment")
    ax.set_title(
        f"{r.experiment_id}: posterior of {m.metric} — P(T > C) = {m.bayesian['prob_treatment_better']:.3f}",
        fontsize=10,
    )
    ax.set_xlabel(m.metric)
    ax.legend(fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def render_charts(r: ExperimentReport, out_dir: Path) -> dict[str, str]:
    """Render every chart for a report; returns name -> path."""
    out = {"forest": forest_plot(r, out_dir / "forest.png")}
    seq = sequential_plot(r, out_dir / "sequential.png")
    if seq:
        out["sequential"] = seq
    post = posterior_plot(r, out_dir / "posterior.png")
    if post:
        out["posterior"] = post
    return {k: str(v) for k, v in out.items()}


def peeking_plot(sim: dict, path: Path) -> Path:
    """Cumulative false-positive rate by look: naive peeking vs mSPRT (A/A)."""
    x = np.arange(1, sim["looks"] + 1)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(
        x,
        np.array(sim["cum_fpr_naive_by_look"]) * 100,
        color=VERMILLION,
        lw=2,
        label="naive p < 0.05 at any look",
    )
    ax.plot(
        x,
        np.array(sim["cum_fpr_sequential_by_look"]) * 100,
        color=BLUE,
        lw=2,
        label="mSPRT (always valid)",
    )
    ax.axhline(sim["alpha"] * 100, color="black", ls="--", lw=1, label="nominal α = 5 %")
    ax.set_xlabel("Number of daily looks")
    ax.set_ylabel("False-positive rate (%)")
    ax.set_title(
        f"A/A peeking simulation ({sim['n_sims']:,} tests): naive {sim['fpr_naive_peeking']:.1%} vs "
        f"sequential {sim['fpr_sequential']:.1%}",
        fontsize=10,
    )
    ax.legend(fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path

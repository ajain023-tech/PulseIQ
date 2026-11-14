"""CUPED variance reduction (Deng et al., 2013)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .frequentist import Readout, welch_readout


@dataclass
class CupedResult:
    """CUPED-adjusted readout plus diagnostics."""

    covariate: str
    theta: float
    correlation: float
    variance_reduction: float
    ci_width_raw: float
    ci_width_cuped: float
    ci_width_reduction: float
    readout: Readout


def cuped_adjust(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, float]:
    """Return ``(y_adj, theta)`` with theta = cov(y, x) / var(x) on pooled data."""
    var_x = np.var(x, ddof=1)
    if var_x == 0:
        return y.astype(float), 0.0
    theta = float(np.cov(y, x, ddof=1)[0, 1] / var_x)
    return y - theta * (x - x.mean()), theta


def cuped_readout(
    y_c: np.ndarray,
    x_c: np.ndarray,
    y_t: np.ndarray,
    x_t: np.ndarray,
    covariate: str,
    raw: Readout,
    alpha: float = 0.05,
) -> CupedResult:
    """Apply CUPED to both arms (pooled theta) and compare CI widths with ``raw``."""
    y = np.concatenate([y_c, y_t]).astype(float)
    x = np.concatenate([x_c, x_t]).astype(float)
    y_adj, theta = cuped_adjust(y, x)
    adj_c, adj_t = y_adj[: len(y_c)], y_adj[len(y_c) :]
    readout = welch_readout(adj_c, adj_t, alpha)
    # Report arm values on the original scale (adjusted means are shifted by theta*dx).
    readout.value_control = float(np.mean(adj_c))
    readout.value_treatment = float(np.mean(adj_t))
    readout.method = "CUPED + Welch t"
    var_y = np.var(y, ddof=1)
    vr = 1 - np.var(y_adj, ddof=1) / var_y if var_y > 0 else 0.0
    w_raw = raw.ci_high - raw.ci_low
    w_cuped = readout.ci_high - readout.ci_low
    corr = float(np.corrcoef(y, x)[0, 1]) if np.std(x) > 0 and np.std(y) > 0 else 0.0
    return CupedResult(
        covariate=covariate,
        theta=theta,
        correlation=corr,
        variance_reduction=float(vr),
        ci_width_raw=float(w_raw),
        ci_width_cuped=float(w_cuped),
        ci_width_reduction=float(1 - w_cuped / w_raw) if w_raw > 0 else 0.0,
        readout=readout,
    )

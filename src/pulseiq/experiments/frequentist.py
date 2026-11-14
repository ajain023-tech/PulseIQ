"""Fixed-horizon frequentist readouts for proportion and mean metrics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass
class Readout:
    """Two-arm comparison (treatment minus control)."""

    n_control: int
    n_treatment: int
    value_control: float
    value_treatment: float
    abs_diff: float
    ci_low: float
    ci_high: float
    p_value: float
    rel_lift: float | None
    rel_ci_low: float | None
    rel_ci_high: float | None
    method: str


def wilson_interval(successes: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score interval for one proportion."""
    if n == 0:
        return 0.0, 1.0
    z = stats.norm.ppf(1 - alpha / 2)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return float(centre - half), float(centre + half)


def newcombe_diff_ci(
    x_c: int, n_c: int, x_t: int, n_t: int, alpha: float = 0.05
) -> tuple[float, float]:
    """Newcombe (1998, method 10) hybrid-score CI for p_t - p_c."""
    p_c, p_t = x_c / n_c, x_t / n_t
    l_c, u_c = wilson_interval(x_c, n_c, alpha)
    l_t, u_t = wilson_interval(x_t, n_t, alpha)
    d = p_t - p_c
    lower = d - np.sqrt((p_t - l_t) ** 2 + (u_c - p_c) ** 2)
    upper = d + np.sqrt((u_t - p_t) ** 2 + (p_c - l_c) ** 2)
    return float(lower), float(upper)


def two_proportion_ztest(x_c: int, n_c: int, x_t: int, n_t: int) -> tuple[float, float]:
    """Pooled two-proportion z-test; returns ``(z, two-sided p)``."""
    p_pool = (x_c + x_t) / (n_c + n_t)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / n_c + 1 / n_t))
    if se == 0:
        return 0.0, 1.0
    z = (x_t / n_t - x_c / n_c) / se
    return float(z), float(2 * stats.norm.sf(abs(z)))


def relative_lift_ci(
    mean_c: float, var_mean_c: float, mean_t: float, var_mean_t: float, alpha: float = 0.05
) -> tuple[float | None, float | None, float | None]:
    """Relative lift t/c - 1 with a delta-method CI on the log ratio."""
    if mean_c <= 0 or mean_t <= 0:
        return None, None, None
    z = stats.norm.ppf(1 - alpha / 2)
    log_ratio = np.log(mean_t / mean_c)
    se = np.sqrt(var_mean_t / mean_t**2 + var_mean_c / mean_c**2)
    return (
        float(np.exp(log_ratio) - 1),
        float(np.exp(log_ratio - z * se) - 1),
        float(np.exp(log_ratio + z * se) - 1),
    )


def proportion_readout(x_c: int, n_c: int, x_t: int, n_t: int, alpha: float = 0.05) -> Readout:
    """Two-proportion readout: z-test p-value, Newcombe CI, delta-method relative CI."""
    p_c, p_t = x_c / n_c, x_t / n_t
    lo, hi = newcombe_diff_ci(x_c, n_c, x_t, n_t, alpha)
    _, p = two_proportion_ztest(x_c, n_c, x_t, n_t)
    rel, rlo, rhi = relative_lift_ci(p_c, p_c * (1 - p_c) / n_c, p_t, p_t * (1 - p_t) / n_t, alpha)
    return Readout(
        n_c, n_t, p_c, p_t, p_t - p_c, lo, hi, p, rel, rlo, rhi, "two-proportion z / Newcombe"
    )


def welch_readout(y_c: np.ndarray, y_t: np.ndarray, alpha: float = 0.05) -> Readout:
    """Welch's t-test and CI for a difference in means."""
    n_c, n_t = len(y_c), len(y_t)
    m_c, m_t = float(np.mean(y_c)), float(np.mean(y_t))
    v_c, v_t = float(np.var(y_c, ddof=1)), float(np.var(y_t, ddof=1))
    se2_c, se2_t = v_c / n_c, v_t / n_t
    se = np.sqrt(se2_c + se2_t)
    if se == 0:
        return Readout(n_c, n_t, m_c, m_t, m_t - m_c, 0.0, 0.0, 1.0, None, None, None, "Welch t")
    df = (se2_c + se2_t) ** 2 / (se2_c**2 / (n_c - 1) + se2_t**2 / (n_t - 1))
    t = (m_t - m_c) / se
    p = 2 * stats.t.sf(abs(t), df)
    q = stats.t.ppf(1 - alpha / 2, df)
    rel, rlo, rhi = relative_lift_ci(m_c, se2_c, m_t, se2_t, alpha)
    d = m_t - m_c
    return Readout(
        n_c, n_t, m_c, m_t, d, d - q * se, d + q * se, float(p), rel, rlo, rhi, "Welch t"
    )


def bootstrap_diff_ci(
    y_c: np.ndarray, y_t: np.ndarray, n_boot: int = 2000, alpha: float = 0.05, seed: int = 42
) -> tuple[float, float]:
    """Percentile bootstrap CI for mean(y_t) - mean(y_c) (vectorised, seeded)."""
    rng = np.random.default_rng(seed)
    idx_c = rng.integers(0, len(y_c), size=(n_boot, len(y_c)))
    idx_t = rng.integers(0, len(y_t), size=(n_boot, len(y_t)))
    diffs = y_t[idx_t].mean(axis=1) - y_c[idx_c].mean(axis=1)
    lo, hi = np.quantile(diffs, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)

"""Always-valid sequential testing: mixture SPRT (mSPRT) for a difference in means.

With a N(0, tau^2) mixing prior on the effect and the normal approximation
d_hat ~ N(theta, V), the mixture likelihood ratio against H0: theta = 0 is

    Lambda = sqrt(V / (V + tau^2)) * exp(tau^2 * d_hat^2 / (2 V (V + tau^2)))

(Johari et al., 2017). Rejecting the first time Lambda >= 1/alpha controls the
type-I error at alpha *no matter how often you look*. The always-valid p-value is
min over looks of 1/Lambda, and the matching confidence sequence is
d_hat +/- sqrt(V (V + tau^2) / tau^2 * (2 log(1/alpha) + log((V + tau^2) / V))).
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def msprt_lambda(d_hat: np.ndarray, var: np.ndarray, tau2: float) -> np.ndarray:
    """Mixture likelihood ratio (vectorised)."""
    var = np.maximum(var, 1e-300)
    log_lam = 0.5 * np.log(var / (var + tau2)) + tau2 * d_hat**2 / (2 * var * (var + tau2))
    return np.exp(np.minimum(log_lam, 700))


def confidence_sequence_halfwidth(var: np.ndarray, tau2: float, alpha: float = 0.05) -> np.ndarray:
    """Half-width of the always-valid (1 - alpha) confidence sequence."""
    var = np.maximum(var, 1e-300)
    return np.sqrt(var * (var + tau2) / tau2 * (2 * np.log(1 / alpha) + np.log((var + tau2) / var)))


def sequential_trace(
    x_c: np.ndarray,
    n_c: np.ndarray,
    x_t: np.ndarray,
    n_t: np.ndarray,
    tau2: float,
    alpha: float = 0.05,
) -> dict:
    """Cumulative look-by-look trace for proportions given cumulative counts per look."""
    p_c = x_c / np.maximum(n_c, 1)
    p_t = x_t / np.maximum(n_t, 1)
    pooled = (x_c + x_t) / np.maximum(n_c + n_t, 1)
    var = pooled * (1 - pooled) * (1 / np.maximum(n_c, 1) + 1 / np.maximum(n_t, 1))
    d = p_t - p_c
    lam = msprt_lambda(d, var, tau2)
    p_always = np.minimum.accumulate(np.minimum(1.0, 1.0 / lam))
    half = confidence_sequence_halfwidth(var, tau2, alpha)
    z = stats.norm.ppf(1 - alpha / 2)
    crossed = np.flatnonzero(lam >= 1 / alpha)
    return {
        "diff": d.tolist(),
        "naive_ci_low": (d - z * np.sqrt(var)).tolist(),
        "naive_ci_high": (d + z * np.sqrt(var)).tolist(),
        "cs_low": (d - half).tolist(),
        "cs_high": (d + half).tolist(),
        "log_lambda": np.log(lam).tolist(),
        "threshold_log": float(np.log(1 / alpha)),
        "always_valid_p": p_always.tolist(),
        "first_crossing_look": int(crossed[0]) if crossed.size else None,
        "tau2": tau2,
    }


def simulate_peeking(
    n_sims: int = 2000,
    looks: int = 30,
    users_per_look_per_arm: int = 200,
    baseline: float = 0.2,
    alpha: float = 0.05,
    tau: float = 0.02,
    seed: int = 42,
) -> dict:
    """A/A simulation: false-positive rates of fixed-horizon, naive peeking and mSPRT."""
    rng = np.random.default_rng(seed)
    xc = rng.binomial(users_per_look_per_arm, baseline, size=(n_sims, looks)).cumsum(axis=1)
    xt = rng.binomial(users_per_look_per_arm, baseline, size=(n_sims, looks)).cumsum(axis=1)
    n = users_per_look_per_arm * np.arange(1, looks + 1)[None, :]
    pc, pt = xc / n, xt / n
    pooled = (xc + xt) / (2 * n)
    var = pooled * (1 - pooled) * (2 / n)
    z = (pt - pc) / np.sqrt(np.maximum(var, 1e-300))
    reject_naive = np.abs(z) > stats.norm.ppf(1 - alpha / 2)
    lam = msprt_lambda(pt - pc, var, tau**2)
    reject_seq = lam >= 1 / alpha
    fpr_fixed = float(reject_naive[:, -1].mean())
    fpr_peek = float(reject_naive.any(axis=1).mean())
    fpr_seq = float(reject_seq.any(axis=1).mean())
    return {
        "n_sims": n_sims,
        "looks": looks,
        "users_per_look_per_arm": users_per_look_per_arm,
        "baseline": baseline,
        "alpha": alpha,
        "tau": tau,
        "fpr_fixed_horizon": fpr_fixed,
        "fpr_naive_peeking": fpr_peek,
        "fpr_sequential": fpr_seq,
        "cum_fpr_naive_by_look": reject_naive.cumsum(axis=1).astype(bool).mean(axis=0).tolist(),
        "cum_fpr_sequential_by_look": reject_seq.cumsum(axis=1).astype(bool).mean(axis=0).tolist(),
    }

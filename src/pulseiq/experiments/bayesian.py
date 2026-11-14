"""Beta-Binomial Bayesian readout for proportion metrics."""

from __future__ import annotations

import numpy as np


def beta_binomial_readout(
    x_c: int,
    n_c: int,
    x_t: int,
    n_t: int,
    draws: int = 100_000,
    seed: int = 42,
    prior_a: float = 1.0,
    prior_b: float = 1.0,
) -> dict:
    """Posterior summaries under independent Beta(prior_a, prior_b) priors.

    Returns P(treatment > control), the expected loss (in absolute rate) of
    shipping each arm, and 95 % credible intervals for the absolute and relative lift.
    """
    rng = np.random.default_rng(seed)
    pc = rng.beta(prior_a + x_c, prior_b + n_c - x_c, size=draws)
    pt = rng.beta(prior_a + x_t, prior_b + n_t - x_t, size=draws)
    diff = pt - pc
    rel = pt / pc - 1
    return {
        "prob_treatment_better": float(np.mean(pt > pc)),
        "expected_loss_ship_treatment": float(np.mean(np.maximum(pc - pt, 0))),
        "expected_loss_ship_control": float(np.mean(np.maximum(pt - pc, 0))),
        "abs_lift_mean": float(diff.mean()),
        "abs_lift_ci": [float(v) for v in np.quantile(diff, [0.025, 0.975])],
        "rel_lift_ci": [float(v) for v in np.quantile(rel, [0.025, 0.975])],
        "posterior_control": [prior_a + x_c, prior_b + n_c - x_c],
        "posterior_treatment": [prior_a + x_t, prior_b + n_t - x_t],
        "draws": draws,
    }

"""Experiment populations, assignment and exact ground-truth effects.

Truth is computed from the per-user *probabilities* the simulation uses (not from
the realised random outcomes), so it is the exact average treatment effect over the
experiment population. Estimators should cover it within their 95 % CI ~95 % of
the time.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq

from .lifecycle import p_alive_active, survival
from .params import ExperimentSpec, GeneratorParams

DAY = 86_400


def scaled_window(spec: ExperimentSpec, n_days: int) -> tuple[int, int]:
    """Scale the 120-day full-size window of ``spec`` to ``n_days``."""
    factor = n_days / 120.0
    return int(round(spec.start_day * factor)), int(round(spec.end_day * factor))


@dataclass
class SignupExperiment:
    """Assignment for an experiment that randomises new users at signup."""

    in_population: np.ndarray  # bool per user
    treatment: np.ndarray  # bool per user (meaningful where in_population)
    logged: np.ndarray  # bool per user: assignment row written to the log


def assign_at_signup(
    rng: np.random.Generator, signup_day: np.ndarray, window: tuple[int, int], allocation: float
) -> SignupExperiment:
    """Randomise users whose signup day falls in ``[start, end)``."""
    in_pop = (signup_day >= window[0]) & (signup_day < window[1])
    treatment = in_pop & (rng.random(signup_day.size) < allocation)
    return SignupExperiment(in_pop, treatment, in_pop.copy())


def plant_srm_bug(
    rng: np.random.Generator,
    exp: SignupExperiment,
    platform: np.ndarray,
    treatment_loss_share: float,
) -> int:
    """Drop Android treatment users from the assignment log (planted SRM bug).

    ``treatment_loss_share`` is the share of *all* treatment users that is lost; the
    loss is concentrated on Android. Returns the number of dropped rows.
    """
    treat = exp.in_population & exp.treatment
    android_treat = treat & (platform == "android")
    n_target = int(round(treatment_loss_share * treat.sum()))
    candidates = np.flatnonzero(android_treat)
    dropped = rng.choice(candidates, size=min(n_target, candidates.size), replace=False)
    exp.logged[dropped] = False
    return int(dropped.size)


def solve_paid_factor(
    p_onb_c: np.ndarray, p_onb_t: np.ndarray, p_trial: np.ndarray, p_paid: np.ndarray, pp: float
) -> float:
    """Factor f on P(paid | trial) for treatment so mean paid diff == ``pp`` exactly."""
    control = np.mean(p_onb_c * p_trial * p_paid)
    treat_base = np.mean(p_onb_t * p_trial * p_paid)
    return float((control + pp) / treat_base)


def solve_streak_multiplier(
    m: np.ndarray, z: np.ndarray, target_pp: float, params: GeneratorParams
) -> float:
    """Hazard multiplier r (< 1) for treatment so that mean D7 lift == target_pp."""
    act = params.activity
    pa = p_alive_active(z, act)
    base = np.mean(pa * survival(m, 7, act))

    def gap(r: float) -> float:
        return float(np.mean(pa * survival(m * r, 7, act)) - base - target_pp)

    return float(brentq(gap, 0.05, 1.0))


def retention_truth(
    m: np.ndarray, z: np.ndarray, r: float, days: tuple[int, ...], params: GeneratorParams
) -> dict[str, float]:
    """Exact mean lift in exact-day retention for hazard multiplier ``r``."""
    act = params.activity
    pa = p_alive_active(z, act)
    return {
        f"d{d}_retained": float(np.mean(pa * (survival(m * r, d, act) - survival(m, d, act))))
        for d in days
    }

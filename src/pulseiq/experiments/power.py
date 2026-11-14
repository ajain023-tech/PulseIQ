"""Power, minimum detectable effect and sample-size calculations (two proportions)."""

from __future__ import annotations

import math

from scipy import optimize, stats


def sample_size(
    baseline: float, mde: float, alpha: float = 0.05, power: float = 0.8, ratio: float = 1.0
) -> int:
    """Control-arm users needed to detect an absolute lift ``mde`` (two-sided test).

    ``ratio`` = n_treatment / n_control. Uses the standard normal-approximation
    formula with the pooled variance under H0 and unpooled variance under H1.
    """
    if mde == 0:
        raise ValueError("mde must be non-zero")
    p1, p2 = baseline, baseline + mde
    if not (0 < p1 < 1 and 0 < p2 < 1):
        raise ValueError("baseline and baseline + mde must lie in (0, 1)")
    k = ratio
    p_bar = (p1 + k * p2) / (1 + k)
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(power)
    num = (
        z_a * math.sqrt(p_bar * (1 - p_bar) * (1 + 1 / k))
        + z_b * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2) / k)
    ) ** 2
    return math.ceil(num / mde**2)


def mde(
    n_control: int, baseline: float, alpha: float = 0.05, power: float = 0.8, ratio: float = 1.0
) -> float:
    """Smallest absolute lift detectable with ``n_control`` users in control."""
    hi = min(1 - baseline, 0.999) - 1e-9

    def gap(d: float) -> float:
        return sample_size(baseline, d, alpha, power, ratio) - n_control

    if gap(hi) > 0:
        return float("nan")
    return float(optimize.brentq(gap, 1e-6, hi, xtol=1e-7))


def days_to_run(
    required_per_arm: int, daily_users_per_arm: float, already_per_arm: int = 0
) -> float:
    """Days of traffic needed to reach ``required_per_arm`` (0 if already reached)."""
    if daily_users_per_arm <= 0:
        return float("inf")
    return max(0.0, (required_per_arm - already_per_arm) / daily_users_per_arm)

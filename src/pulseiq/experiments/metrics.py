"""Metric registry and pre-registered experiment design parameters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class MetricSpec:
    """How to compute and judge one metric from ``fct_experiment_exposures``."""

    name: str
    kind: Literal["proportion", "mean"]
    column: str
    higher_is_better: bool = True
    eligibility: str | None = None
    heavy_tailed: bool = False
    label: str = ""


METRICS: dict[str, MetricSpec] = {
    m.name: m
    for m in (
        MetricSpec(
            "onboarding_completed",
            "proportion",
            "onboarding_completed",
            label="Onboarding completion",
        ),
        MetricSpec(
            "trial_started_14d",
            "proportion",
            "trial_started_14d",
            eligibility="trial_eligible",
            label="Trial start ≤14 d",
        ),
        MetricSpec(
            "paid_30d", "proportion", "paid_30d", eligibility="paid_eligible", label="Paid ≤30 d"
        ),
        MetricSpec(
            "d1_retained",
            "proportion",
            "d1_retained",
            eligibility="d1_eligible",
            label="D1 retention",
        ),
        MetricSpec(
            "d7_retained",
            "proportion",
            "d7_retained",
            eligibility="d7_eligible",
            label="D7 retention",
        ),
        MetricSpec(
            "d30_retained",
            "proportion",
            "d30_retained",
            eligibility="d30_eligible",
            label="D30 retention",
        ),
        MetricSpec(
            "trial_started_in_test",
            "proportion",
            "trial_started_in_test",
            label="Trial start in test",
        ),
        MetricSpec("paid_in_test", "proportion", "paid_in_test", label="Paid in test"),
        MetricSpec(
            "refund_in_test",
            "proportion",
            "refund_in_test",
            higher_is_better=False,
            label="Refund in test",
        ),
        MetricSpec("sessions_in_test", "mean", "sessions_in_test", label="Sessions in test"),
        MetricSpec(
            "net_revenue_in_test",
            "mean",
            "net_revenue_in_test",
            heavy_tailed=True,
            label="Net revenue in test (USD)",
        ),
    )
}


@dataclass(frozen=True)
class Design:
    """Pre-registered design: minimum detectable effect and guardrail tolerances.

    ``mde_abs`` is the absolute effect on the primary metric the test was sized for.
    ``tolerances`` maps guardrail -> largest acceptable harm (absolute, in the
    metric's bad direction). A guardrail is "safe" when its CI excludes harm beyond
    the tolerance (non-inferiority).
    """

    mde_abs: float | None = None
    mde_rel: float | None = 0.10
    tolerances: dict | None = None
    alpha: float = 0.05
    power: float = 0.80


DESIGNS: dict[str, Design] = {
    "onboarding_flow_v2": Design(
        mde_abs=0.02, tolerances={"paid_30d": 0.01, "d30_retained": 0.015}
    ),
    "paywall_redesign": Design(mde_rel=0.10, tolerances={"refund_in_test": 0.005}),
    "streak_reminder": Design(mde_abs=0.015, tolerances={"d1_retained": 0.01}),
}
DEFAULT_TOLERANCE = 0.01

# Covariates used for CUPED, in order of preference.
CUPED_COVARIATES = ("pre_sessions_14d", "pre_active_days_14d")
SEGMENT_COLUMNS = ("platform", "acquisition_channel", "country_tier")
SRM_SEGMENT_COLUMNS = ("platform", "country_tier")
SRM_ALPHA = 0.001

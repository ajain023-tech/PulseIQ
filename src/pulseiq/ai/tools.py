"""Tools the analyst may call instead of writing SQL."""

from __future__ import annotations

import pandas as pd

from pulseiq.experiments.power import days_to_run, sample_size
from pulseiq.services import experiments as exp_service


def get_experiment_report(experiment_id: str) -> tuple[pd.DataFrame, str, list[str]]:
    """(metric table, answer text, caveats) from the validated experimentation engine."""
    rep = exp_service.get_report(experiment_id)
    rows = pd.DataFrame(
        [
            {
                "metric": m.metric,
                "role": m.role,
                "control": m.value_control,
                "treatment": m.value_treatment,
                "lift": m.decision_diff,
                "ci_low": m.decision_ci[0],
                "ci_high": m.decision_ci[1],
                "adj_p": m.p_adjusted,
                "significant": m.significant,
            }
            for m in rep.metrics
        ]
    )
    answer = f"**{rep.decision}** for `{experiment_id}`. " + " ".join(rep.reasons)
    caveats = [
        "Readout from the validated experimentation engine (SRM, CUPED, Holm), not ad-hoc SQL."
    ]
    if rep.srm.flagged:
        caveats.append("Sample ratio mismatch: metric differences are not trustworthy.")
    return rows, answer, caveats


def list_experiments() -> tuple[pd.DataFrame, str, list[str]]:
    """All experiments with their decisions."""
    rows = pd.DataFrame(exp_service.list_experiments())[
        ["experiment_id", "name", "primary_metric", "primary_lift_abs", "decision"]
    ]
    answer = "; ".join(f"`{r.experiment_id}`: {r.decision}" for r in rows.itertuples())
    return rows, answer, []


def power_calc(baseline: float, mde: float, daily_users_per_arm: float | None = None) -> dict:
    """Sample size per arm (and days) for an absolute MDE."""
    n = sample_size(baseline, mde)
    return {
        "n_per_arm": n,
        "days": days_to_run(n, daily_users_per_arm) if daily_users_per_arm else None,
    }

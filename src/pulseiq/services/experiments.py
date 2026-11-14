"""Experiment listing, cached reports and on-demand re-analysis."""

from __future__ import annotations

from pulseiq.config import get_settings
from pulseiq.experiments import ExperimentReport, analyze_experiment, load_report, save_report
from pulseiq.experiments.data import list_experiments as _list_ids

from .db import cached, cursor


def _report_path(exp_id: str):
    return get_settings().artifacts_dir / "experiments" / exp_id / "report.json"


def experiment_ids() -> list[str]:
    """Experiment ids present in the warehouse."""
    with cursor() as cur:
        return _list_ids(cur)


@cached
def get_report(exp_id: str) -> ExperimentReport:
    """Cached report from artifacts (computed and saved on first request). KeyError if unknown."""
    if exp_id not in experiment_ids():
        raise KeyError(exp_id)
    path = _report_path(exp_id)
    if path.exists():
        return load_report(path)
    with cursor() as cur:
        rep = analyze_experiment(cur, exp_id)
    save_report(rep, path.parent)
    return rep


def list_experiments() -> list[dict]:
    """Summary row per experiment (id, name, dates, decision, n, primary lift)."""
    rows = []
    for exp_id in experiment_ids():
        r = get_report(exp_id)
        p = r.metrics[0]
        rows.append(
            {
                "experiment_id": r.experiment_id,
                "name": r.name,
                "start_date": r.start_date,
                "end_date": r.end_date,
                "primary_metric": r.primary_metric,
                "primary_lift_abs": p.decision_diff,
                "primary_ci": p.decision_ci,
                "srm_flagged": r.srm.flagged,
                "decision": r.decision,
                "n_control": r.n_control,
                "n_treatment": r.n_treatment,
            }
        )
    return rows


def run_analysis(
    exp_id: str, sequential: bool = True, bayesian: bool = True, cuped: bool = True
) -> ExperimentReport:
    """Re-run the analysis with options (not persisted unless all defaults)."""
    if exp_id not in experiment_ids():
        raise KeyError(exp_id)
    with cursor() as cur:
        rep = analyze_experiment(cur, exp_id, sequential=sequential, bayesian=bayesian, cuped=cuped)
    if sequential and bayesian and cuped:
        save_report(rep, _report_path(exp_id).parent)
    return rep

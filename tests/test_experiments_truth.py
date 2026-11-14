"""The experiment engine must recover the effects planted by the generator."""

from __future__ import annotations

import json

import duckdb
import pytest

from pulseiq.experiments import analyze_experiment
from pulseiq.experiments.sequential import simulate_peeking

pytestmark = pytest.mark.slow
EXPS = ("onboarding_flow_v2", "paywall_redesign", "streak_reminder")


@pytest.fixture(scope="module")
def reports_and_truth(full_env):
    truth = json.loads((full_env / "raw" / "ground_truth.json").read_text())
    with duckdb.connect(str(full_env / "warehouse" / "pulseiq.duckdb"), read_only=True) as con:
        reports = {e: analyze_experiment(con, e) for e in EXPS}
    return reports, truth


def test_every_planted_effect_covered(reports_and_truth):
    reports, truth = reports_and_truth
    for exp_id, rep in reports.items():
        for metric, true in truth["experiments"][exp_id]["true_effects_abs"].items():
            m = rep.metric(metric)
            lo, hi = m.decision_ci
            assert lo <= true <= hi, (exp_id, metric, true, m.decision_ci)


def test_srm_only_on_streak_and_localised(reports_and_truth):
    reports, _ = reports_and_truth
    assert not reports["onboarding_flow_v2"].srm.flagged
    assert not reports["paywall_redesign"].srm.flagged
    srm = reports["streak_reminder"].srm
    assert srm.flagged
    assert [(c["segment_type"], c["segment_value"]) for c in srm.likely_causes] == [
        ("platform", "android")
    ]


def test_cuped_cuts_ci_width_on_paywall(reports_and_truth):
    reports, _ = reports_and_truth
    m = reports["paywall_redesign"].metric("trial_started_in_test")
    assert m.cuped_used
    assert m.cuped.ci_width_reduction >= 0.20


def test_cuped_skipped_for_new_user_experiments(reports_and_truth):
    reports, _ = reports_and_truth
    assert reports["onboarding_flow_v2"].cuped_status.startswith("skipped")


def test_expected_decisions(reports_and_truth):
    reports, _ = reports_and_truth
    assert reports["streak_reminder"].decision == "INVESTIGATE"
    assert reports["paywall_redesign"].decision == "SHIP"
    assert reports["onboarding_flow_v2"].decision in ("KEEP RUNNING", "DON'T SHIP")


def test_aa_simulation_500_runs():
    sim = simulate_peeking(n_sims=500, seed=99)
    assert abs(sim["fpr_fixed_horizon"] - 0.05) < 0.03
    assert sim["fpr_naive_peeking"] > 0.15
    assert sim["fpr_sequential"] <= 0.06

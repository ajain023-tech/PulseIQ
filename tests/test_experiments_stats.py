"""Unit tests for every statistics function, with hand-computable examples."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from pulseiq.experiments.bayesian import beta_binomial_readout
from pulseiq.experiments.corrections import benjamini_hochberg, holm
from pulseiq.experiments.cuped import cuped_adjust, cuped_readout
from pulseiq.experiments.decision import DONT_SHIP, INVESTIGATE, KEEP_RUNNING, SHIP, decide
from pulseiq.experiments.frequentist import (
    bootstrap_diff_ci,
    newcombe_diff_ci,
    proportion_readout,
    two_proportion_ztest,
    welch_readout,
    wilson_interval,
)
from pulseiq.experiments.power import days_to_run, mde, sample_size
from pulseiq.experiments.sequential import msprt_lambda, simulate_peeking
from pulseiq.experiments.srm import localise_srm, srm_by_segment, srm_test


def test_srm_balanced_and_skewed():
    chi2, p = srm_test(5000, 5000)
    assert chi2 == 0 and p == 1
    # (5100-5000)^2/5000 * 2 = 4.0
    chi2, p = srm_test(5100, 4900)
    assert chi2 == pytest.approx(4.0)
    assert p == pytest.approx(stats.chi2.sf(4.0, 1))


def test_srm_localisation():
    rng = np.random.default_rng(0)
    n = 20000
    df = pd.DataFrame(
        {
            "variant": np.where(rng.random(n) < 0.5, "treatment", "control"),
            "platform": rng.choice(["ios", "android"], n),
            "tier": rng.choice(["a", "b"], n, p=[0.6, 0.4]),
        }
    )
    drop = (df["platform"] == "android") & (df["variant"] == "treatment") & (rng.random(n) < 0.25)
    df = df[~drop]
    flagged = [r for col in ("platform", "tier") for r in srm_by_segment(df, col) if r["flagged"]]
    causes = localise_srm(df, flagged)
    assert [c["segment_value"] for c in causes] == ["android"]


def test_wilson_known_value():
    # Wilson 95 % CI for 10/20 is symmetric around 0.5: [0.2993, 0.7007]
    lo, hi = wilson_interval(10, 20)
    assert lo == pytest.approx(0.2993, abs=1e-4)
    assert hi == pytest.approx(0.7007, abs=1e-4)


def test_newcombe_known_value():
    # Newcombe (1998) example 1: 56/70 vs 48/80 -> diff 0.2, CI [0.0524, 0.3339]
    lo, hi = newcombe_diff_ci(48, 80, 56, 70)
    assert lo == pytest.approx(0.0524, abs=5e-4)
    assert hi == pytest.approx(0.3339, abs=5e-4)


def test_ztest_matches_formula():
    z, p = two_proportion_ztest(100, 1000, 130, 1000)
    pooled = 230 / 2000
    se = math.sqrt(pooled * (1 - pooled) * 2 / 1000)
    assert z == pytest.approx(0.03 / se)
    assert p == pytest.approx(2 * stats.norm.sf(0.03 / se))


def test_proportion_readout_relative():
    r = proportion_readout(100, 1000, 120, 1000)
    assert r.abs_diff == pytest.approx(0.02)
    assert r.rel_lift == pytest.approx(0.2)
    assert r.rel_ci_low < 0.2 < r.rel_ci_high


def test_welch_matches_scipy():
    rng = np.random.default_rng(1)
    a, b = rng.normal(0, 1, 300), rng.normal(0.3, 2, 500)
    r = welch_readout(a, b)
    ref = stats.ttest_ind(b, a, equal_var=False)
    assert r.p_value == pytest.approx(ref.pvalue)
    assert r.ci_low < r.abs_diff < r.ci_high


def test_bootstrap_ci_reasonable():
    rng = np.random.default_rng(2)
    a, b = rng.exponential(1, 2000), rng.exponential(1.2, 2000)
    lo, hi = bootstrap_diff_ci(a, b, seed=3)
    assert lo < 0.2 < hi
    assert bootstrap_diff_ci(a, b, seed=3) == (lo, hi)  # seeded


def test_cuped_theta_and_variance():
    rng = np.random.default_rng(4)
    x = rng.normal(10, 3, 5000)
    y = 2 * x + rng.normal(0, 1, 5000)
    y_adj, theta = cuped_adjust(y, x)
    assert theta == pytest.approx(2.0, abs=0.05)
    assert np.var(y_adj) < 0.05 * np.var(y)
    assert y_adj.mean() == pytest.approx(y.mean())  # unbiased: mean preserved


def test_cuped_shrinks_ci_without_bias():
    rng = np.random.default_rng(5)
    n = 4000
    xc, xt = rng.poisson(5, n), rng.poisson(5, n)
    yc = (rng.random(n) < 0.04 * xc).astype(float)
    yt = (rng.random(n) < 0.04 * xt * 1.1).astype(float)
    raw = welch_readout(yc, yt)
    cr = cuped_readout(yc, xc, yt, xt, "x", raw)
    assert cr.ci_width_cuped < raw.ci_high - raw.ci_low
    # variance reduction equals the squared correlation between outcome and covariate
    assert cr.variance_reduction == pytest.approx(cr.correlation**2, rel=1e-6)
    assert cr.variance_reduction > 0.03


def test_cuped_uncorrelated_covariate_no_gain():
    rng = np.random.default_rng(6)
    y = rng.normal(0, 1, 2000)
    x = rng.normal(0, 1, 2000)
    y_adj, theta = cuped_adjust(y, x)
    assert abs(theta) < 0.1
    assert np.var(y_adj) == pytest.approx(np.var(y), rel=0.01)


def test_holm_and_bh_known_values():
    p = [0.01, 0.04, 0.03, 0.005]
    # Holm: sorted 0.005*4=0.02, 0.01*3=0.03, 0.03*2=0.06, 0.04*1 -> max(0.06, 0.04)=0.06
    assert holm(p) == pytest.approx([0.03, 0.06, 0.06, 0.02])
    # BH: sorted p*m/rank = .02,.02,.04,.04 -> step-up min
    assert benjamini_hochberg(p) == pytest.approx([0.02, 0.04, 0.04, 0.02])


def test_msprt_lambda_properties():
    assert msprt_lambda(np.array([0.0]), np.array([1e-4]), 1e-4)[0] < 1  # no evidence
    lam = msprt_lambda(np.array([0.0, 0.01, 0.03]), np.array([1e-5] * 3), 4e-4)
    assert lam[0] < lam[1] < lam[2]


def test_peeking_simulation_story():
    sim = simulate_peeking(n_sims=600, looks=20, seed=11)
    assert 0.02 <= sim["fpr_fixed_horizon"] <= 0.09
    assert sim["fpr_naive_peeking"] > 0.15
    assert sim["fpr_sequential"] <= 0.06


def test_bayesian_symmetry_and_direction():
    same = beta_binomial_readout(100, 1000, 100, 1000, draws=50_000, seed=1)
    assert same["prob_treatment_better"] == pytest.approx(0.5, abs=0.01)
    better = beta_binomial_readout(100, 1000, 150, 1000, draws=50_000, seed=1)
    assert better["prob_treatment_better"] > 0.99
    assert better["expected_loss_ship_treatment"] < better["expected_loss_ship_control"]


def test_power_matches_statsmodels():
    from statsmodels.stats.power import NormalIndPower
    from statsmodels.stats.proportion import proportion_effectsize

    n = sample_size(0.10, 0.02)
    ref = NormalIndPower().solve_power(proportion_effectsize(0.12, 0.10), alpha=0.05, power=0.8)
    assert n == pytest.approx(ref, rel=0.03)
    # textbook value for 10% -> 12% is ~3,841 per arm
    assert 3800 <= n <= 3900


def test_mde_inverts_sample_size():
    n = sample_size(0.2, 0.03)
    assert mde(n, 0.2) == pytest.approx(0.03, abs=2e-4)
    assert days_to_run(1000, 100, 400) == pytest.approx(6.0)
    assert days_to_run(1000, 100, 2000) == 0.0


def _m(name, diff, ci, sig, improved=True, tol=None, hib=True, p=0.01):
    return {
        "metric": name,
        "decision_diff": diff,
        "decision_ci": ci,
        "significant": sig,
        "improved": improved,
        "tolerance": tol,
        "higher_is_better": hib,
        "p_adjusted": p,
    }


SRM_OK = {"flagged": False}


def test_decision_rules():
    power = {"required_n_per_arm": 1000, "n_per_arm": 5000, "days_left": 0}
    prim = _m("p", 0.03, [0.01, 0.05], True)
    safe = _m("g", -0.001, [-0.004, 0.002], False, improved=False, tol=0.01)
    unsafe = _m("g", -0.004, [-0.012, 0.004], False, improved=False, tol=0.01)
    harmed = _m("g", -0.02, [-0.03, -0.01], True, improved=False, tol=0.01)
    srm_bad = {
        "flagged": True,
        "p_value": 1e-6,
        "treatment_share": 0.48,
        "allocation": 0.5,
        "flagged_segments": [],
        "likely_causes": [],
    }
    assert decide(srm_bad, prim, [safe], power)[0] == INVESTIGATE
    assert decide(SRM_OK, prim, [harmed], power)[0] == DONT_SHIP
    assert decide(SRM_OK, prim, [safe], power)[0] == SHIP
    assert decide(SRM_OK, prim, [unsafe], power)[0] == KEEP_RUNNING
    ns = _m("p", 0.001, [-0.01, 0.012], False)
    assert (
        decide(SRM_OK, ns, [], {"required_n_per_arm": 9000, "n_per_arm": 5000, "days_left": 4})[0]
        == KEEP_RUNNING
    )
    assert decide(SRM_OK, ns, [], power)[0] == DONT_SHIP

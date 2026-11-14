"""Facts extracted from generated artifacts - the ONLY source of numbers in README/docs.

Used by render_results.py (writes the README results block) and check_numbers.py
(verifies that docs quote these exact values).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"


def _load(rel: str) -> dict:
    path = ART / rel
    if not path.exists():
        raise FileNotFoundError(f"{path} missing - run `make all` first")
    return json.loads(path.read_text())


def facts() -> dict:
    """Name -> value dictionary (raw numbers) built from artifacts."""
    val = _load("reports/experiment_validation.json")
    mlv = _load("reports/ml_validation.json")
    ml = _load("ml/metrics.json")
    meta = _load("ml/model_meta.json")
    ai = _load("reports/ai_eval.json")["summary"]
    surv = _load("ml/survival.json")
    reps = {e: _load(f"experiments/{e}/report.json") for e in ("onboarding_flow_v2", "paywall_redesign", "streak_reminder")}
    cox = {c["feature"]: c for c in surv["cox"]}
    best = meta["model"]
    f = {
        "effects_covered": val["n_covered"],
        "effects_total": val["n_effects"],
        "srm_only_on_streak": val["srm_only_on_streak"],
        "srm_localised_android": val["srm_localised_android"],
        "cuped_ci_width_reduction": val["cuped_ci_width_reduction_paywall"],
        "cuped_variance_reduction": val["cuped_variance_reduction_paywall"],
        "fpr_fixed": val["fpr_fixed_horizon"],
        "fpr_naive": val["fpr_naive_peeking"],
        "fpr_sequential": val["fpr_sequential"],
        "model": best,
        "pr_auc_model": ml[best]["pr_auc"],
        "pr_auc_lr": ml["logistic_regression"]["pr_auc"],
        "pr_auc_majority": ml["majority_baseline"]["pr_auc"],
        "pr_auc_heuristic": ml["active_days_heuristic"]["pr_auc"],
        "roc_auc_model": ml[best]["roc_auc"],
        "recall_model": ml[best]["recall"],
        "precision_model": ml[best]["precision"],
        "accuracy_majority": ml["majority_baseline"]["accuracy"],
        "recall_at_top20": ml[best]["recall_at_top20"],
        "lift_top_decile": ml[best]["lift_at_top_decile"],
        "drivers_recovered": mlv["all_explicit_drivers_recovered"],
        "cox_hr_reminder": cox["reminder_set_any"]["hazard_ratio"],
        "ai_n": ai["n_questions"],
        "ai_correct": ai["overall_correct_pct"],
        "ai_sql_valid": ai["sql_valid_pct"],
        "ai_refusal": ai["refusal_correct_pct"],
        "ai_provider": ai["provider"],
    }
    for e, r in reps.items():
        p = r["metrics"][0]
        f[f"{e}_decision"] = r["decision"]
        f[f"{e}_lift"] = p["decision_diff"]
        f[f"{e}_ci_low"] = p["decision_ci"][0]
        f[f"{e}_ci_high"] = p["decision_ci"][1]
        f[f"{e}_srm_p"] = r["srm"]["p_value"]
    return f


def pp(v: float) -> str:
    """Absolute change as percentage points, e.g. +2.81 pp."""
    return f"{v * 100:+.2f} pp"


def pct(v: float, d: int = 1) -> str:
    """Ratio as a percentage."""
    return f"{v * 100:.{d}f}%"

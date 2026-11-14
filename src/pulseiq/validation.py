"""Validation reports that compare engine/model output with planted ground truth.

This is the ONLY module (besides tests) allowed to read ``ground_truth.json``.
The experimentation engine and the ML models never import it.
"""

from __future__ import annotations

import json
from pathlib import Path

from pulseiq.config import Settings
from pulseiq.experiments.report import ExperimentReport


def load_ground_truth(settings: Settings) -> dict:
    """Read the validation-only ground-truth file."""
    return json.loads(settings.ground_truth_path.read_text())


def coverage_rows(reports: dict[str, ExperimentReport], truth: dict) -> list[dict]:
    """One row per (experiment, metric) with a planted truth."""
    rows = []
    for exp_id, rep in reports.items():
        t = truth["experiments"][exp_id]
        for m in rep.metrics:
            if m.metric not in t.get("true_effects_abs", {}):
                continue
            true = t["true_effects_abs"][m.metric]
            lo, hi = m.decision_ci
            rows.append(
                {
                    "experiment_id": exp_id,
                    "metric": m.metric,
                    "role": m.role,
                    "true_effect": true,
                    "estimate": m.decision_diff,
                    "ci_low": lo,
                    "ci_high": hi,
                    "covered": bool(lo <= true <= hi),
                    "cuped": m.cuped_used,
                }
            )
    return rows


def write_experiment_validation(
    reports: dict[str, ExperimentReport], truth: dict, peeking: dict, out: Path
) -> dict:
    """Write ``experiment_validation.md``; return a machine-readable summary."""
    rows = coverage_rows(reports, truth)
    srm_flags = {k: r.srm.flagged for k, r in reports.items()}
    srm_causes = {
        k: [f"{c['segment_type']}={c['segment_value']}" for c in r.srm.likely_causes]
        for k, r in reports.items()
    }
    pw = reports["paywall_redesign"].metric("trial_started_in_test")
    pw_rel_truth = truth["experiments"]["paywall_redesign"]["true_effects_rel"][
        "trial_started_in_test"
    ]
    summary = {
        "n_effects": len(rows),
        "n_covered": sum(r["covered"] for r in rows),
        "srm_flags": srm_flags,
        "srm_only_on_streak": srm_flags
        == {"onboarding_flow_v2": False, "paywall_redesign": False, "streak_reminder": True},
        "srm_localised_android": srm_causes.get("streak_reminder") == ["platform=android"],
        "cuped_ci_width_reduction_paywall": pw.cuped.ci_width_reduction if pw.cuped else None,
        "cuped_variance_reduction_paywall": pw.cuped.variance_reduction if pw.cuped else None,
        "fpr_fixed_horizon": peeking["fpr_fixed_horizon"],
        "fpr_naive_peeking": peeking["fpr_naive_peeking"],
        "fpr_sequential": peeking["fpr_sequential"],
        "decisions": {k: r.decision for k, r in reports.items()},
    }
    lines = [
        "# Experiment engine validation against planted ground truth",
        "",
        f"Dataset: size `{truth['size']}`, seed `{truth['seed']}`. The truth is the exact average treatment "
        "effect computed by the generator from per-user probabilities.",
        "",
        f"**{summary['n_covered']} / {summary['n_effects']} planted effects lie inside the engine's 95 % CI.**",
        "",
        "| Experiment | Metric | Role | True effect | Estimate | 95 % CI | Covered |",
        "|---|---|---|---:|---:|---|:-:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['experiment_id']} | {r['metric']}{' (CUPED)' if r['cuped'] else ''} | {r['role']} | "
            f"{r['true_effect']:+.4f} | {r['estimate']:+.4f} | [{r['ci_low']:+.4f}, {r['ci_high']:+.4f}] | "
            f"{'yes' if r['covered'] else '**NO**'} |"
        )
    lines += [
        "",
        f"Paywall relative lift: true {pw_rel_truth:+.2%}; estimate {pw.rel_lift:+.2%} "
        f"(raw delta-method CI [{pw.rel_ci_low:+.2%}, {pw.rel_ci_high:+.2%}]).",
        "",
        "## Sample ratio mismatch",
        "",
        "| Experiment | SRM p-value | Flagged | Likely cause | Planted bug |",
        "|---|---:|:-:|---|---|",
    ]
    for k, r in reports.items():
        bug = truth["experiments"][k]["srm_bug"]
        lines.append(
            f"| {k} | {r.srm.p_value:.3g} | {'yes' if r.srm.flagged else 'no'} | "
            f"{', '.join(srm_causes[k]) or '–'} | {bug['description'] + ' (' + str(bug['rows_dropped']) + ' rows)' if bug else '–'} |"
        )
    lines += [
        "",
        f"SRM flagged only on `streak_reminder`: **{'yes' if summary['srm_only_on_streak'] else 'NO'}**; "
        f"localised to Android: **{'yes' if summary['srm_localised_android'] else 'NO'}**.",
        "",
        "## CUPED on `paywall_redesign`",
        "",
        f"Covariate `pre_sessions_14d`: variance reduction {summary['cuped_variance_reduction_paywall']:.1%}, "
        f"CI width reduction **{summary['cuped_ci_width_reduction_paywall']:.1%}** (target ≥ 20 %).",
        "",
        "## Peeking (A/A simulation)",
        "",
        f"{peeking['n_sims']:,} simulated A/A tests, {peeking['looks']} daily looks, "
        f"{peeking['users_per_look_per_arm']} users/arm/look, baseline {peeking['baseline']:.0%}, "
        f"mSPRT τ = {peeking['tau']}.",
        "",
        "| Procedure | False-positive rate |",
        "|---|---:|",
        f"| Fixed horizon (one look at the end) | {peeking['fpr_fixed_horizon']:.1%} |",
        f"| Naive peeking (stop at first p < 0.05) | {peeking['fpr_naive_peeking']:.1%} |",
        f"| mSPRT always-valid sequential test | {peeking['fpr_sequential']:.1%} |",
        "",
        "![peeking](../experiments/peeking_simulation.png)",
        "",
        "## Decisions",
        "",
        *[f"- `{k}` → **{v}**" for k, v in summary["decisions"].items()],
        "",
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    (out.with_suffix(".json")).write_text(json.dumps(summary, indent=2))
    return summary


DRIVER_FEATURES = {"reminder_set_72h", "reminder_set_any_72h", "workout_log_72h", "active_days_72h"}


def write_ml_validation(meta: dict, truth: dict, out: Path) -> dict:
    """Do the model's top drivers match the planted true retention drivers?"""
    top = [r["feature"] for r in meta["top_features"]]
    planted = [d["feature"] for d in truth["true_retention_drivers"]]
    top5 = top[:5]
    found = sorted(
        {f.replace("_any", "") for f in top5}
        & {"reminder_set_72h", "workout_log_72h", "active_days_72h"}
    )
    m = meta["metrics_test"]
    best = meta["model"]
    summary = {
        "model": best,
        "pr_auc_model": m[best]["pr_auc"],
        "pr_auc_majority": m["majority_baseline"]["pr_auc"],
        "pr_auc_heuristic": m["active_days_heuristic"]["pr_auc"],
        "beats_baselines": m[best]["pr_auc"]
        > max(m["majority_baseline"]["pr_auc"], m["active_days_heuristic"]["pr_auc"]),
        "recall_model": m[best]["recall"],
        "top5_features": top5,
        "planted_drivers_in_top5": found,
        "all_explicit_drivers_recovered": len(found) == 3,
    }
    lines = [
        "# Retention model validation",
        "",
        f"Best model `{best}`: test PR-AUC **{summary['pr_auc_model']:.3f}** vs majority baseline "
        f"{summary['pr_auc_majority']:.3f} and active-days heuristic {summary['pr_auc_heuristic']:.3f}; "
        f"recall {summary['recall_model']:.3f} at the validation-chosen threshold.",
        "",
        "## Do the model's drivers match the planted ones?",
        "",
        "Planted drivers (generator, `ground_truth.json`): "
        + ", ".join(f"`{p}`" for p in planted[:3])
        + ", plus latent engagement.",
        "",
        "| Rank | Feature (permutation importance on test) | Drop in PR-AUC | Planted driver? |",
        "|---:|---|---:|:-:|",
    ]
    for i, r in enumerate(meta["top_features"][:10], 1):
        f = r["feature"]
        lines.append(
            f"| {i} | `{f}` | {r['importance']:.4f} | {'yes' if f in DRIVER_FEATURES else ''} |"
        )
    lines += [
        "",
        f"All three explicit planted drivers are in the top 5: **{'yes' if summary['all_explicit_drivers_recovered'] else 'NO'}**.",
        "The model never reads the ground-truth file; this comparison is done only here.",
        "",
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    out.with_suffix(".json").write_text(json.dumps(summary, indent=2))
    return summary

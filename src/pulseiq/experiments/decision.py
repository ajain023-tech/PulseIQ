"""Turn a readout into SHIP / DON'T SHIP / KEEP RUNNING / INVESTIGATE.

Rules (evaluated in order; documented in docs/EXPERIMENTATION.md):

1. SRM detected (p < 0.001)                       -> INVESTIGATE (no readout trusted)
2. A guardrail is significantly worse (Holm)      -> DON'T SHIP (even if primary wins)
3. Primary significantly better (Holm) and every
   guardrail's CI excludes harm beyond tolerance  -> SHIP
4. Primary significantly better but a guardrail
   is not yet shown safe (CI crosses -tolerance)  -> KEEP RUNNING (+ days left)
5. Primary not significant and n < required n     -> KEEP RUNNING (+ days left)
6. Primary not significant and adequately powered -> DON'T SHIP (no detectable effect)
7. Primary significantly worse                    -> DON'T SHIP
"""

from __future__ import annotations

SHIP = "SHIP"
DONT_SHIP = "DON'T SHIP"
KEEP_RUNNING = "KEEP RUNNING"
INVESTIGATE = "INVESTIGATE"


def _harm_bound(m: dict) -> float:
    """Worst plausible harm (positive number = harm) from the 95 % CI."""
    lo, hi = m["decision_ci"]
    return -lo if m["higher_is_better"] else hi


def decide(srm: dict, primary: dict, guardrails: list[dict], power: dict) -> tuple[str, list[str]]:
    """Return ``(decision, reasons)``. Metric dicts use the report's MetricResult fields."""
    reasons: list[str] = []
    if srm["flagged"]:
        causes = srm.get("likely_causes") or []
        where = (
            ", ".join(f"{s['segment_type']}={s['segment_value']}" for s in causes)
            or "not localised"
        )
        flagged = ", ".join(
            f"{s['segment_type']}={s['segment_value']}" for s in srm["flagged_segments"]
        )
        reasons.append(
            f"Sample ratio mismatch: p = {srm['p_value']:.2g} (< 0.001); treatment share "
            f"{srm['treatment_share']:.1%} vs intended {srm['allocation']:.0%}."
        )
        reasons.append(
            f"Likely cause: {where} (excluding it restores the intended split). Segments flagged: {flagged or 'none'}."
        )
        reasons.append(
            "Assignment is broken, so no metric readout can be trusted until the cause is fixed."
        )
        return INVESTIGATE, reasons

    harmed = [g for g in guardrails if g["significant"] and not g["improved"]]
    if harmed:
        for g in harmed:
            reasons.append(
                f"Guardrail {g['metric']} is significantly worse: {g['decision_diff']:+.4f} "
                f"(95 % CI {g['decision_ci'][0]:+.4f} to {g['decision_ci'][1]:+.4f}, Holm p = {g['p_adjusted']:.3g})."
            )
        return DONT_SHIP, reasons

    p_txt = (
        f"Primary {primary['metric']}: {primary['decision_diff']:+.4f} "
        f"(95 % CI {primary['decision_ci'][0]:+.4f} to {primary['decision_ci'][1]:+.4f}, "
        f"Holm p = {primary['p_adjusted']:.3g}{', CUPED' if primary.get('cuped_used') else ''})."
    )
    reasons.append(p_txt)
    days_left = power.get("days_left")
    if primary["significant"] and primary["improved"]:
        unsafe = [g for g in guardrails if _harm_bound(g) > g["tolerance"]]
        if not unsafe:
            for g in guardrails:
                reasons.append(
                    f"Guardrail {g['metric']} is safe: worst plausible harm {max(_harm_bound(g), 0):.4f} "
                    f"is within tolerance {g['tolerance']:.4f}."
                )
            return SHIP, reasons
        for g in unsafe:
            reasons.append(
                f"Guardrail {g['metric']} not yet shown safe: observed {g['decision_diff']:+.4f}, CI allows harm "
                f"up to {_harm_bound(g):.4f} > tolerance {g['tolerance']:.4f}."
            )
        if power.get("guardrail_days_left") is not None:
            reasons.append(
                f"About {power['guardrail_days_left']:.0f} more days of traffic would be needed to bound the "
                "guardrail within tolerance (or ship with an explicit, accepted risk)."
            )
        return KEEP_RUNNING, reasons

    if primary["significant"] and not primary["improved"]:
        reasons.append("The primary metric is significantly worse in treatment.")
        return DONT_SHIP, reasons

    if power.get("required_n_per_arm") and power["n_per_arm"] < power["required_n_per_arm"]:
        reasons.append(
            f"Not significant and underpowered: {power['n_per_arm']:,} users per arm vs "
            f"{power['required_n_per_arm']:,} needed for the pre-registered MDE"
            + (
                f"; ~{days_left:.0f} more days at current traffic."
                if days_left is not None
                else "."
            )
        )
        return KEEP_RUNNING, reasons
    reasons.append(
        "Adequately powered for the pre-registered MDE and no significant effect: no detectable effect."
    )
    return DONT_SHIP, reasons

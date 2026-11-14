"""Verify that numbers quoted in README/docs match the generated artifacts.

1. The README RESULTS block must equal a fresh render (render_results.py --check logic).
2. Each doc listed in CLAIMS must contain every artifact-derived string it is expected to
   quote (formatted the way the doc writes it). A stale doc fails loudly.
3. Hygiene: no machine-specific paths, no foreign Tableau link, no placeholder TODO/FIXME in
   the active tree.
Usage: python scripts/check_numbers.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from results_facts import ROOT, facts  # noqa: E402


def claims(f: dict) -> dict[str, list[str]]:
    """doc -> strings (derived from artifacts) the doc must contain."""
    p3 = lambda v: f"{v:.3f}"  # noqa: E731
    pc1 = lambda v: f"{v * 100:.1f} %"  # noqa: E731
    return {
        "docs/EXPERIMENTATION.md": [
            f"{f['effects_covered']} / {f['effects_total']}",
            pc1(f["cuped_ci_width_reduction"]),
            pc1(f["cuped_variance_reduction"]),
            pc1(f["fpr_naive"]),
            pc1(f["fpr_sequential"]),
            pc1(f["fpr_fixed"]),
            f["onboarding_flow_v2_decision"],
            f["paywall_redesign_decision"],
            f["streak_reminder_decision"],
        ],
        "docs/ML_RETENTION.md": [
            p3(f["pr_auc_model"]),
            p3(f["pr_auc_majority"]),
            p3(f["pr_auc_heuristic"]),
            p3(f["pr_auc_lr"]),
            p3(f["recall_model"]),
            p3(f["roc_auc_model"]),
            p3(f["cox_hr_reminder"]),
        ],
        "docs/MODEL_CARD.md": [
            p3(f["pr_auc_model"]),
            p3(f["roc_auc_model"]),
            p3(f["recall_model"]),
        ],
        "docs/career/RESUME_BULLETS.md": [
            f"{f['effects_covered']}/{f['effects_total']}",
            f"{f['cuped_ci_width_reduction'] * 100:.0f}%",
            f"{f['fpr_naive'] * 100:.1f}%",
            p3(f["pr_auc_model"]),
            p3(f["pr_auc_majority"]),
        ],
    }


def norm(text: str) -> str:
    return re.sub(r"(\d) %", r"\1 %", text)


def main() -> int:
    problems: list[str] = []
    from render_results import END, START, block

    readme = (ROOT / "README.md").read_text()
    current = readme[readme.find(START) : readme.find(END) + len(END)]
    if current != block():
        problems.append("README RESULTS block is stale (run `make results`)")
    f = facts()
    for doc, needles in claims(f).items():
        path = ROOT / doc
        if not path.exists():
            problems.append(f"{doc} missing")
            continue
        text = norm(path.read_text())
        for n in needles:
            if n not in text and n.replace(" %", "%") not in text:
                problems.append(f"{doc}: expected to quote '{n}' (from artifacts) but it does not")
    active = [
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and p.suffix in {".py", ".md", ".yml", ".yaml", ".toml", ".sql", ".sh"}
        and not any(
            part
            in {".venv", "legacy", ".git", "target", "logs", "artifacts", "data", "node_modules"}
            for part in p.parts
        )
        and not (p.parent.name == "roadmap" and p.name.startswith("PHASE_"))
        and p.name != "check_numbers.py"
    ]
    for p in active:
        t = p.read_text(errors="ignore")
        if "/Users/" in t:
            problems.append(f"{p.relative_to(ROOT)}: machine-specific path '/Users/'")
        if "nikita.sergeevich" in t:
            problems.append(f"{p.relative_to(ROOT)}: foreign Tableau link")
        if re.search(r"\b(TODO|FIXME|XXX)\b", t):
            problems.append(f"{p.relative_to(ROOT)}: TODO/FIXME marker")
    for msg in problems:
        print("FAIL", msg)
    print(
        f"{'OK' if not problems else 'FAILED'}: checked README results, {len(claims(f))} docs and {len(active)} files"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

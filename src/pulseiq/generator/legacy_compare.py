"""Compare the generated dataset's headline rates with the v1 legacy CSV."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pulseiq.config import Settings

from .calibration import TARGETS, headline_rates, legacy_rates

LABELS = {
    "onboarding_rate": "Onboarding completed (share of signups)",
    "trial_rate": "Trial started within 14 d (share of eligible signups)",
    "paid_rate": "Paid within 30 d (share of eligible signups)",
    "d1_retention": "D1 exact-day retention (eligible users)",
    "d7_retention": "D7 exact-day retention (eligible users)",
    "d30_retention": "D30 exact-day retention (eligible users)",
}


def load_raw_tables(raw_dir: Path) -> dict[str, pd.DataFrame]:
    """Read the raw parquet tables needed for headline rates."""
    return {
        name: pd.read_parquet(raw_dir / f"{name}.parquet")
        for name in ("users", "events", "sessions", "subscriptions")
    }


def compare_legacy(settings: Settings) -> tuple[pd.DataFrame, Path]:
    """Write ``artifacts/reports/legacy_vs_generated.md`` and return the table."""
    import json

    truth = json.loads(settings.ground_truth_path.read_text())
    data_end = pd.Timestamp(truth["data_end"])
    tables = load_raw_tables(settings.raw_dir)
    # Use deduplicated, skew-free events for a fair comparison.
    ev = tables["events"].drop_duplicates("event_id")
    tables["events"] = ev
    gen = headline_rates(tables, data_end)
    legacy = legacy_rates(pd.read_csv(settings.legacy_csv))
    rows = []
    for key, label in LABELS.items():
        rows.append(
            {
                "metric": label,
                "legacy_v1": legacy[key],
                "generated_v2": gen[key],
                "target": TARGETS[key],
                "diff_pp_vs_legacy": (gen[key] - legacy[key]) * 100,
            }
        )
    frame = pd.DataFrame(rows)
    out = settings.artifacts_dir / "reports" / "legacy_vs_generated.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Legacy (v1) vs generated (v2) headline rates",
        "",
        f"Generated dataset: size `{truth['size']}`, seed `{truth['seed']}`, "
        f"{truth['n_users']:,} users over {truth['n_days']} days.",
        "Legacy dataset: `data/legacy/ab_test_dataset.csv` (11,462 users, user-level flags).",
        "",
        "| Metric | Legacy v1 | Generated v2 | Calibration target | Diff vs legacy (pp) |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['metric']} | {r['legacy_v1']:.2%} | {r['generated_v2']:.2%} | "
            f"{r['target']:.0%} | {r['diff_pp_vs_legacy']:+.2f} |"
        )
    lines += [
        "",
        "Notes: the legacy trial/paid flags are lifetime flags without a window, so the",
        "generated windowed rates are the closest comparable definition. v2 data is a",
        "calibrated simulation of v1's observed behaviour, not a copy of it.",
        "",
    ]
    out.write_text("\n".join(lines))
    return frame, out

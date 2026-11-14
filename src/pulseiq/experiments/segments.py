"""Exploratory heterogeneous-effect breakdown by segment (BH-corrected)."""

from __future__ import annotations

import pandas as pd

from .corrections import benjamini_hochberg
from .frequentist import proportion_readout, welch_readout
from .metrics import MetricSpec
from .power import sample_size


def segment_effects(
    df: pd.DataFrame, metric: MetricSpec, columns: tuple[str, ...], mde_abs: float | None
) -> list[dict]:
    """Effect of treatment on ``metric`` within each segment value."""
    rows = []
    for col in columns:
        for value, g in df.groupby(col):
            c = g[g["variant"] == "control"][metric.column].to_numpy()
            t = g[g["variant"] == "treatment"][metric.column].to_numpy()
            if len(c) < 30 or len(t) < 30:
                continue
            if metric.kind == "proportion":
                r = proportion_readout(int(c.sum()), len(c), int(t.sum()), len(t))
            else:
                r = welch_readout(c.astype(float), t.astype(float))
            needed = None
            if metric.kind == "proportion" and mde_abs and 0 < r.value_control < 1 - mde_abs:
                needed = sample_size(r.value_control, mde_abs)
            rows.append(
                {
                    "segment_type": col,
                    "segment_value": str(value),
                    "n_control": r.n_control,
                    "n_treatment": r.n_treatment,
                    "value_control": r.value_control,
                    "value_treatment": r.value_treatment,
                    "abs_diff": r.abs_diff,
                    "ci_low": r.ci_low,
                    "ci_high": r.ci_high,
                    "p_value": r.p_value,
                    "underpowered": bool(
                        needed is not None and min(r.n_control, r.n_treatment) < needed
                    ),
                }
            )
    adj = benjamini_hochberg([r["p_value"] for r in rows])
    for r, a in zip(rows, adj, strict=True):
        r["p_adjusted_bh"] = a
        r["significant_bh"] = a < 0.05
    return rows

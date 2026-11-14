"""Sample-ratio-mismatch (SRM) detection, overall and per segment."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .metrics import SRM_ALPHA


def srm_test(n_control: int, n_treatment: int, allocation: float = 0.5) -> tuple[float, float]:
    """Chi-square goodness-of-fit of observed arm sizes vs the intended split.

    Returns ``(chi2, p_value)``. ``allocation`` is the intended treatment share.
    """
    total = n_control + n_treatment
    if total == 0:
        return 0.0, 1.0
    expected = np.array([total * (1 - allocation), total * allocation])
    chi2, p = stats.chisquare([n_control, n_treatment], f_exp=expected)
    return float(chi2), float(p)


def srm_by_segment(
    df: pd.DataFrame, column: str, allocation: float = 0.5, alpha: float = SRM_ALPHA
) -> list[dict]:
    """SRM test inside each value of ``column`` (localises the cause of an SRM)."""
    rows = []
    counts = df.groupby([column, "variant"]).size().unstack(fill_value=0)
    for value, row in counts.iterrows():
        nc, nt = int(row.get("control", 0)), int(row.get("treatment", 0))
        chi2, p = srm_test(nc, nt, allocation)
        rows.append(
            {
                "segment_type": column,
                "segment_value": str(value),
                "n_control": nc,
                "n_treatment": nt,
                "treatment_share": nt / max(nc + nt, 1),
                "chi2": chi2,
                "p_value": p,
                "flagged": p < alpha,
            }
        )
    return rows


def localise_srm(
    df: pd.DataFrame, flagged: list[dict], allocation: float = 0.5, alpha: float = SRM_ALPHA
) -> list[dict]:
    """Identify flagged segments that *cause* the SRM.

    A segment that is merely large inherits part of an SRM caused elsewhere. A
    segment is a likely cause when (a) excluding it removes the SRM (p >= alpha) and
    (b) the remaining traffic is close to the intended split: its deviation is less
    than half of the segment's own deviation. Condition (b) stops a big segment
    from looking guilty just because removing it costs power.
    """
    causes = []
    for seg in flagged:
        rest = df[df[seg["segment_type"]].astype(str) != seg["segment_value"]]
        nc = int((rest["variant"] == "control").sum())
        nt = int((rest["variant"] == "treatment").sum())
        _, p = srm_test(nc, nt, allocation)
        rest_dev = abs(nt / max(nc + nt, 1) - allocation)
        seg_dev = abs(seg["treatment_share"] - allocation)
        if p >= alpha and rest_dev < 0.5 * seg_dev:
            causes.append(
                {**seg, "p_value_without_segment": p, "rest_treatment_share": nt / max(nc + nt, 1)}
            )
    return sorted(causes, key=lambda c: -abs(c["treatment_share"] - allocation))

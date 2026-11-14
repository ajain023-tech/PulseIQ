"""Full-size calibration: headline rates within +/-3 pp of the v1 targets."""

from __future__ import annotations

import pandas as pd
import pytest

from pulseiq.generator import generate
from pulseiq.generator.calibration import TARGETS, headline_rates


@pytest.mark.slow
def test_full_size_calibration():
    result = generate("full", seed=42)
    tables = dict(result.tables)
    tables["events"] = tables["events"].drop_duplicates("event_id")
    rates = headline_rates(tables, pd.Timestamp(result.ground_truth["data_end"]))
    for key, target in TARGETS.items():
        assert abs(rates[key] - target) <= 0.03, (key, rates[key], target)

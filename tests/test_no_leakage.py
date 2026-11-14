"""Features must be identical when every post-72 h event is deleted."""

from __future__ import annotations

import pandas as pd

from pulseiq.config import get_settings
from pulseiq.generator.write import write_result
from pulseiq.ml.features import load_feature_frame, to_matrix


def test_features_ignore_post_72h_events(small_result, small_con, tmp_path, monkeypatch):
    import duckdb

    from pulseiq.warehouse import build_warehouse

    tables = dict(small_result.tables)
    users = tables["users"].set_index("user_id")["signup_ts"]
    ev = tables["events"]
    cutoff = ev["user_id"].map(users) + pd.Timedelta(hours=72)
    truncated = ev[ev["event_ts"] < cutoff]
    assert len(truncated) < len(ev) * 0.8  # a large share of events really was removed
    tables["events"] = truncated.reset_index(drop=True)

    monkeypatch.setenv("PULSEIQ_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PULSEIQ_WAREHOUSE", raising=False)
    settings = get_settings()
    result = type(small_result)(tables=tables, ground_truth=small_result.ground_truth)
    write_result(result, settings.raw_dir)
    assert build_warehouse(settings).success

    full = load_feature_frame(small_con, eligible_only=False).set_index("user_id")
    with duckdb.connect(str(settings.warehouse_path), read_only=True) as con2:
        cut = load_feature_frame(con2, eligible_only=False).set_index("user_id")
    cut = cut.loc[full.index]
    X_full = to_matrix(full.reset_index())
    X_cut = to_matrix(cut.reset_index(), list(X_full.columns))
    pd.testing.assert_frame_equal(X_full, X_cut, check_exact=True)

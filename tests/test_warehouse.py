"""Warehouse: marts exist, are populated, cleaned and internally consistent."""

from __future__ import annotations

import pandas as pd

from pulseiq.generator.calibration import headline_rates
from pulseiq.warehouse.build import MART_TABLES


def test_marts_exist_and_populated(small_con):
    for table in MART_TABLES:
        n = small_con.execute(f"select count(*) from {table}").fetchone()[0]
        assert n > 0, table


def test_dedupe_and_skew_removed(small_con, small_result):
    raw = len(small_result.tables["events"])
    dirt = small_result.ground_truth["dirt"]
    clean = small_con.execute("select count(*) from stg_events").fetchone()[0]
    assert clean == raw - dirt["duplicate_events"] - dirt["clock_skew_events"]
    nulls = small_con.execute("select count(*) from stg_events where platform is null").fetchone()[
        0
    ]
    assert nulls == 0


def test_funnel_monotonic(small_con):
    row = small_con.execute(
        "select sum(is_onboarded), sum(is_trial), sum(is_paid), count(*) from fct_funnel_user"
    ).fetchone()
    assert row[3] >= row[0] >= row[1] >= row[2] > 0


def test_retention_matches_pandas(small_con, small_result):
    tables = dict(small_result.tables)
    tables["events"] = tables["events"].drop_duplicates("event_id")
    expected = headline_rates(tables, pd.Timestamp(small_result.ground_truth["data_end"]))
    for n in (1, 7, 30):
        got = small_con.execute(
            "select sum(retained_users) / sum(eligible_users) from agg_retention_cohorts where day_n = ?",
            [n],
        ).fetchone()[0]
        assert abs(got - expected[f"d{n}_retention"]) < 1e-9, n


def test_exposures_contract(small_con):
    cols = [r[0] for r in small_con.execute("describe fct_experiment_exposures").fetchall()]
    for c in (
        "experiment_id",
        "user_id",
        "variant",
        "pre_sessions_14d",
        "d7_retained",
        "d7_eligible",
        "trial_started_in_test",
        "paid_30d",
        "platform",
        "country_tier",
    ):
        assert c in cols
    exps = {
        r[0]
        for r in small_con.execute(
            "select distinct experiment_id from fct_experiment_exposures"
        ).fetchall()
    }
    assert exps == {"onboarding_flow_v2", "paywall_redesign", "streak_reminder"}

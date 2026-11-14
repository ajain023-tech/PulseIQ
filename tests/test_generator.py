"""Generator: determinism, schema, integrity, dirt and experiment allocation."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
from scipy import stats

from pulseiq.generator import generate
from pulseiq.generator.write import write_result

EXPECTED_COLUMNS = {
    "users": [
        "user_id",
        "signup_ts",
        "country",
        "platform",
        "acquisition_channel",
        "device_tier",
        "app_version_at_signup",
    ],
    "events": [
        "event_id",
        "user_id",
        "session_id",
        "event_ts",
        "event_name",
        "properties",
        "platform",
        "app_version",
    ],
    "sessions": ["session_id", "user_id", "session_start", "session_end", "n_events"],
    "experiment_assignments": ["experiment_id", "user_id", "variant", "assigned_at"],
    "subscriptions": [
        "subscription_id",
        "user_id",
        "plan",
        "price_usd",
        "currency",
        "started_at",
        "trial_started_at",
        "canceled_at",
        "status",
    ],
    "invoices": [
        "invoice_id",
        "subscription_id",
        "user_id",
        "charged_at",
        "amount_usd",
        "is_refund",
    ],
}


def test_determinism_frames(small_result):
    again = generate("small", seed=42)
    for name, frame in small_result.tables.items():
        pd.testing.assert_frame_equal(frame, again.tables[name], check_exact=True)


def test_determinism_parquet_bytes(small_result, tmp_path):
    write_result(small_result, tmp_path / "a")
    write_result(generate("small", seed=42), tmp_path / "b")
    for f in sorted((tmp_path / "a").glob("*.parquet")):
        a = hashlib.sha256(f.read_bytes()).hexdigest()
        b = hashlib.sha256((tmp_path / "b" / f.name).read_bytes()).hexdigest()
        assert a == b, f.name


def test_different_seed_differs(small_result):
    other = generate("small", seed=7)
    assert not small_result.tables["users"]["signup_ts"].equals(other.tables["users"]["signup_ts"])


def test_schema(small_result):
    for name, cols in EXPECTED_COLUMNS.items():
        assert list(small_result.tables[name].columns) == cols, name
    ev = small_result.tables["events"]
    assert str(ev["event_ts"].dtype).startswith("datetime64")
    assert ev["event_id"].str.match(r"^e\d{9}$").all()


def test_no_orphans(small_result):
    t = small_result.tables
    users = set(t["users"]["user_id"])
    assert set(t["events"]["user_id"]) <= users
    assert set(t["sessions"]["user_id"]) <= users
    assert set(t["experiment_assignments"]["user_id"]) <= users
    assert set(t["invoices"]["subscription_id"]) <= set(t["subscriptions"]["subscription_id"])
    sess_ids = set(t["sessions"]["session_id"])
    ev_sess = t["events"]["session_id"].dropna()
    assert set(ev_sess) <= sess_ids


def test_dirt_rates(small_result):
    ev = small_result.tables["events"]
    truth = small_result.ground_truth["dirt"]
    n_clean = len(ev) - truth["duplicate_events"]
    assert ev["event_id"].duplicated().sum() == truth["duplicate_events"]
    assert abs(truth["duplicate_events"] / n_clean - 0.003) < 0.0005
    assert abs(truth["clock_skew_events"] / n_clean - 0.002) < 0.0005
    users = small_result.tables["users"].set_index("user_id")["signup_ts"]
    skewed = ev.drop_duplicates("event_id")
    before = (skewed["event_ts"] < skewed["user_id"].map(users)).sum()
    assert before == truth["clock_skew_events"]
    assert ev["platform"].isna().sum() >= truth["null_platform_events"]


def test_sessions_have_2_to_15_events(small_result):
    s = small_result.tables["sessions"]
    end = pd.Timestamp(small_result.ground_truth["data_end"])
    complete = s[s["session_end"] < end]
    assert complete["n_events"].min() >= 2
    # Regular sessions hold <= 15 events; the signup session also carries the
    # onboarding prefix and a few inserted paywall/trial events.
    later = complete.merge(small_result.tables["users"], on="user_id")
    later = later[later["session_start"] > later["signup_ts"]]
    assert later["n_events"].max() <= 15 + 3


def test_allocation_balanced_except_srm(small_result):
    a = small_result.tables["experiment_assignments"]
    for exp_id in ("onboarding_flow_v2", "paywall_redesign"):
        counts = a[a["experiment_id"] == exp_id]["variant"].value_counts()
        p = stats.chisquare([counts["control"], counts["treatment"]]).pvalue
        assert p > 0.001, (exp_id, counts.to_dict())
    bug = small_result.ground_truth["experiments"]["streak_reminder"]["srm_bug"]
    assert bug["rows_dropped"] > 0
    s = a[a["experiment_id"] == "streak_reminder"]
    assert (s["variant"] == "treatment").sum() < (s["variant"] == "control").sum()


def test_ground_truth_contents(small_result):
    gt = small_result.ground_truth
    assert set(gt["experiments"]) == {"onboarding_flow_v2", "paywall_redesign", "streak_reminder"}
    onb = gt["experiments"]["onboarding_flow_v2"]["true_effects_abs"]
    assert np.isclose(onb["paid_30d"], -0.005)
    assert abs(onb["onboarding_completed"] - 0.03) < 0.002
    assert np.isclose(
        gt["experiments"]["streak_reminder"]["true_effects_abs"]["d7_retained"], 0.015
    )
    assert np.isclose(
        gt["experiments"]["paywall_redesign"]["true_effects_rel"]["trial_started_in_test"],
        0.08,
        atol=0.005,
    )
    assert gt["true_retention_drivers"]
    assert "validation only" in gt["_note"].lower()

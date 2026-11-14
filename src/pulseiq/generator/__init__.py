"""Seeded synthetic event generator with known ground truth.

``generate(size, seed)`` simulates users of a fitness/habit subscription app, their
sessions and events, three planted experiments and billing, and returns every raw
table plus a ground-truth dictionary describing exactly what was planted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from pulseiq.config import SIZES, START_DATE

from . import experiments as ex
from .billing import simulate_billing
from .lifecycle import (
    FEATURES,
    PAYWALL_CODE,
    Sessions,
    build_sessions,
    early_active,
    hazard_multiplier,
    sigmoid,
    simulate_later_activity,
    simulate_onboarding,
)
from .params import EXPERIMENTS, TRUE_RETENTION_DRIVERS, GeneratorParams
from .users import simulate_users

__all__ = ["GenerationResult", "generate"]

DAY = 86_400
STREAMS = (
    "users",
    "assign",
    "srm",
    "onboarding",
    "early",
    "sessions_a",
    "later",
    "sessions_b",
    "monetization",
    "paywall",
    "sessions_c",
    "billing",
    "events",
    "dirt",
)

# Event-kind sort priority inside identical timestamps.
SEQ = {"app_install": 0, "session_start": 1, "signup": 2, "session_end": 9}


@dataclass
class GenerationResult:
    """All generated tables (public columns only) and the ground truth."""

    tables: dict[str, pd.DataFrame]
    ground_truth: dict
    internals: dict = field(default_factory=dict, repr=False)


def _epoch(d) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())


def _concat_sessions(parts: list[Sessions]) -> Sessions:
    """Concatenate session batches, re-basing middle-event session indices."""
    offset = 0
    mids = []
    for p in parts:
        mids.append(p.mid_session + offset)
        offset += p.size
    return Sessions(
        np.concatenate([p.user_idx for p in parts]),
        np.concatenate([p.block for p in parts]),
        np.concatenate([p.start_ts for p in parts]),
        np.concatenate([p.n_mid for p in parts]),
        np.concatenate([p.mid_codes for p in parts]),
        np.concatenate([p.mid_offsets for p in parts]),
        np.concatenate(mids),
        np.concatenate([p.duration for p in parts]),
    )


def _session_counts(rng, user_idx, eng, act) -> np.ndarray:
    return 1 + rng.poisson(act.sessions_base + act.sessions_slope * eng[user_idx])


def _rand_choice_per_group(rng, group: np.ndarray, n_groups: int) -> np.ndarray:
    """Pick one random element index per group id (returns -1 for empty groups)."""
    out = np.full(n_groups, -1, dtype=np.int64)
    if group.size == 0:
        return out
    keys = rng.random(group.size)
    order = np.lexsort((keys, group))
    g_sorted = group[order]
    first = np.ones(g_sorted.size, dtype=bool)
    first[1:] = g_sorted[1:] != g_sorted[:-1]
    out[g_sorted[first]] = order[first]
    return out


def generate(
    size: str = "full", seed: int = 42, params: GeneratorParams | None = None
) -> GenerationResult:
    """Simulate the full dataset deterministically from ``seed``."""
    params = params or GeneratorParams()
    cfg = SIZES[size]
    act, mon, eff = params.activity, params.monetization, params.effects
    rngs = {
        name: np.random.default_rng(s)
        for name, s in zip(STREAMS, np.random.SeedSequence(seed).spawn(len(STREAMS)), strict=True)
    }
    start_epoch = _epoch(START_DATE)
    data_end = start_epoch + cfg.n_days * DAY

    # ---- users -----------------------------------------------------------
    users = simulate_users(rngs["users"], cfg.n_users, cfg.n_days, start_epoch, params)
    n = len(users)
    z = users["_z"].to_numpy()
    eng = users["_eng"].to_numpy()
    signup_ts = users["_signup_ts"].to_numpy().astype(np.int64)
    signup_day = users["_signup_day"].to_numpy()
    platform = users["platform"].to_numpy()
    tier = users["country_tier"].to_numpy()

    # ---- signup-time experiments -----------------------------------------
    spec = {s.experiment_id: s for s in EXPERIMENTS}
    windows = {k: ex.scaled_window(s, cfg.n_days) for k, s in spec.items()}
    onb_exp = ex.assign_at_signup(rngs["assign"], signup_day, windows["onboarding_flow_v2"], 0.5)
    streak = ex.assign_at_signup(rngs["assign"], signup_day, windows["streak_reminder"], 0.5)
    srm_dropped = ex.plant_srm_bug(rngs["srm"], streak, platform, eff.streak_srm_treatment_loss)

    # ---- onboarding -------------------------------------------------------
    onb = simulate_onboarding(rngs["onboarding"], z, onb_exp.treatment, params)

    # ---- stage A: blocks 0-2 ---------------------------------------------
    early = early_active(rngs["early"], z, act)
    observable = lambda b: signup_ts + b * DAY < data_end  # noqa: E731
    rows_u, rows_b = [np.arange(n)], [np.zeros(n, dtype=np.int64)]
    for b in (1, 2):
        mask = early[:, b - 1] & observable(b)
        rows_u.append(np.flatnonzero(mask))
        rows_b.append(np.full(mask.sum(), b))
    au, ab = np.concatenate(rows_u), np.concatenate(rows_b)
    sess_a = build_sessions(
        rngs["sessions_a"],
        au,
        ab,
        _session_counts(rngs["sessions_a"], au, eng, act),
        signup_ts,
        eng,
        act,
    )
    mid_user_a = sess_a.user_idx[sess_a.mid_session]
    reminder72 = np.bincount(mid_user_a[sess_a.mid_codes == 4], minlength=n)
    workout72 = np.bincount(mid_user_a[sess_a.mid_codes == 0], minlength=n)
    early_days = early.sum(axis=1)

    # ---- hazard + streak_reminder effect -----------------------------------
    m = hazard_multiplier(z, reminder72, workout72, early_days, act)
    pop_s = streak.in_population
    r_streak = ex.solve_streak_multiplier(m[pop_s], z[pop_s], eff.streak_d7_pp, params)
    m_actual = np.where(streak.treatment, m * r_streak, m)
    streak_truth = ex.retention_truth(m[pop_s], z[pop_s], r_streak, (7, 30), params)
    streak_truth["d1_retained"] = 0.0

    # ---- stage B: blocks 3.. ----------------------------------------------
    n_blocks = cfg.n_days + 1
    later, life = simulate_later_activity(rngs["later"], m_actual, z, n_blocks, act)
    blocks = np.arange(3, n_blocks)
    obs_b = (signup_ts[:, None] + blocks[None, :] * DAY) < data_end
    bu, bcol = np.nonzero(later & obs_b)
    bb = blocks[bcol]
    sess_b = build_sessions(
        rngs["sessions_b"],
        bu,
        bb,
        _session_counts(rngs["sessions_b"], bu, eng, act),
        signup_ts,
        eng,
        act,
        first_block0_at_signup=False,
    )
    sess = _concat_sessions([sess_a, sess_b])

    # ---- new-user monetization ----------------------------------------------
    rng_m = rngs["monetization"]
    p_trial = sigmoid(
        mon.trial_intercept + mon.trial_slope * z + np.vectorize(mon.trial_tier_shift.get)(tier)
    )
    p_paid = sigmoid(
        mon.paid_intercept + mon.paid_slope * z + np.vectorize(mon.paid_tier_shift.get)(tier)
    )
    pop_o = onb_exp.in_population
    p_onb_t = np.minimum(onb.p_control + eff.onboarding_completion_pp, 0.995)
    paid_factor = ex.solve_paid_factor(
        onb.p_control[pop_o], p_onb_t[pop_o], p_trial[pop_o], p_paid[pop_o], eff.onboarding_paid_pp
    )
    trial_new = onb.completed & (rng_m.random(n) < p_trial)
    converts_new = rng_m.random(n) < p_paid * np.where(onb_exp.treatment, paid_factor, 1.0)
    plan_new = np.where(rng_m.random(n) < mon.annual_share, "annual", "monthly")
    later_trial = trial_new & (rng_m.random(n) >= mon.trial_day0_share)
    sess_end = sess.start_ts + sess.duration
    cand = (sess.block >= 1) & (sess.block < mon.trial_window_days) & (sess_end < data_end)
    cand_idx = np.flatnonzero(cand & later_trial[sess.user_idx])
    pick = _rand_choice_per_group(rng_m, sess.user_idx[cand_idx], n)
    trial_session = np.where(pick >= 0, cand_idx[np.maximum(pick, 0)], -1)
    trial_session = np.where(later_trial, trial_session, -1)  # -1 => day-0 trial
    onb_truth = {
        "onboarding_completed": float(np.mean(p_onb_t[pop_o] - onb.p_control[pop_o])),
        "trial_started_14d": float(
            np.mean((p_onb_t[pop_o] - onb.p_control[pop_o]) * p_trial[pop_o])
        ),
        "paid_30d": float(
            np.mean(p_onb_t[pop_o] * p_trial[pop_o] * p_paid[pop_o] * paid_factor)
            - np.mean(onb.p_control[pop_o] * p_trial[pop_o] * p_paid[pop_o])
        ),
        "d1_retained": 0.0,
        "d7_retained": 0.0,
        "d30_retained": 0.0,
    }

    # ---- paywall_redesign (existing users) -------------------------------------
    rng_p = rngs["paywall"]
    pw_start = start_epoch + windows["paywall_redesign"][0] * DAY
    pw_end = start_epoch + windows["paywall_redesign"][1] * DAY
    recent = (sess.start_ts >= pw_start - 28 * DAY) & (sess.start_ts < pw_start)
    had_recent = np.bincount(sess.user_idx[recent], minlength=n) > 0
    pop_p = (signup_ts <= pw_start - 14 * DAY) & ~trial_new & had_recent
    pw_users = np.flatnonzero(pop_p)
    assigned_pw = pw_start + rng_p.integers(0, 6 * 3600, size=n)
    pre_mask = (sess.start_ts >= assigned_pw[sess.user_idx] - 14 * DAY) & (
        sess.start_ts < assigned_pw[sess.user_idx]
    )
    pre_sessions = np.bincount(sess.user_idx[pre_mask], minlength=n)
    pw_treat = np.zeros(n, dtype=bool)
    pw_treat[pw_users] = rng_p.random(pw_users.size) < 0.5
    pc = np.clip(
        eff.paywall_trial_intercept + eff.paywall_trial_per_session * pre_sessions,
        0,
        eff.paywall_trial_cap,
    )
    pt = np.minimum(pc * (1 + eff.paywall_trial_relative), 0.95)
    p_pw = np.where(pw_treat, pt, pc)
    trial_pw = pop_p & (rng_p.random(n) < p_pw)
    converts_pw = rng_p.random(n) < p_paid
    plan_pw = np.where(rng_p.random(n) < mon.annual_share, "annual", "monthly")
    in_test = (
        (sess.start_ts >= assigned_pw[sess.user_idx]) & (sess_end < pw_end) & pop_p[sess.user_idx]
    )
    in_test_idx = np.flatnonzero(in_test)
    pick_pw = _rand_choice_per_group(rng_p, sess.user_idx[in_test_idx], n)
    first_test = np.full(n, -1, dtype=np.int64)
    if in_test_idx.size:
        order = np.lexsort((sess.start_ts[in_test_idx], sess.user_idx[in_test_idx]))
        su_sorted = sess.user_idx[in_test_idx][order]
        firsts = np.ones(su_sorted.size, dtype=bool)
        firsts[1:] = su_sorted[1:] != su_sorted[:-1]
        first_test[su_sorted[firsts]] = in_test_idx[order][firsts]
    need_extra = trial_pw & (pick_pw < 0)
    extra_users = np.flatnonzero(need_extra)
    extra_start = assigned_pw[extra_users] + (
        rng_p.random(extra_users.size) * (pw_end - assigned_pw[extra_users] - 3600)
    ).astype(np.int64)
    extra_block = (extra_start - signup_ts[extra_users]) // DAY
    sess_c = build_sessions(
        rngs["sessions_c"],
        extra_users,
        extra_block,
        np.ones(extra_users.size, dtype=np.int64),
        signup_ts,
        eng,
        act,
        first_block0_at_signup=False,
        fixed_start=extra_start,
    )
    base_c = sess.size
    sess = _concat_sessions([sess, sess_c])
    sess_end = sess.start_ts + sess.duration
    pw_trial_session = np.full(n, -1, dtype=np.int64)
    pw_trial_session[trial_pw & (pick_pw >= 0)] = in_test_idx[pick_pw[trial_pw & (pick_pw >= 0)]]
    pw_trial_session[extra_users] = base_c + np.arange(extra_users.size)
    first_test[extra_users] = np.where(
        first_test[extra_users] < 0, pw_trial_session[extra_users], first_test[extra_users]
    )
    pw_truth_abs = float(np.mean(pt[pop_p] - pc[pop_p]))
    pw_truth_rel = float(np.mean(pt[pop_p]) / np.mean(pc[pop_p]) - 1)

    # ---- event assembly ---------------------------------------------------------
    rng_e = rngs["events"]
    is_first = (sess.block == 0) & (sess.start_ts == signup_ts[sess.user_idx])
    first_sess = np.full(n, -1, dtype=np.int64)
    first_sess[sess.user_idx[is_first]] = np.flatnonzero(is_first)

    ev_user: list[np.ndarray] = []
    ev_sess: list[np.ndarray] = []
    ev_ts: list[np.ndarray] = []
    ev_name: list[np.ndarray] = []
    ev_prop: list[np.ndarray] = []

    def add(u, s, t, name, prop):
        k = np.size(u)
        ev_user.append(np.asarray(u, dtype=np.int64))
        ev_sess.append(np.asarray(s, dtype=np.int64))
        ev_ts.append(np.asarray(t, dtype=np.int64))
        ev_name.append(np.broadcast_to(np.asarray(name, dtype=object), (k,)).copy())
        ev_prop.append(np.broadcast_to(np.asarray(prop, dtype=object), (k,)).copy())

    # Prefix events of the signup session (install, signup, onboarding, paywall, trial).
    allu = np.arange(n)
    fs = first_sess
    t0 = signup_ts
    add(allu, fs, t0, "app_install", '{"source": "store"}')
    add(allu, fs, t0, "signup", "{}")
    cursor = t0.copy()
    for step in range(1, 6):
        viewed = onb.last_step_viewed >= step
        cursor = cursor + np.where(viewed, rng_e.integers(5, 20, size=n), 0)
        add(
            allu[viewed],
            fs[viewed],
            cursor[viewed],
            "onboarding_step_viewed",
            f'{{"step": {step}}}',
        )
        done = onb.steps_completed >= step
        cursor = cursor + np.where(done, rng_e.integers(15, 60, size=n), 0)
        add(allu[done], fs[done], cursor[done], "onboarding_step_completed", f'{{"step": {step}}}')
    c = onb.completed
    cursor = cursor + np.where(c, 2, 0)
    add(allu[c], fs[c], cursor[c], "onboarding_completed", "{}")
    cursor = cursor + np.where(c, rng_e.integers(3, 15, size=n), 0)
    add(
        allu[c],
        fs[c],
        cursor[c],
        "paywall_viewed",
        '{"source": "onboarding", "paywall_variant": "v1"}',
    )
    d0 = trial_new & (trial_session < 0)
    cursor = cursor + np.where(d0, rng_e.integers(10, 40, size=n), 0)
    for plan in ("monthly", "annual"):
        mk = d0 & (plan_new == plan)
        add(allu[mk], fs[mk], cursor[mk], "trial_started", f'{{"plan": "{plan}"}}')
    shift = np.zeros(sess.size, dtype=np.int64)
    shift[fs] = cursor - t0 + 5
    trial_ts = np.where(d0, cursor, -1)

    # Generic session events.
    sidx = np.arange(sess.size)
    s_start = sess.start_ts
    s_end = s_start + shift + sess.duration
    add(sess.user_idx, sidx, s_start, "session_start", "{}")
    add(sess.user_idx, sidx, s_end, "session_end", "{}")
    mid_ts = s_start[sess.mid_session] + shift[sess.mid_session] + sess.mid_offsets
    mid_user = sess.user_idx[sess.mid_session]
    for code, feat in enumerate(FEATURES):
        mk = sess.mid_codes == code
        add(
            mid_user[mk],
            sess.mid_session[mk],
            mid_ts[mk],
            "feature_used",
            f'{{"feature": "{feat}"}}',
        )
    mk = sess.mid_codes == PAYWALL_CODE
    add(
        mid_user[mk],
        sess.mid_session[mk],
        mid_ts[mk],
        "paywall_viewed",
        '{"source": "feature_gate", "paywall_variant": "v1"}',
    )

    # Later new-user trials, inserted just before the chosen session ends.
    lt = np.flatnonzero(trial_session >= 0)
    ls = trial_session[lt]
    add(
        lt,
        ls,
        s_end[ls] - 2,
        "paywall_viewed",
        '{"source": "feature_gate", "paywall_variant": "v1"}',
    )
    for plan in ("monthly", "annual"):
        mk = plan_new[lt] == plan
        add(lt[mk], ls[mk], s_end[ls[mk]] - 1, "trial_started", f'{{"plan": "{plan}"}}')
    trial_ts[lt] = s_end[ls] - 1

    # paywall_redesign exposure (first in-test session) and campaign trials.
    exp_u = np.flatnonzero(first_test >= 0)
    for variant, flag in (("v1", False), ("v2", True)):
        mk = pw_treat[exp_u] == flag
        uu = exp_u[mk]
        ss = first_test[uu]
        add(
            uu,
            ss,
            s_start[ss] + 1,
            "paywall_viewed",
            f'{{"source": "campaign", "paywall_variant": "{variant}"}}',
        )
    tu = np.flatnonzero(trial_pw)
    ts_ = pw_trial_session[tu]
    for plan in ("monthly", "annual"):
        mk = plan_pw[tu] == plan
        add(tu[mk], ts_[mk], s_end[ts_[mk]] - 1, "trial_started", f'{{"plan": "{plan}"}}')
    pw_trial_ts = np.full(n, -1, dtype=np.int64)
    pw_trial_ts[tu] = s_end[ts_] - 1

    # Streak reminder pushes for treatment users (first session of days 1-13).
    blk_first = np.ones(sess.size, dtype=bool)
    order = np.lexsort((s_start, sess.block, sess.user_idx))
    ou, ob = sess.user_idx[order], sess.block[order]
    blk_first_sorted = np.ones(order.size, dtype=bool)
    blk_first_sorted[1:] = (ou[1:] != ou[:-1]) | (ob[1:] != ob[:-1])
    blk_first[order] = blk_first_sorted
    push = blk_first & streak.treatment[sess.user_idx] & (sess.block >= 1) & (sess.block <= 13)
    pidx = np.flatnonzero(push)
    pu = sess.user_idx[pidx]
    add(
        pu,
        pidx,
        s_start[pidx] - rng_e.integers(300, 3600, size=pidx.size),
        "push_received",
        '{"campaign": "streak_reminder"}',
    )
    opened = rng_e.random(pidx.size) < 0.5
    add(
        pu[opened],
        pidx[opened],
        s_start[pidx[opened]] - 10,
        "push_opened",
        '{"campaign": "streak_reminder"}',
    )

    # ---- billing ------------------------------------------------------------------
    trials = pd.concat(
        [
            pd.DataFrame(
                {
                    "user_idx": np.flatnonzero(trial_new),
                    "trial_ts": trial_ts[trial_new],
                    "plan": plan_new[trial_new],
                    "converts": converts_new[trial_new],
                }
            ),
            pd.DataFrame(
                {
                    "user_idx": tu,
                    "trial_ts": pw_trial_ts[tu],
                    "plan": plan_pw[tu],
                    "converts": converts_pw[tu],
                }
            ),
        ],
        ignore_index=True,
    )
    subs, invoices, bill_ev = simulate_billing(
        rngs["billing"], trials, signup_ts, life, tier, data_end, params
    )
    add(
        bill_ev["user_idx"].to_numpy(),
        np.full(len(bill_ev), -1),
        bill_ev["ts"].to_numpy(),
        bill_ev["event_name"].to_numpy(),
        bill_ev["properties"].to_numpy(),
    )

    # ---- finalize events ------------------------------------------------------------
    e_user = np.concatenate(ev_user)
    e_sess = np.concatenate(ev_sess)
    e_ts = np.concatenate(ev_ts)
    e_name = np.concatenate(ev_name)
    e_prop = np.concatenate(ev_prop)
    keep = e_ts < data_end
    e_user, e_sess, e_ts, e_name, e_prop = (
        e_user[keep],
        e_sess[keep],
        e_ts[keep],
        e_name[keep],
        e_prop[keep],
    )
    seq = pd.Series(e_name).map(SEQ).fillna(5).to_numpy()
    order = np.lexsort((np.arange(e_ts.size), seq, e_ts, e_user))
    e_user, e_sess, e_ts, e_name, e_prop = (
        e_user[order],
        e_sess[order],
        e_ts[order],
        e_name[order],
        e_prop[order],
    )

    # Session ids ordered by (user, start).
    s_keep = s_start < data_end
    s_order = np.lexsort((np.arange(sess.size), s_start, sess.user_idx))
    s_order = s_order[s_keep[s_order]]
    session_id = np.full(sess.size, None, dtype=object)
    session_id[s_order] = np.char.add(
        "s", np.char.zfill(np.arange(1, s_order.size + 1).astype(str), 8)
    )
    n_events_per_session = np.bincount(e_sess[e_sess >= 0], minlength=sess.size)

    versions = np.array(params.signup.app_versions)
    ev_day = (e_ts - start_epoch) // DAY
    cal_version = np.minimum(ev_day * len(versions) // cfg.n_days, len(versions) - 1)
    user_version = np.searchsorted(versions, users["app_version_at_signup"].to_numpy())
    app_version = versions[np.maximum(cal_version, user_version[e_user])]

    user_ids = users["user_id"].to_numpy()
    events = pd.DataFrame(
        {
            "event_id": np.char.add("e", np.char.zfill(np.arange(1, e_ts.size + 1).astype(str), 9)),
            "user_id": user_ids[e_user],
            "session_id": np.where(e_sess >= 0, session_id[np.maximum(e_sess, 0)], None),
            "_ts": e_ts,
            "event_name": e_name.astype(str),
            "properties": e_prop.astype(str),
            "platform": platform[e_user].astype(object),
            "app_version": app_version,
        }
    )

    # ---- dirt -------------------------------------------------------------------------
    rng_d = rngs["dirt"]
    dirt = params.dirt
    n_ev = len(events)
    perm = rng_d.permutation(n_ev)
    n_dup = int(round(dirt.duplicate_event_rate * n_ev))
    n_skew = int(round(dirt.clock_skew_rate * n_ev))
    n_null = int(round(dirt.null_platform_rate * n_ev))
    dup_idx = np.sort(perm[:n_dup])
    skew_idx = np.sort(perm[n_dup : n_dup + n_skew])
    null_idx = np.sort(perm[n_dup + n_skew : n_dup + n_skew + n_null])
    user_pos = e_user
    ts_col = events["_ts"].to_numpy().copy()
    ts_col[skew_idx] = signup_ts[user_pos[skew_idx]] - rng_d.integers(
        3600, 3 * DAY, size=skew_idx.size
    )
    events["_ts"] = ts_col
    plat = events["platform"].to_numpy().copy()
    plat[null_idx] = None
    events["platform"] = plat
    dups = events.iloc[dup_idx]
    events = pd.concat([events, dups], ignore_index=True)
    events = events.sort_values(["user_id", "_ts", "event_id"], kind="mergesort").reset_index(
        drop=True
    )

    # ---- public tables ------------------------------------------------------------------
    def to_dt(sec: np.ndarray) -> pd.Series:
        s = pd.Series(sec, dtype="float64")
        s[s < 0] = np.nan
        return pd.to_datetime(s, unit="s").astype("datetime64[us]")

    events.insert(3, "event_ts", to_dt(events.pop("_ts").to_numpy()))
    users_pub = users[
        [
            "user_id",
            "country",
            "platform",
            "acquisition_channel",
            "device_tier",
            "app_version_at_signup",
        ]
    ].copy()
    users_pub.insert(1, "signup_ts", to_dt(signup_ts))

    sk = s_order
    sessions_pub = pd.DataFrame(
        {
            "session_id": session_id[sk].astype(str),
            "user_id": user_ids[sess.user_idx[sk]],
            "session_start": to_dt(s_start[sk]).to_numpy(),
            "session_end": to_dt(s_end[sk]).to_numpy(),
            "n_events": n_events_per_session[sk],
        }
    )

    assign_rows = []
    for exp_id, e_obj in (("onboarding_flow_v2", onb_exp), ("streak_reminder", streak)):
        idx = np.flatnonzero(e_obj.in_population & e_obj.logged)
        assign_rows.append(
            pd.DataFrame(
                {
                    "experiment_id": exp_id,
                    "user_id": user_ids[idx],
                    "variant": np.where(e_obj.treatment[idx], "treatment", "control"),
                    "assigned_at": to_dt(signup_ts[idx]).to_numpy(),
                }
            )
        )
    assign_rows.append(
        pd.DataFrame(
            {
                "experiment_id": "paywall_redesign",
                "user_id": user_ids[pw_users],
                "variant": np.where(pw_treat[pw_users], "treatment", "control"),
                "assigned_at": to_dt(assigned_pw[pw_users]).to_numpy(),
            }
        )
    )
    assignments = pd.concat(assign_rows, ignore_index=True)

    subs_pub = pd.DataFrame(
        {
            "subscription_id": subs["subscription_id"],
            "user_id": user_ids[subs["user_idx"].to_numpy()],
            "plan": subs["plan"],
            "price_usd": subs["price_usd"],
            "currency": subs["currency"],
            "started_at": to_dt(subs["_started_at"].to_numpy()).to_numpy(),
            "trial_started_at": to_dt(subs["_trial_started_at"].to_numpy()).to_numpy(),
            "canceled_at": to_dt(subs["_canceled_at"].to_numpy()).to_numpy(),
            "status": subs["status"],
        }
    )
    inv_pub = pd.DataFrame(
        {
            "invoice_id": invoices["invoice_id"],
            "subscription_id": invoices["subscription_id"],
            "user_id": user_ids[invoices["user_idx"].to_numpy()],
            "charged_at": to_dt(invoices["_charged_at"].to_numpy()).to_numpy(),
            "amount_usd": invoices["amount_usd"],
            "is_refund": invoices["is_refund"].astype(bool),
        }
    )
    exp_rows = []
    for s in EXPERIMENTS:
        a, b = windows[s.experiment_id]
        exp_rows.append(
            {
                "experiment_id": s.experiment_id,
                "name": s.name,
                "hypothesis": s.hypothesis,
                "start_date": pd.Timestamp(START_DATE) + pd.Timedelta(days=a),
                "end_date": pd.Timestamp(START_DATE) + pd.Timedelta(days=b),
                "population": s.population,
                "primary_metric": s.primary_metric,
                "guardrail_metrics": ",".join(s.guardrail_metrics),
                "secondary_metrics": ",".join(s.secondary_metrics),
                "allocation": s.allocation,
            }
        )
    experiments_pub = pd.DataFrame(exp_rows)
    experiments_pub["start_date"] = experiments_pub["start_date"].dt.date
    experiments_pub["end_date"] = experiments_pub["end_date"].dt.date

    tables = {
        "users": users_pub,
        "events": events,
        "sessions": sessions_pub,
        "experiment_assignments": assignments,
        "subscriptions": subs_pub,
        "invoices": inv_pub,
        "experiments": experiments_pub,
    }

    # ---- ground truth ---------------------------------------------------------------------
    def counts(e_obj):
        logged = e_obj.in_population & e_obj.logged
        return {
            "intended_population": int(e_obj.in_population.sum()),
            "logged_control": int((logged & ~e_obj.treatment).sum()),
            "logged_treatment": int((logged & e_obj.treatment).sum()),
        }

    truth = {
        "_note": "FOR VALIDATION ONLY - library code and models must never read this file.",
        "seed": seed,
        "size": size,
        "n_users": cfg.n_users,
        "n_days": cfg.n_days,
        "start_date": START_DATE.isoformat(),
        "data_end": (pd.Timestamp(START_DATE) + pd.Timedelta(days=cfg.n_days)).isoformat(),
        "params": params.to_dict(),
        "experiments": {
            "onboarding_flow_v2": {
                "window_days": list(windows["onboarding_flow_v2"]),
                **counts(onb_exp),
                "true_effects_abs": onb_truth,
                "paid_factor_on_treatment": paid_factor,
                "srm_bug": None,
            },
            "paywall_redesign": {
                "window_days": list(windows["paywall_redesign"]),
                "intended_population": int(pop_p.sum()),
                "logged_control": int((pop_p & ~pw_treat).sum()),
                "logged_treatment": int((pop_p & pw_treat).sum()),
                "true_effects_abs": {"trial_started_in_test": pw_truth_abs},
                "true_effects_rel": {"trial_started_in_test": pw_truth_rel},
                "pre_period_covariate": "sessions in the 14 days before assigned_at (pre_sessions_14d)",
                "srm_bug": None,
            },
            "streak_reminder": {
                "window_days": list(windows["streak_reminder"]),
                **counts(streak),
                "true_effects_abs": {**streak_truth, "trial_started_14d": 0.0, "paid_30d": 0.0},
                "hazard_multiplier_on_treatment": r_streak,
                "srm_bug": {
                    "description": "Android treatment users silently dropped from the assignment log",
                    "platform": "android",
                    "variant": "treatment",
                    "rows_dropped": srm_dropped,
                },
            },
        },
        "true_retention_drivers": list(TRUE_RETENTION_DRIVERS),
        "dirt": {
            "duplicate_events": int(n_dup),
            "clock_skew_events": int(n_skew),
            "null_platform_events": int(n_null),
        },
        "definitions": {
            "day_n_block": "day N = the 24 h block [signup_ts + N*24h, signup_ts + (N+1)*24h)",
            "dN_retained": "at least one session starting in day-N block",
            "dN_eligible": "signup_ts + (N+1)*24h <= data_end",
            "trial_started_14d": "trial started within 14 days of signup",
            "paid_30d": "subscription started within 30 days of signup (eligible if signup + 30d <= data_end)",
        },
    }
    return GenerationResult(
        tables=tables, ground_truth=truth, internals={"life": life, "m": m_actual}
    )

"""User lifecycle: onboarding, daily activity, sessions and in-session events.

The model is two-stage so that early *habits* can causally change later retention:

1. Blocks 0–2 (the first 72 h): onboarding, early activity and in-app events.
2. Features counted from those events (reminder_set, workout_log, active days)
   lower the churn hazard used to simulate activity from block 3 onwards.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .params import FEATURES, ActivityParams, GeneratorParams

DAY = 86_400
# Middle-event codes: 0..4 = feature_used(FEATURES[i]); 5 = paywall_viewed (feature gate)
PAYWALL_CODE = len(FEATURES)


def sigmoid(x: np.ndarray) -> np.ndarray:
    """Numerically safe logistic function."""
    return 1.0 / (1.0 + np.exp(-x))


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------
@dataclass
class OnboardingResult:
    """Per-user onboarding probabilities and realised outcome."""

    p_control: np.ndarray
    p_actual: np.ndarray
    completed: np.ndarray
    steps_completed: np.ndarray  # 0..5
    last_step_viewed: np.ndarray  # 1..5


def simulate_onboarding(
    rng: np.random.Generator,
    z: np.ndarray,
    treat_v2: np.ndarray,
    params: GeneratorParams,
) -> OnboardingResult:
    """Onboarding completion with the additive ``onboarding_flow_v2`` effect."""
    onb = params.onboarding
    p_control = sigmoid(onb.intercept + onb.slope * z)
    p_treat = np.minimum(p_control + params.effects.onboarding_completion_pp, 0.995)
    p_actual = np.where(treat_v2, p_treat, p_control)
    completed = rng.random(z.size) < p_actual
    drop_step = rng.choice(5, size=z.size, p=np.array(onb.drop_step_probs)) + 1
    steps_completed = np.where(completed, 5, drop_step - 1)
    last_step_viewed = np.where(completed, 5, drop_step)
    return OnboardingResult(p_control, p_actual, completed, steps_completed, last_step_viewed)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
@dataclass
class Sessions:
    """Flat arrays describing sessions (one element per session)."""

    user_idx: np.ndarray
    block: np.ndarray
    start_ts: np.ndarray
    n_mid: np.ndarray
    mid_codes: np.ndarray  # concatenated middle-event codes
    mid_offsets: np.ndarray  # seconds after session start (excluding prefix shift)
    mid_session: np.ndarray  # session index of each middle event (local to this batch)
    duration: np.ndarray  # seconds from start to session_end (excluding prefix shift)

    @property
    def size(self) -> int:
        """Number of sessions."""
        return int(self.user_idx.size)


def _event_type_probs(eng: np.ndarray) -> np.ndarray:
    """Per-event categorical probabilities over middle-event codes."""
    w = np.column_stack(
        [
            0.15 + 0.30 * eng,  # workout_log
            np.full_like(eng, 0.25),  # plan_view
            0.15 + 0.10 * eng,  # progress_chart
            np.full_like(eng, 0.05),  # social_share
            0.012 + 0.045 * eng,  # reminder_set
            np.full_like(eng, 0.03),  # paywall_viewed (feature gate)
        ]
    )
    return w / w.sum(axis=1, keepdims=True)


def build_sessions(
    rng: np.random.Generator,
    user_idx: np.ndarray,
    block: np.ndarray,
    n_sessions: np.ndarray,
    signup_ts: np.ndarray,
    eng: np.ndarray,
    act: ActivityParams,
    first_block0_at_signup: bool = True,
    fixed_start: np.ndarray | None = None,
) -> Sessions:
    """Expand (user, block, n_sessions) rows into sessions with middle events.

    ``fixed_start`` (optional, one per input row with n_sessions == 1) forces the
    start timestamp — used for campaign sessions added by experiments.
    """
    su = np.repeat(user_idx, n_sessions)
    sb = np.repeat(block, n_sessions)
    n = su.size
    if n == 0:
        e = np.zeros(0, dtype=np.int64)
        return Sessions(e, e, e, e, e.astype(np.int8), e, e, e)
    block_start = signup_ts[su] + sb * DAY
    if fixed_start is not None:
        start = np.repeat(fixed_start, n_sessions)
    else:
        start = block_start + rng.integers(0, 23 * 3600, size=n)
        # Within a (user, block) the first session of block 0 starts at signup.
        if first_block0_at_signup and n:
            row_starts = np.concatenate([[0], np.cumsum(n_sessions)[:-1]])
            first_of_row = np.zeros(n, dtype=bool)
            first_of_row[row_starts[n_sessions > 0]] = True
            b0_first = first_of_row & (sb == 0)
            b0_other = (~first_of_row) & (sb == 0)
            start = np.where(b0_first, signup_ts[su], start)
            start = np.where(b0_other, signup_ts[su] + rng.integers(3600, 23 * 3600, size=n), start)

    lam = act.events_base + act.events_slope * eng[su]
    n_mid = np.minimum(rng.poisson(lam), act.max_events_per_session - 2)
    total = int(n_mid.sum())
    mid_session = np.repeat(np.arange(n), n_mid)
    probs = _event_type_probs(eng[su][mid_session]) if total else np.zeros((0, 6))
    cum = probs.cumsum(axis=1)
    u = rng.random(total)
    codes = (u[:, None] > cum).sum(axis=1).astype(np.int8)
    gaps = (20 + rng.exponential(40, size=total)).astype(np.int64)
    csum = np.cumsum(gaps)
    group_start = np.concatenate([[0], np.cumsum(n_mid)[:-1]]).astype(np.int64)
    if total:
        prior = np.where(group_start > 0, csum[np.maximum(group_start - 1, 0)], 0)
    else:
        prior = np.zeros(n, dtype=np.int64)
    offsets = csum - np.repeat(prior, n_mid)
    last = np.zeros(n, dtype=np.int64)
    if total:
        ends = group_start + n_mid - 1
        has = n_mid > 0
        last[has] = offsets[ends[has]]
    duration = last + (20 + rng.exponential(40, size=n)).astype(np.int64)
    return Sessions(su, sb, start.astype(np.int64), n_mid, codes, offsets, mid_session, duration)


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------
def early_active(rng: np.random.Generator, z: np.ndarray, act: ActivityParams) -> np.ndarray:
    """Active flags for blocks 1 and 2 (shape n x 2)."""
    p = sigmoid(act.early_intercept + act.early_slope * z)
    return rng.random((z.size, 2)) < p[:, None]


def hazard_multiplier(
    z: np.ndarray,
    reminder72: np.ndarray,
    workout72: np.ndarray,
    early_days: np.ndarray,
    act: ActivityParams,
) -> np.ndarray:
    """Per-user churn-hazard multiplier m_u (lower = retained longer)."""
    log_m = (
        -act.hazard_z * z
        - act.reminder_effect * (reminder72 > 0)
        - act.workout_effect * np.minimum(workout72, act.workout_cap)
        - act.early_days_effect * early_days
    )
    return np.exp(log_m)


def survival(m: np.ndarray, day: int, act: ActivityParams) -> np.ndarray:
    """P(alive at block ``day``) for day >= 3 given hazard multiplier ``m``."""
    return np.exp(-m * act.base_hazard * float(day - 2) ** act.hazard_shape)


def p_alive_active(z: np.ndarray, act: ActivityParams) -> np.ndarray:
    """P(active on a day | still alive)."""
    return sigmoid(act.alive_intercept + act.alive_slope * z)


def simulate_later_activity(
    rng: np.random.Generator,
    m: np.ndarray,
    z: np.ndarray,
    n_blocks: int,
    act: ActivityParams,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (active matrix for blocks 3..n_blocks-1, latent lifetime L).

    A user is alive at block d iff (d - 2) <= L where L has survival
    exp(-m * base_hazard * t ** shape).
    """
    e = rng.exponential(1.0, size=m.size)
    life = (e / (m * act.base_hazard)) ** (1.0 / act.hazard_shape)
    days = np.arange(3, n_blocks)
    alive = (days[None, :] - 2) <= life[:, None]
    pa = p_alive_active(z, act)
    active = alive & (rng.random((m.size, days.size)) < pa[:, None])
    return active, life

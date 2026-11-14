"""Simulate users: dimensions, latent engagement and signup timestamps."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .params import CHANNELS, COUNTRIES, DEVICE_TIERS, PLATFORMS, GeneratorParams

DAY = 86_400
# Relative signup intensity by hour of day (local time is ignored for simplicity).
_HOUR_WEIGHTS = np.array(
    [
        1,
        0.6,
        0.4,
        0.3,
        0.3,
        0.5,
        1.0,
        1.8,
        2.4,
        2.4,
        2.2,
        2.2,
        2.6,
        2.4,
        2.2,
        2.2,
        2.4,
        2.8,
        3.2,
        3.6,
        3.8,
        3.4,
        2.6,
        1.6,
    ],
    dtype=float,
)


def _categorical(rng: np.random.Generator, mapping: dict, n: int) -> np.ndarray:
    keys = np.array(list(mapping))
    probs = np.array(list(mapping.values()), dtype=float)
    return keys[rng.choice(len(keys), size=n, p=probs / probs.sum())]


def signup_day_weights(n_days: int, params: GeneratorParams) -> np.ndarray:
    """Relative signup volume per day: weekday seasonality + marketing spike."""
    from pulseiq.config import START_DATE

    weekday0 = START_DATE.weekday()
    days = np.arange(n_days)
    weights = np.array(params.signup.weekday_multiplier)[(weekday0 + days) % 7]
    spike_start = int(round(params.signup.spike_start_frac * n_days))
    spike = (days >= spike_start) & (days < spike_start + params.signup.spike_days)
    weights = np.where(spike, weights * params.signup.spike_multiplier, weights)
    return weights / weights.sum()


def simulate_users(
    rng: np.random.Generator, n_users: int, n_days: int, start_epoch: int, params: GeneratorParams
) -> pd.DataFrame:
    """Return one row per user with dims, latent engagement ``z`` and signup times.

    Columns prefixed with ``_`` are internal simulation state and are never written.
    """
    eng = params.engagement
    country = _categorical(rng, {c: share for c, (_, share) in COUNTRIES.items()}, n_users)
    tier = np.array([COUNTRIES[c][0] for c in country])
    platform = _categorical(rng, PLATFORMS, n_users)
    channel = _categorical(rng, CHANNELS, n_users)

    device = np.empty(n_users, dtype=object)
    for plat, mix in eng.device_mix.items():
        mask = platform == plat
        device[mask] = np.array(DEVICE_TIERS)[rng.choice(3, size=mask.sum(), p=mix)]
    device = device.astype(str)

    base = rng.beta(eng.beta_a, eng.beta_b, size=n_users)
    z = np.log(base / (1 - base))
    z += np.vectorize(eng.channel_shift.get)(channel)
    z += np.vectorize(eng.platform_shift.get)(platform)
    z += np.vectorize(eng.device_shift.get)(device)
    z += np.vectorize(eng.country_tier_shift.get)(tier)

    day_weights = signup_day_weights(n_days, params)
    signup_day = np.sort(rng.choice(n_days, size=n_users, p=day_weights))
    hour = rng.choice(24, size=n_users, p=_HOUR_WEIGHTS / _HOUR_WEIGHTS.sum())
    second_of_hour = rng.integers(0, 3600, size=n_users)
    signup_ts = start_epoch + signup_day * DAY + hour * 3600 + second_of_hour

    versions = np.array(params.signup.app_versions)
    version_idx = np.minimum((signup_day * len(versions)) // n_days, len(versions) - 1)

    order = np.lexsort((np.arange(n_users), signup_ts))
    users = pd.DataFrame(
        {
            "country": country[order],
            "country_tier": tier[order],
            "platform": platform[order],
            "acquisition_channel": channel[order],
            "device_tier": device[order],
            "app_version_at_signup": versions[version_idx][order],
            "_signup_day": signup_day[order],
            "_signup_ts": signup_ts[order],
            "_z": z[order],
        }
    )
    users.insert(0, "user_id", [f"u{i:06d}" for i in range(1, n_users + 1)])
    users["_eng"] = 1.0 / (1.0 + np.exp(-users["_z"].to_numpy()))
    return users

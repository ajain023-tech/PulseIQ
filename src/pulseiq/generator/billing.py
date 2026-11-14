"""Subscriptions, invoices and server-side billing events."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .params import CANCEL_REASONS, GeneratorParams

DAY = 86_400


def _is_alive(ts: np.ndarray, signup_ts: np.ndarray, life: np.ndarray) -> np.ndarray:
    block = (ts - signup_ts) // DAY
    return (block < 3) | ((block - 2) <= life)


def simulate_billing(
    rng: np.random.Generator,
    trials: pd.DataFrame,
    signup_ts: np.ndarray,
    life: np.ndarray,
    tier: np.ndarray,
    data_end: int,
    params: GeneratorParams,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Turn trials into subscriptions, invoices and billing events.

    ``trials`` columns: user_idx, trial_ts, plan, converts (bool, latent intent to pay).
    Returns (subscriptions, invoices, events) with internal ``user_idx`` columns.
    """
    mon = params.monetization
    trials = trials.sort_values(["trial_ts", "user_idx"], kind="mergesort").reset_index(drop=True)
    n = len(trials)
    uidx = trials["user_idx"].to_numpy()
    trial_ts = trials["trial_ts"].to_numpy()
    plan = trials["plan"].to_numpy()
    utier = tier[uidx]
    price = np.where(
        plan == "annual",
        np.vectorize(mon.price_annual.get)(utier),
        np.vectorize(mon.price_monthly.get)(utier),
    ).astype(float)
    trial_end = trial_ts + mon.trial_length_days * DAY
    paid = trials["converts"].to_numpy() & (trial_end <= data_end)

    started_at = np.where(paid, trial_end, -1)
    canceled_at = np.full(n, -1, dtype=np.int64)
    status = np.where(trial_end > data_end, "trialing", "expired").astype(object)
    status[paid] = "active"

    inv_rows: list[tuple] = []
    ev_rows: list[tuple] = []
    sub_ids = np.array([f"sub{i:06d}" for i in range(1, n + 1)])
    for i in np.flatnonzero(paid):
        u = uidx[i]
        start = int(started_at[i])
        ev_rows.append((u, start, "subscription_started", i, None))
        period = 365 * DAY if plan[i] == "annual" else mon.renewal_days * DAY
        charge_ts = start
        k = 0
        while charge_ts <= data_end:
            inv_rows.append((i, u, charge_ts, price[i], False))
            if k > 0:
                ev_rows.append((u, charge_ts, "subscription_renewed", i, None))
            if rng.random() < mon.refund_rate:
                refund_ts = charge_ts + int(rng.integers(1, 6)) * DAY
                if refund_ts <= data_end:
                    inv_rows.append((i, u, refund_ts, -price[i], True))
                    ev_rows.append((u, refund_ts, "refund_issued", i, None))
                    canceled_at[i] = refund_ts
                    break
            next_ts = charge_ts + period
            if plan[i] == "annual":
                cancel_p = mon.annual_cancel_prob
            else:
                alive = _is_alive(
                    np.array([next_ts]), np.array([signup_ts[u]]), np.array([life[u]])
                )[0]
                cancel_p = mon.cancel_prob_active_user if alive else mon.cancel_prob_churned_user
            if rng.random() < cancel_p:
                cancel_ts = charge_ts + int(rng.integers(DAY, max(period - DAY, 2 * DAY)))
                if cancel_ts <= data_end:
                    canceled_at[i] = cancel_ts
                break
            charge_ts = next_ts
            k += 1
        if canceled_at[i] >= 0:
            reason = CANCEL_REASONS[int(rng.integers(len(CANCEL_REASONS)))]
            ev_rows.append((u, int(canceled_at[i]), "subscription_canceled", i, reason))
            status[i] = "canceled"

    subs = pd.DataFrame(
        {
            "subscription_id": sub_ids,
            "user_idx": uidx,
            "plan": plan,
            "price_usd": price.round(2),
            "currency": "USD",
            "_started_at": started_at,
            "_trial_started_at": trial_ts,
            "_canceled_at": canceled_at,
            "status": status.astype(str),
        }
    )
    inv = pd.DataFrame(
        inv_rows, columns=["sub_pos", "user_idx", "_charged_at", "amount_usd", "is_refund"]
    )
    inv = inv.sort_values(["_charged_at", "sub_pos", "is_refund"], kind="mergesort").reset_index(
        drop=True
    )
    inv["subscription_id"] = sub_ids[inv["sub_pos"].to_numpy()] if len(inv) else []
    inv.insert(0, "invoice_id", [f"inv{i:07d}" for i in range(1, len(inv) + 1)])
    inv["amount_usd"] = inv["amount_usd"].round(2)

    ev = pd.DataFrame(ev_rows, columns=["user_idx", "ts", "event_name", "sub_pos", "reason"])
    if len(ev):
        sp = ev["sub_pos"].to_numpy()
        props = np.empty(len(ev), dtype=object)
        name = ev["event_name"].to_numpy()
        for j in range(len(ev)):
            if name[j] == "subscription_started":
                props[j] = f'{{"plan": "{plan[sp[j]]}", "price_usd": {price[sp[j]]:.2f}}}'
            elif name[j] == "subscription_canceled":
                props[j] = f'{{"reason": "{ev["reason"].iat[j]}"}}'
            elif name[j] == "refund_issued":
                props[j] = f'{{"amount_usd": {price[sp[j]]:.2f}}}'
            else:
                props[j] = f'{{"plan": "{plan[sp[j]]}"}}'
        ev["properties"] = props
    else:
        ev["properties"] = []
    return subs, inv.drop(columns=["sub_pos"]), ev[["user_idx", "ts", "event_name", "properties"]]

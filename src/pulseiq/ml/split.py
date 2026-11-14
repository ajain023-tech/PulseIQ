"""Time-based train / validation / test split (never shuffles across time)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Split:
    """Index arrays into the (signup-ordered) feature frame."""

    train: pd.Index
    valid: pd.Index
    test: pd.Index
    boundaries: dict


def time_split(frame: pd.DataFrame, train: float = 0.70, valid: float = 0.15) -> Split:
    """Earliest ``train`` share -> train, next ``valid`` -> validation, rest -> test."""
    f = frame.sort_values(["signup_ts", "user_id"], kind="mergesort")
    n = len(f)
    a, b = int(n * train), int(n * (train + valid))
    idx = f.index
    tr, va, te = idx[:a], idx[a:b], idx[b:]
    ts = f["signup_ts"]
    bounds = {
        "train": [str(ts.iloc[0]), str(ts.iloc[a - 1])],
        "valid": [str(ts.iloc[a]), str(ts.iloc[b - 1])],
        "test": [str(ts.iloc[b]), str(ts.iloc[-1])],
    }
    return Split(tr, va, te, bounds)


def class_balance(frame: pd.DataFrame, split: Split, target: str) -> dict:
    """Rows and positive rate per split."""
    out = {}
    for name in ("train", "valid", "test"):
        y = frame.loc[getattr(split, name), target]
        out[name] = {
            "rows": int(len(y)),
            "positives": int(y.sum()),
            "positive_rate": float(y.mean()),
        }
    return out

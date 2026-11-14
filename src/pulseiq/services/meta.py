"""Data window, build metadata and health information."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, date, datetime

import pandas as pd

from pulseiq import __version__
from pulseiq.config import get_settings

from .db import cached, query


@cached
def data_window() -> tuple[date, date]:
    """(first date, last date) covered by the warehouse (inclusive)."""
    row = query(
        "select data_start, cast(data_end - interval 1 day as date) from int_data_window"
    ).iloc[0]
    return pd.Timestamp(row.iloc[0]).date(), pd.Timestamp(row.iloc[1]).date()


def build_info() -> dict:
    """Warehouse path/timestamp, model version and git SHA."""
    s = get_settings()
    path = s.warehouse_path
    built = (
        datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(timespec="seconds")
        if path.exists()
        else None
    )
    meta_path = s.artifacts_dir / "ml" / "model_meta.json"
    model = None
    if meta_path.exists():
        m = json.loads(meta_path.read_text())
        model = f"{m['model']} (trained {m['trained_at']}, sha {m['git_sha']})"
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=s.dbt_dir.parent,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        sha = "unknown"
    return {
        "version": __version__,
        "warehouse": str(path),
        "warehouse_built_at": built,
        "model_version": model,
        "git_sha": sha,
    }

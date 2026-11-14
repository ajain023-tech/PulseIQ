"""Load experiment exposures and metadata from the warehouse."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import duckdb
import pandas as pd


@dataclass
class ExperimentData:
    """Exposure rows (one per user) plus the experiment's design metadata."""

    experiment_id: str
    name: str
    hypothesis: str
    start_date: date
    end_date: date
    allocation: float
    primary_metric: str
    guardrail_metrics: list[str]
    secondary_metrics: list[str]
    df: pd.DataFrame
    data_end: pd.Timestamp


def list_experiments(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Experiment ids present in the warehouse."""
    return [
        r[0]
        for r in con.execute(
            "select experiment_id from stg_experiments order by start_date"
        ).fetchall()
    ]


def load_experiment(con: duckdb.DuckDBPyConnection, experiment_id: str) -> ExperimentData:
    """Return exposures for ``experiment_id``; raises ``KeyError`` if unknown."""
    meta = con.execute(
        "select name, hypothesis, start_date, end_date, allocation, primary_metric, "
        "guardrail_metrics, secondary_metrics from stg_experiments where experiment_id = ?",
        [experiment_id],
    ).fetchone()
    if meta is None:
        raise KeyError(experiment_id)
    df = con.execute(
        "select * from fct_experiment_exposures where experiment_id = ? order by user_id",
        [experiment_id],
    ).df()
    data_end = pd.Timestamp(con.execute("select data_end from int_data_window").fetchone()[0])
    return ExperimentData(
        experiment_id=experiment_id,
        name=meta[0],
        hypothesis=meta[1],
        start_date=meta[2],
        end_date=meta[3],
        allocation=float(meta[4]),
        primary_metric=meta[5],
        guardrail_metrics=[m for m in meta[6] if m],
        secondary_metrics=[m for m in meta[7] if m],
        df=df,
        data_end=data_end,
    )

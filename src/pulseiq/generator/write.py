"""Persist generated tables as parquet plus ``ground_truth.json``."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from . import GenerationResult


def write_result(result: GenerationResult, raw_dir: Path) -> dict[str, int]:
    """Write every table to ``raw_dir/<table>.parquet``; return row counts.

    Parquet files are written without pandas index metadata and with a fixed
    compression so identical inputs produce byte-identical files.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for name, frame in result.tables.items():
        table = pa.Table.from_pandas(frame, preserve_index=False)
        table = table.replace_schema_metadata(None)
        pq.write_table(
            table, raw_dir / f"{name}.parquet", compression="zstd", write_statistics=True
        )
        counts[name] = len(frame)
    truth = dict(result.ground_truth)
    truth["row_counts"] = counts
    (raw_dir / "ground_truth.json").write_text(json.dumps(truth, indent=2, default=str) + "\n")
    return counts

"""Shared fixtures: one small generated dataset + warehouse per test session."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pulseiq.generator import GenerationResult, generate


@pytest.fixture(scope="session")
def small_result() -> GenerationResult:
    """Small dataset generated in memory with the default seed."""
    return generate("small", seed=42)


@pytest.fixture(scope="session")
def small_env(tmp_path_factory, small_result) -> Path:
    """Write the small dataset to a temp dir, build the warehouse there, return data dir."""
    from pulseiq.config import get_settings
    from pulseiq.generator.write import write_result
    from pulseiq.warehouse import build_warehouse

    data_dir = tmp_path_factory.mktemp("pulseiq_data")
    old = {
        k: os.environ.get(k)
        for k in ("PULSEIQ_DATA_DIR", "PULSEIQ_WAREHOUSE", "PULSEIQ_ARTIFACTS_DIR")
    }
    os.environ["PULSEIQ_DATA_DIR"] = str(data_dir)
    os.environ["PULSEIQ_ARTIFACTS_DIR"] = str(data_dir / "artifacts")
    os.environ.pop("PULSEIQ_WAREHOUSE", None)
    settings = get_settings()
    write_result(small_result, settings.raw_dir)
    res = build_warehouse(settings)
    assert res.success, res.failures
    yield data_dir
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture(scope="session")
def small_con(small_env):
    """Read-only DuckDB connection to the small warehouse."""
    import duckdb

    con = duckdb.connect(str(small_env / "warehouse" / "pulseiq.duckdb"), read_only=True)
    yield con
    con.close()


@pytest.fixture(scope="session")
def full_env(tmp_path_factory) -> Path:
    """Full-size dataset + warehouse in a temp dir (slow tests only)."""
    from pulseiq.config import get_settings
    from pulseiq.generator.write import write_result
    from pulseiq.warehouse import build_warehouse

    data_dir = tmp_path_factory.mktemp("pulseiq_full")
    old = os.environ.get("PULSEIQ_DATA_DIR")
    os.environ["PULSEIQ_DATA_DIR"] = str(data_dir)
    settings = get_settings()
    write_result(generate("full", seed=42), settings.raw_dir)
    res = build_warehouse(settings)
    assert res.success, res.failures
    if old is None:
        os.environ.pop("PULSEIQ_DATA_DIR", None)
    else:
        os.environ["PULSEIQ_DATA_DIR"] = old
    return data_dir

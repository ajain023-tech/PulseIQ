"""Central configuration: seed, dataset sizes and filesystem paths.

Every value can be overridden with an environment variable so the same code runs
locally, in CI, in Docker and on Streamlit Cloud.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class SizeConfig:
    """How many users to simulate and over how many days."""

    name: str
    n_users: int
    n_days: int


SIZES: dict[str, SizeConfig] = {
    "full": SizeConfig("full", n_users=60_000, n_days=120),
    "small": SizeConfig("small", n_users=4_000, n_days=60),
}

START_DATE = date(2025, 1, 6)  # a Monday


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else default


@dataclass(frozen=True)
class Settings:
    """Resolved runtime settings (single source of truth for seed and paths)."""

    seed: int = field(default_factory=lambda: int(os.environ.get("PULSEIQ_SEED", "42")))
    size: str = field(default_factory=lambda: os.environ.get("PULSEIQ_SIZE", "full"))
    data_dir: Path = field(
        default_factory=lambda: _env_path("PULSEIQ_DATA_DIR", PROJECT_ROOT / "data")
    )
    artifacts_dir: Path = field(
        default_factory=lambda: _env_path("PULSEIQ_ARTIFACTS_DIR", PROJECT_ROOT / "artifacts")
    )

    @property
    def raw_dir(self) -> Path:
        """Directory holding generated raw parquet + ground truth."""
        return self.data_dir / "raw"

    @property
    def warehouse_path(self) -> Path:
        """DuckDB warehouse file built by dbt."""
        override = os.environ.get("PULSEIQ_WAREHOUSE")
        if override:
            return Path(override).expanduser().resolve()
        return self.data_dir / "warehouse" / "pulseiq.duckdb"

    @property
    def ground_truth_path(self) -> Path:
        """Validation-only ground-truth file written by the generator."""
        return self.raw_dir / "ground_truth.json"

    @property
    def legacy_csv(self) -> Path:
        """The v1 user-level experiment dataset kept for calibration."""
        return PROJECT_ROOT / "data" / "legacy" / "ab_test_dataset.csv"

    @property
    def dbt_dir(self) -> Path:
        """dbt project directory."""
        return PROJECT_ROOT / "warehouse"

    def size_config(self, size: str | None = None) -> SizeConfig:
        """Return the size configuration for ``size`` (default: settings size)."""
        key = size or self.size
        if key not in SIZES:
            raise ValueError(f"Unknown size {key!r}; expected one of {sorted(SIZES)}")
        return SIZES[key]


def get_settings() -> Settings:
    """Return fresh settings (re-reads environment variables)."""
    return Settings()

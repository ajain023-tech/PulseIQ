"""Build the DuckDB warehouse with dbt and inspect it."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import duckdb

from pulseiq.config import Settings, get_settings

MART_TABLES = (
    "dim_users",
    "fct_events",
    "fct_funnel_user",
    "agg_funnel_daily",
    "agg_funnel_by_segment",
    "agg_retention_cohorts",
    "fct_revenue_daily",
    "agg_kpis_daily",
    "fct_experiment_exposures",
)


@dataclass
class BuildResult:
    """Outcome of a dbt build."""

    success: bool
    seconds: float
    n_models: int
    n_tests: int
    failures: list[str]


def _dbt_env(settings: Settings) -> dict[str, str]:
    return {
        "PULSEIQ_WAREHOUSE": str(settings.warehouse_path),
        "PULSEIQ_RAW_DIR": str(settings.raw_dir),
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
    }


def build_warehouse(settings: Settings | None = None, select: str | None = None) -> BuildResult:
    """Run ``dbt build`` (models + tests) into the configured DuckDB file.

    dbt runs in a subprocess so it never holds a DuckDB handle in this process
    (DuckDB refuses mixed read-only / read-write handles to one file).
    """
    settings = settings or get_settings()
    if not (settings.raw_dir / "events.parquet").exists():
        raise FileNotFoundError(f"No raw data in {settings.raw_dir}; run `pulseiq generate` first.")
    settings.warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    target = settings.dbt_dir / "target"
    cmd = [
        sys.executable,
        "-c",
        "from dbt.cli.main import cli; cli()",
        "build",
        "--project-dir",
        str(settings.dbt_dir),
        "--profiles-dir",
        str(settings.dbt_dir),
        "--target-path",
        str(target),
        "--log-path",
        str(settings.dbt_dir / "logs"),
        "--quiet",
    ]
    if select:
        cmd += ["--select", select]
    env = {**os.environ, **_dbt_env(settings)}
    start = time.perf_counter()
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    seconds = time.perf_counter() - start
    failures: list[str] = []
    n_models = n_tests = 0
    results_path = target / "run_results.json"
    if results_path.exists():
        for r in json.loads(results_path.read_text()).get("results", []):
            uid = r["unique_id"]
            if uid.startswith("model."):
                n_models += 1
            elif uid.startswith("test."):
                n_tests += 1
            if r["status"] not in ("success", "pass"):
                failures.append(
                    f"{uid.split('.')[-1]}: {r['status']} {r.get('message') or ''}".strip()
                )
    if proc.returncode != 0 and not failures:
        failures.append(
            (proc.stdout + proc.stderr).strip()[-2000:] or f"dbt exited {proc.returncode}"
        )
    return BuildResult(proc.returncode == 0 and not failures, seconds, n_models, n_tests, failures)


def connect(path: Path | None = None, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """Open the warehouse (read-only by default)."""
    path = path or get_settings().warehouse_path
    if not Path(path).exists():
        raise FileNotFoundError(f"Warehouse not found at {path}; run `pulseiq build`.")
    return duckdb.connect(str(path), read_only=read_only)


def profile_warehouse(con: duckdb.DuckDBPyConnection) -> dict:
    """Row counts of every mart plus headline KPIs."""
    counts = {t: con.execute(f"select count(*) from {t}").fetchone()[0] for t in MART_TABLES}
    funnel = con.execute(
        "select count(*), avg(is_onboarded), avg(is_trial), avg(is_paid) from fct_funnel_user"
    ).fetchone()
    ret = dict(
        con.execute(
            "select day_n, sum(retained_users) / sum(eligible_users) from agg_retention_cohorts "
            "group by day_n order by day_n"
        ).fetchall()
    )
    rev = con.execute(
        "select sum(gross_revenue_usd), sum(refunds_usd), sum(net_revenue_usd) from fct_revenue_daily"
    ).fetchone()
    last = con.execute(
        "select dau, mau, stickiness, kpi_date from agg_kpis_daily order by kpi_date desc limit 1"
    ).fetchone()
    exposures = con.execute(
        "select experiment_id, variant, count(*) from fct_experiment_exposures group by 1, 2 order by 1, 2"
    ).fetchall()
    return {
        "row_counts": counts,
        "headline": {
            "users": funnel[0],
            "onboarding_rate": funnel[1],
            "trial_rate_ordered": funnel[2],
            "paid_rate_ordered": funnel[3],
            **{f"d{k}_retention": v for k, v in ret.items()},
            "gross_revenue_usd": rev[0],
            "refunds_usd": rev[1],
            "net_revenue_usd": rev[2],
            "last_day_dau": last[0],
            "last_day_mau": last[1],
            "last_day_stickiness": last[2],
            "last_day": str(last[3]),
        },
        "exposures": [{"experiment_id": e, "variant": v, "users": n} for e, v, n in exposures],
    }

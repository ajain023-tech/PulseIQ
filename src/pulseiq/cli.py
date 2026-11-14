"""``pulseiq`` command-line interface."""

from __future__ import annotations

import json
import time

import typer

from pulseiq.config import get_settings

app = typer.Typer(
    add_completion=False, help="PulseIQ - product analytics & experimentation platform."
)


@app.command()
def generate(
    small: bool = typer.Option(False, "--small", help="Small dataset (4,000 users / 60 days)."),
    seed: int = typer.Option(None, "--seed", help="Random seed (default PULSEIQ_SEED or 42)."),
) -> None:
    """Simulate raw events and write data/raw/*.parquet + ground_truth.json."""
    from pulseiq.generator import generate as run
    from pulseiq.generator.write import write_result

    settings = get_settings()
    size = "small" if small else settings.size
    seed = settings.seed if seed is None else seed
    start = time.perf_counter()
    result = run(size=size, seed=seed)
    counts = write_result(result, settings.raw_dir)
    typer.echo(
        f"Generated size={size} seed={seed} in {time.perf_counter() - start:.1f}s -> {settings.raw_dir}"
    )
    for name, n in counts.items():
        typer.echo(f"  {name:<24}{n:>12,}")


@app.command()
def build(select: str = typer.Option(None, help="Optional dbt --select expression.")) -> None:
    """Run dbt build (models + tests) into data/warehouse/pulseiq.duckdb."""
    from pulseiq.warehouse import build_warehouse

    res = build_warehouse(select=select)
    typer.echo(f"dbt build: {res.n_models} models, {res.n_tests} tests in {res.seconds:.1f}s")
    if not res.success:
        for f in res.failures:
            typer.echo(f"  FAIL {f}", err=True)
        raise typer.Exit(code=1)
    typer.echo("All models built and all tests passed.")


@app.command()
def profile() -> None:
    """Print mart row counts and headline KPIs."""
    from pulseiq.warehouse import connect, profile_warehouse

    with connect() as con:
        typer.echo(json.dumps(profile_warehouse(con), indent=2, default=str))


@app.command("compare-legacy")
def compare_legacy_cmd() -> None:
    """Compare generated headline rates with the v1 CSV (writes a markdown report)."""
    from pulseiq.generator.legacy_compare import compare_legacy

    frame, path = compare_legacy(get_settings())
    typer.echo(frame.to_string(index=False))
    typer.echo(f"Report: {path}")


def _later(phase: int) -> None:
    typer.echo(f"Implemented in Phase {phase}.")
    raise typer.Exit(code=2)


@app.command()
def analyze(experiment_id: str = typer.Argument(None)) -> None:  # noqa: ARG001
    """Analyse experiments (Phase 2)."""
    _later(2)


@app.command()
def train() -> None:
    """Train the retention model (Phase 2)."""
    _later(2)


@app.command()
def survival() -> None:
    """Survival analysis (Phase 2)."""
    _later(2)


@app.command()
def serve() -> None:
    """Run the API (Phase 3)."""
    _later(3)


if __name__ == "__main__":
    app()

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
def analyze(
    experiment_id: str = typer.Argument(None, help="Experiment id (omit with --all)."),
    all_: bool = typer.Option(False, "--all", help="Analyse every experiment."),
    sequential: bool = typer.Option(True, "--sequential/--no-sequential"),
    bayesian: bool = typer.Option(True, "--bayesian/--no-bayesian"),
    cuped: bool = typer.Option(True, "--cuped/--no-cuped"),
) -> None:
    """Analyse experiments -> artifacts/experiments/<id>/report.{json,md} + charts."""
    from pulseiq.experiments import analyze_experiment, save_report
    from pulseiq.experiments.data import list_experiments
    from pulseiq.warehouse import connect

    settings = get_settings()
    with connect() as con:
        ids = list_experiments(con) if all_ or experiment_id is None else [experiment_id]
        for exp_id in ids:
            rep = analyze_experiment(
                con, exp_id, sequential=sequential, bayesian=bayesian, cuped=cuped
            )
            out = save_report(rep, settings.artifacts_dir / "experiments" / exp_id)
            typer.echo(f"{exp_id:<22} {rep.decision:<13} -> {out}")
    if all_ or experiment_id is None:
        _peeking(settings)


def _peeking(settings) -> dict:
    from pulseiq.experiments.charts import peeking_plot
    from pulseiq.experiments.sequential import simulate_peeking

    sim = simulate_peeking()
    out = settings.artifacts_dir / "experiments"
    out.mkdir(parents=True, exist_ok=True)
    (out / "peeking_simulation.json").write_text(json.dumps(sim, indent=2))
    peeking_plot(sim, out / "peeking_simulation.png")
    typer.echo(
        f"Peeking A/A sim: fixed {sim['fpr_fixed_horizon']:.1%}, naive peeking "
        f"{sim['fpr_naive_peeking']:.1%}, sequential {sim['fpr_sequential']:.1%}"
    )
    return sim


@app.command()
def validate() -> None:
    """Compare experiment reports with ground truth -> artifacts/reports/experiment_validation.md."""
    from pulseiq.experiments import analyze_experiment
    from pulseiq.experiments.data import list_experiments
    from pulseiq.validation import load_ground_truth, write_experiment_validation
    from pulseiq.warehouse import connect

    settings = get_settings()
    with connect() as con:
        reports = {e: analyze_experiment(con, e) for e in list_experiments(con)}
    summary = write_experiment_validation(
        reports,
        load_ground_truth(settings),
        _peeking(settings),
        settings.artifacts_dir / "reports" / "experiment_validation.md",
    )
    typer.echo(json.dumps(summary, indent=2))
    ml_meta = settings.artifacts_dir / "ml" / "model_meta.json"
    if ml_meta.exists():
        from pulseiq.validation import write_ml_validation

        ml = write_ml_validation(
            json.loads(ml_meta.read_text()),
            load_ground_truth(settings),
            settings.artifacts_dir / "reports" / "ml_validation.md",
        )
        typer.echo(json.dumps(ml, indent=2))


@app.command()
def train() -> None:
    """Train + evaluate the D30 retention model -> artifacts/ml/."""
    from pulseiq.ml.pipeline import run_training
    from pulseiq.warehouse import connect

    settings = get_settings()
    with connect() as con:
        meta = run_training(con, settings.artifacts_dir / "ml")
    typer.echo(f"Best model: {meta['model']} {meta['params']}")
    for name, m in meta["metrics_test"].items():
        typer.echo(
            f"  {name:<24} PR-AUC {m['pr_auc']:.3f}  ROC-AUC {m['roc_auc']:.3f}  "
            f"recall {m['recall']:.3f}  F1 {m['f1']:.3f}  accuracy {m['accuracy']:.3f}"
        )
    typer.echo(f"Artifacts: {settings.artifacts_dir / 'ml'}")


@app.command()
def survival() -> None:
    """Kaplan-Meier, log-rank and Cox time-to-churn analysis -> artifacts/ml/."""
    from pulseiq.ml.pipeline import run_survival
    from pulseiq.warehouse import connect

    settings = get_settings()
    with connect() as con:
        res = run_survival(con, settings.artifacts_dir / "ml")
    typer.echo(f"{res['n_users']:,} users, {res['churn_events']:,} churn events")
    for km in res["km"]:
        typer.echo(f"  KM by {km['by']:<20} log-rank p = {km['logrank_p']:.3g}")
    for c in res["cox"]:
        if not c["feature"].startswith("_"):
            typer.echo(
                f"  Cox HR {c['feature']:<26} {c['hazard_ratio']:.3f} [{c['ci_low']:.3f}, {c['ci_high']:.3f}]"
            )


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address (0.0.0.0 in Docker)."),
    port: int = typer.Option(8000),
    reload: bool = typer.Option(False),
) -> None:
    """Run the FastAPI service (Swagger UI at /docs)."""
    import uvicorn

    uvicorn.run("pulseiq.api.app:app", host=host, port=port, reload=reload, log_level="info")


@app.command("ai-eval")
def ai_eval(
    provider: str = typer.Option("mock", help="mock | offline | gemini | anthropic | openai"),
) -> None:
    """Run the AI-analyst eval set -> artifacts/reports/ai_eval.{md,json}."""
    from pulseiq.ai.evals.run_evals import run

    summary = run(provider, get_settings().artifacts_dir / "reports")
    typer.echo(json.dumps(summary, indent=2))


@app.command()
def ask(question: str, provider: str = typer.Option(None)) -> None:
    """Ask the AI analyst a question from the terminal."""
    from pulseiq.ai.agent import ask as run_ask

    r = run_ask(question, provider=provider)
    typer.echo(f"[{r.provider}] {r.answer}")
    if r.sql:
        typer.echo(f"SQL: {r.sql}")
    for c in r.caveats:
        typer.echo(f"  - {c}")


if __name__ == "__main__":
    app()

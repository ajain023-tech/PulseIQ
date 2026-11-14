"""Build, render and persist an ``ExperimentReport``.

``ExperimentReport`` is a stable pydantic schema consumed by the API and dashboard.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from .bayesian import beta_binomial_readout
from .corrections import benjamini_hochberg, holm
from .cuped import cuped_readout
from .data import ExperimentData, load_experiment
from .decision import decide
from .frequentist import Readout, bootstrap_diff_ci, proportion_readout, welch_readout
from .metrics import (
    CUPED_COVARIATES,
    DEFAULT_TOLERANCE,
    DESIGNS,
    METRICS,
    SEGMENT_COLUMNS,
    SRM_ALPHA,
    SRM_SEGMENT_COLUMNS,
    Design,
)
from .power import days_to_run, mde, sample_size
from .segments import segment_effects
from .sequential import sequential_trace
from .srm import localise_srm, srm_by_segment, srm_test


class CupedSummary(BaseModel):
    """CUPED diagnostics for one metric."""

    covariate: str
    theta: float
    correlation: float
    variance_reduction: float
    ci_width_raw: float
    ci_width_cuped: float
    ci_width_reduction: float
    abs_diff: float
    ci_low: float
    ci_high: float
    p_value: float


class MetricResult(BaseModel):
    """Readout for one metric (treatment minus control)."""

    metric: str
    label: str
    role: str = Field(description="primary | guardrail | secondary")
    kind: str
    higher_is_better: bool
    n_control: int
    n_treatment: int
    value_control: float
    value_treatment: float
    abs_diff: float
    ci_low: float
    ci_high: float
    rel_lift: float | None = None
    rel_ci_low: float | None = None
    rel_ci_high: float | None = None
    p_value: float
    method: str
    cuped: CupedSummary | None = None
    cuped_used: bool = False
    decision_diff: float
    decision_ci: list[float]
    decision_p: float
    p_adjusted: float
    adjustment: str
    significant: bool
    improved: bool
    tolerance: float | None = None
    bootstrap_ci: list[float] | None = None
    bayesian: dict | None = None


class SRMResult(BaseModel):
    """Sample-ratio-mismatch check."""

    n_control: int
    n_treatment: int
    allocation: float
    treatment_share: float
    chi2: float
    p_value: float
    flagged: bool
    alpha: float = SRM_ALPHA
    segments: list[dict]
    flagged_segments: list[dict]
    likely_causes: list[dict] = Field(
        default_factory=list, description="flagged segments whose exclusion removes the SRM"
    )


class PowerSummary(BaseModel):
    """Design power and run-length estimates."""

    baseline: float
    mde_abs: float
    required_n_per_arm: int | None
    n_per_arm: int
    mde_at_current_n: float | None
    daily_users_per_arm: float | None
    days_left: float | None
    guardrail_days_left: float | None = None


class ExperimentReport(BaseModel):
    """Full analysis of one experiment."""

    experiment_id: str
    name: str
    hypothesis: str
    start_date: str
    end_date: str
    data_end: str
    primary_metric: str
    guardrail_metrics: list[str]
    secondary_metrics: list[str]
    n_control: int
    n_treatment: int
    srm: SRMResult
    metrics: list[MetricResult]
    cuped_status: str
    power: PowerSummary
    sequential: dict | None = None
    segments: list[dict] = []
    decision: str
    reasons: list[str]
    charts: dict[str, str] = {}
    skipped_metrics: list[str] = Field(
        default_factory=list, description="metrics with too few eligible users in an arm to analyse"
    )
    generated_at: str

    def metric(self, name: str) -> MetricResult:
        """Return the result for ``name``."""
        for m in self.metrics:
            if m.metric == name:
                return m
        raise KeyError(name)


# ---------------------------------------------------------------------------
def _arm_arrays(df: pd.DataFrame, elig: str | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = df if elig is None else df[df[elig] == 1]
    return d[d["variant"] == "control"], d[d["variant"] == "treatment"]


def _metric_readout(
    data: ExperimentData, name: str, role: str, use_cuped: bool, design: Design, seed: int
) -> MetricResult:
    spec = METRICS[name]
    c, t = _arm_arrays(data.df, spec.eligibility)
    yc, yt = c[spec.column].to_numpy(dtype=float), t[spec.column].to_numpy(dtype=float)
    if spec.kind == "proportion":
        raw: Readout = proportion_readout(int(yc.sum()), len(yc), int(yt.sum()), len(yt))
    else:
        raw = welch_readout(yc, yt)
    cuped = None
    dec_diff, dec_ci, dec_p = raw.abs_diff, [raw.ci_low, raw.ci_high], raw.p_value
    if use_cuped:
        cov = CUPED_COVARIATES[0]
        cr = cuped_readout(yc, c[cov].to_numpy(float), yt, t[cov].to_numpy(float), cov, raw)
        cuped = CupedSummary(
            covariate=cov,
            theta=cr.theta,
            correlation=cr.correlation,
            variance_reduction=cr.variance_reduction,
            ci_width_raw=cr.ci_width_raw,
            ci_width_cuped=cr.ci_width_cuped,
            ci_width_reduction=cr.ci_width_reduction,
            abs_diff=cr.readout.abs_diff,
            ci_low=cr.readout.ci_low,
            ci_high=cr.readout.ci_high,
            p_value=cr.readout.p_value,
        )
        dec_diff, dec_ci, dec_p = cuped.abs_diff, [cuped.ci_low, cuped.ci_high], cuped.p_value
    boot = None
    if spec.heavy_tailed:
        boot = list(bootstrap_diff_ci(yc, yt, seed=seed))
    bayes = None
    if spec.kind == "proportion":
        bayes = beta_binomial_readout(int(yc.sum()), len(yc), int(yt.sum()), len(yt), seed=seed)
    tol = None
    if role == "guardrail":
        tol = (design.tolerances or {}).get(name, DEFAULT_TOLERANCE)
    improved = (dec_diff > 0) == spec.higher_is_better
    return MetricResult(
        metric=name,
        label=spec.label or name,
        role=role,
        kind=spec.kind,
        higher_is_better=spec.higher_is_better,
        n_control=raw.n_control,
        n_treatment=raw.n_treatment,
        value_control=raw.value_control,
        value_treatment=raw.value_treatment,
        abs_diff=raw.abs_diff,
        ci_low=raw.ci_low,
        ci_high=raw.ci_high,
        rel_lift=raw.rel_lift,
        rel_ci_low=raw.rel_ci_low,
        rel_ci_high=raw.rel_ci_high,
        p_value=raw.p_value,
        method=raw.method,
        cuped=cuped,
        cuped_used=cuped is not None,
        decision_diff=dec_diff,
        decision_ci=dec_ci,
        decision_p=dec_p,
        p_adjusted=dec_p,
        adjustment="none",
        significant=False,
        improved=improved,
        tolerance=tol,
        bootstrap_ci=boot,
        bayesian=bayes,
    )


def _sequential(data: ExperimentData, metric: str, tau: float) -> dict | None:
    spec = METRICS[metric]
    if spec.kind != "proportion":
        return None
    d = data.df if spec.eligibility is None else data.df[data.df[spec.eligibility] == 1]
    d = d.assign(look=pd.to_datetime(d["assigned_at"]).dt.floor("D"))
    g = d.groupby(["look", "variant"])[spec.column].agg(["sum", "count"]).unstack(fill_value=0)
    if len(g) < 2:
        return {
            "applicable": False,
            "reason": "All users were assigned on a single day; no interim looks exist.",
        }
    cum = g.cumsum()
    trace = sequential_trace(
        cum[("sum", "control")].to_numpy(float),
        cum[("count", "control")].to_numpy(float),
        cum[("sum", "treatment")].to_numpy(float),
        cum[("count", "treatment")].to_numpy(float),
        tau2=tau**2,
    )
    trace["looks"] = [str(x.date()) for x in g.index]
    trace["applicable"] = True
    trace["metric"] = metric
    trace["note"] = (
        "Retrospective daily looks by assignment date (users assigned up to each day, with their final outcomes)."
    )
    return trace


def analyze_experiment(
    con: duckdb.DuckDBPyConnection,
    experiment_id: str,
    sequential: bool = True,
    bayesian: bool = True,
    cuped: bool = True,
    seed: int = 42,
) -> ExperimentReport:
    """Run the full analysis for one experiment."""
    data = load_experiment(con, experiment_id)
    design = DESIGNS.get(experiment_id, Design())
    df = data.df
    nc = int((df["variant"] == "control").sum())
    nt = int((df["variant"] == "treatment").sum())

    # SRM
    chi2, p = srm_test(nc, nt, data.allocation)
    seg_rows = [r for col in SRM_SEGMENT_COLUMNS for r in srm_by_segment(df, col, data.allocation)]
    flagged_segs = [r for r in seg_rows if r["flagged"]]
    srm = SRMResult(
        n_control=nc,
        n_treatment=nt,
        allocation=data.allocation,
        treatment_share=nt / max(nc + nt, 1),
        chi2=chi2,
        p_value=p,
        flagged=p < SRM_ALPHA,
        segments=seg_rows,
        flagged_segments=flagged_segs,
        likely_causes=localise_srm(df, flagged_segs, data.allocation) if p < SRM_ALPHA else [],
    )

    # CUPED applicability
    new_user = bool(df["assigned_at_signup"].all())
    cov = CUPED_COVARIATES[0]
    if not cuped:
        use_cuped, cuped_status = False, "disabled by option"
    elif new_user or df[cov].var() == 0:
        use_cuped = False
        cuped_status = (
            "skipped: users were randomised at signup, so there is no pre-period covariate"
        )
    else:
        use_cuped, cuped_status = (
            True,
            f"applied with covariate {cov} (sessions in 14 days before assignment)",
        )

    roles = (
        [(data.primary_metric, "primary")]
        + [(m, "guardrail") for m in data.guardrail_metrics]
        + [(m, "secondary") for m in data.secondary_metrics]
    )
    results, skipped = [], []
    for m, role in roles:
        c, t = _arm_arrays(data.df, METRICS[m].eligibility)
        if role != "primary" and (len(c) < 2 or len(t) < 2):
            skipped.append(m)
            continue
        results.append(_metric_readout(data, m, role, use_cuped, design, seed))
    if not bayesian:
        for r in results:
            r.bayesian = None

    confirm = [r for r in results if r.role in ("primary", "guardrail")]
    for r, a in zip(confirm, holm([r.decision_p for r in confirm]), strict=True):
        r.p_adjusted, r.adjustment, r.significant = a, "holm", a < design.alpha
    explore = [r for r in results if r.role == "secondary"]
    for r, a in zip(explore, benjamini_hochberg([r.decision_p for r in explore]), strict=True):
        r.p_adjusted, r.adjustment, r.significant = a, "bh", a < design.alpha

    primary = results[0]
    baseline = primary.value_control if primary.kind == "proportion" else float("nan")
    mde_abs = design.mde_abs or (design.mde_rel or 0.1) * baseline
    req = sample_size(baseline, mde_abs) if primary.kind == "proportion" else None
    n_arm = min(primary.n_control, primary.n_treatment)
    days = pd.to_datetime(df["assigned_at"]).dt.floor("D").nunique()
    daily = (len(df) / 2 / days) if new_user and days > 1 else None
    days_left = days_to_run(req, daily, n_arm) if (req and daily) else None
    g_days = None
    for g in [r for r in results if r.role == "guardrail" and r.kind == "proportion"]:
        harm = -g.decision_diff if g.higher_is_better else g.decision_diff
        if g.tolerance is not None and harm < g.tolerance and daily:
            p0 = g.value_control
            se_needed = (g.tolerance - max(harm, 0)) / 1.96
            n_needed = int(np.ceil(2 * p0 * (1 - p0) / se_needed**2))
            g_days = max(
                g_days or 0.0, days_to_run(n_needed, daily, min(g.n_control, g.n_treatment))
            )
    power = PowerSummary(
        baseline=baseline,
        mde_abs=mde_abs,
        required_n_per_arm=req,
        n_per_arm=n_arm,
        mde_at_current_n=mde(n_arm, baseline) if primary.kind == "proportion" else None,
        daily_users_per_arm=daily,
        days_left=days_left,
        guardrail_days_left=g_days,
    )

    seq = _sequential(data, data.primary_metric, tau=mde_abs) if sequential else None
    segs = segment_effects(df, METRICS[data.primary_metric], SEGMENT_COLUMNS, mde_abs)

    decision, reasons = decide(
        srm.model_dump(),
        primary.model_dump(),
        [r.model_dump() for r in results if r.role == "guardrail"],
        power.model_dump(),
    )
    return ExperimentReport(
        experiment_id=experiment_id,
        name=data.name,
        hypothesis=data.hypothesis,
        start_date=str(data.start_date),
        end_date=str(data.end_date),
        data_end=str(data.data_end),
        primary_metric=data.primary_metric,
        guardrail_metrics=data.guardrail_metrics,
        secondary_metrics=data.secondary_metrics,
        n_control=nc,
        n_treatment=nt,
        srm=srm,
        metrics=results,
        cuped_status=cuped_status,
        power=power,
        sequential=seq,
        segments=segs,
        decision=decision,
        reasons=reasons,
        skipped_metrics=skipped,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


# ---------------------------------------------------------------------------
def _fmt(v: float | None, pct: bool = True) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    return f"{v:+.2%}" if pct else f"{v:+.4f}"


def render_markdown(r: ExperimentReport) -> str:
    """Human-readable report."""
    lines = [
        f"# {r.name} (`{r.experiment_id}`)",
        "",
        f"**Decision: {r.decision}**",
        "",
        *[f"- {x}" for x in r.reasons],
        "",
        f"Hypothesis: {r.hypothesis}  ",
        f"Window: {r.start_date} → {r.end_date} (data until {r.data_end}). "
        f"Control n = {r.n_control:,}, treatment n = {r.n_treatment:,}.",
        "",
        "## Sample ratio mismatch",
        f"Treatment share {r.srm.treatment_share:.2%} vs intended {r.srm.allocation:.0%}; "
        f"χ² = {r.srm.chi2:.2f}, p = {r.srm.p_value:.3g} → {'**SRM DETECTED**' if r.srm.flagged else 'no SRM'}.",
    ]
    if r.srm.likely_causes:
        lines.append(
            "Likely cause (excluding it removes the SRM): "
            + ", ".join(
                f"**{s['segment_type']}={s['segment_value']}**" for s in r.srm.likely_causes
            )
        )
    if r.srm.flagged_segments:
        lines.append(
            "Flagged segments: "
            + ", ".join(
                f"{s['segment_type']}={s['segment_value']} (p = {s['p_value']:.2g}, treatment share {s['treatment_share']:.1%})"
                for s in r.srm.flagged_segments
            )
        )
    lines += [
        "",
        f"## Metrics (CUPED: {r.cuped_status})",
        "",
        "| Metric | Role | Control | Treatment | Diff (raw) | 95 % CI (raw) | Diff (decision) | 95 % CI (decision) | p | adj. p | Sig. |",
        "|---|---|---:|---:|---:|---|---:|---|---:|---:|:-:|",
    ]
    for m in r.metrics:
        pct = m.kind == "proportion"
        val = (lambda v: f"{v:.2%}") if pct else (lambda v: f"{v:.3f}")
        lines.append(
            f"| {m.label} | {m.role} | {val(m.value_control)} | {val(m.value_treatment)} | "
            f"{_fmt(m.abs_diff, pct)} | [{_fmt(m.ci_low, pct)}, {_fmt(m.ci_high, pct)}] | "
            f"{_fmt(m.decision_diff, pct)} | [{_fmt(m.decision_ci[0], pct)}, {_fmt(m.decision_ci[1], pct)}] | "
            f"{m.decision_p:.3g} | {m.p_adjusted:.3g} ({m.adjustment}) | {'✔' if m.significant else ''} |"
        )
    cup = [m for m in r.metrics if m.cuped]
    if cup:
        lines += [
            "",
            "### CUPED variance reduction",
            "",
            "| Metric | θ | corr(Y, X) | Variance reduction | CI width raw → CUPED |",
            "|---|---:|---:|---:|---|",
        ]
        for m in cup:
            c = m.cuped
            lines.append(
                f"| {m.label} | {c.theta:.4f} | {c.correlation:.3f} | {c.variance_reduction:.1%} | "
                f"{c.ci_width_raw:.4f} → {c.ci_width_cuped:.4f} (−{c.ci_width_reduction:.1%}) |"
            )
    bay = [m for m in r.metrics if m.bayesian and m.role in ("primary", "guardrail")]
    if bay:
        lines += [
            "",
            "## Bayesian readout (Beta(1,1) priors)",
            "",
            "| Metric | P(T > C) | Expected loss if ship T | 95 % credible interval (abs) |",
            "|---|---:|---:|---|",
        ]
        for m in bay:
            b = m.bayesian
            lines.append(
                f"| {m.label} | {b['prob_treatment_better']:.3f} | {b['expected_loss_ship_treatment']:.5f} | "
                f"[{b['abs_lift_ci'][0]:+.4f}, {b['abs_lift_ci'][1]:+.4f}] |"
            )
    p = r.power
    lines += [
        "",
        "## Power",
        f"Baseline {p.baseline:.2%}, pre-registered MDE {p.mde_abs:.4f} (abs). Required n per arm: "
        f"{p.required_n_per_arm:,}; current n per arm: {p.n_per_arm:,}; MDE at current n: {p.mde_at_current_n:.4f}."
        if p.required_n_per_arm
        else "Power not computed for mean primary metrics.",
    ]
    if r.sequential and r.sequential.get("applicable"):
        s = r.sequential
        lines += [
            "",
            "## Sequential monitoring (mSPRT)",
            f"τ = {np.sqrt(s['tau2']):.4f}; final always-valid p = {s['always_valid_p'][-1]:.3g}; "
            f"boundary first crossed at look {s['first_crossing_look']} "
            f"({s['looks'][s['first_crossing_look']] if s['first_crossing_look'] is not None else 'never'}).",
        ]
    elif r.sequential:
        lines += ["", "## Sequential monitoring", r.sequential.get("reason", "")]
    if r.segments:
        lines += [
            "",
            "## Segments (exploratory, BH-corrected)",
            "",
            "| Segment | n C / T | Diff | 95 % CI | BH p | Note |",
            "|---|---|---:|---|---:|---|",
        ]
        for s in r.segments:
            lines.append(
                f"| {s['segment_type']}={s['segment_value']} | {s['n_control']:,} / {s['n_treatment']:,} | "
                f"{s['abs_diff']:+.4f} | [{s['ci_low']:+.4f}, {s['ci_high']:+.4f}] | {s['p_adjusted_bh']:.3g} | "
                f"{'underpowered' if s['underpowered'] else ''} |"
            )
    if r.charts:
        lines += ["", "## Charts", *[f"![{k}]({Path(v).name})" for k, v in r.charts.items()]]
    if r.skipped_metrics:
        lines += ["", "Skipped (no eligible users yet in an arm): " + ", ".join(r.skipped_metrics)]
    lines += ["", f"_Generated {r.generated_at}._", ""]
    return "\n".join(lines)


def save_report(report: ExperimentReport, out_dir: Path, charts: bool = True) -> Path:
    """Write report.json, report.md and charts into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if charts:
        from .charts import render_charts

        report.charts = render_charts(report, out_dir)
    (out_dir / "report.json").write_text(report.model_dump_json(indent=2))
    (out_dir / "report.md").write_text(render_markdown(report))
    return out_dir


def load_report(path: Path) -> ExperimentReport:
    """Load a saved report.json."""
    return ExperimentReport.model_validate(json.loads(Path(path).read_text()))

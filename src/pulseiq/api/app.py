"""PulseIQ REST API (FastAPI). Thin layer over ``pulseiq.services``."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from pulseiq import __version__
from pulseiq.ai.agent import AnalystResponse, ask
from pulseiq.experiments import ExperimentReport
from pulseiq.experiments.power import days_to_run, mde, sample_size
from pulseiq.services import experiments as exp_svc
from pulseiq.services import funnel as funnel_svc
from pulseiq.services import kpis as kpi_svc
from pulseiq.services import predictions as pred_svc
from pulseiq.services import retention as ret_svc
from pulseiq.services import revenue as rev_svc
from pulseiq.services.filters import Filters
from pulseiq.services.meta import build_info

log = logging.getLogger("pulseiq.api")

app = FastAPI(
    title="PulseIQ API",
    version=__version__,
    description=(
        "Product analytics & experimentation platform: KPIs, funnel, retention cohorts, revenue, "
        "validated experiment readouts, retention predictions and an AI analyst with guarded SQL. "
        "All data is synthetic (see /docs of the repo)."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def timing(request: Request, call_next):
    """Log method, path, status and latency; expose X-Response-Time-ms."""
    start = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    response.headers["X-Response-Time-ms"] = f"{ms:.1f}"
    log.info("%s %s -> %s in %.1f ms", request.method, request.url.path, response.status_code, ms)
    return response


def filters(
    start: date | None = Query(None, description="First day (inclusive). Default: last 28 days."),
    end: date | None = Query(None, description="Last day (inclusive)."),
    platform: Literal["ios", "android", "web"] | None = None,
    channel: Literal["organic", "paid_social", "search", "referral", "influencer"] | None = None,
    country_tier: Literal["high", "mid", "low"] | None = None,
) -> Filters:
    """Shared filter query parameters."""
    try:
        return Filters(start, end, platform, channel, country_tier)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


# ---- response models --------------------------------------------------------------
class Health(BaseModel):
    """Service health."""

    status: str
    version: str
    warehouse: str
    warehouse_built_at: str | None
    model_version: str | None
    git_sha: str


class Series(BaseModel):
    """Generic tabular response."""

    start: str
    end: str
    rows: list[dict]


class CohortResponse(BaseModel):
    """Cohort x day-N matrix (retention_rate null = immature)."""

    start: str
    end: str
    cells: list[dict]


class ExperimentSummary(BaseModel):
    """One row of the experiment list."""

    experiment_id: str
    name: str
    start_date: str
    end_date: str
    primary_metric: str
    primary_lift_abs: float
    primary_ci: list[float]
    srm_flagged: bool
    decision: str
    n_control: int
    n_treatment: int


class AnalyzeOptions(BaseModel):
    """Options for re-running an analysis."""

    sequential: bool = True
    bayesian: bool = True
    cuped: bool = True


class PowerRequest(BaseModel):
    """Sample-size / MDE calculator input."""

    baseline: float = Field(..., gt=0, lt=1, description="Control conversion rate, e.g. 0.20")
    mde: float | None = Field(
        None, gt=0, lt=1, description="Absolute minimum detectable effect, e.g. 0.02"
    )
    n_per_arm: int | None = Field(
        None, gt=10, description="Users per arm (to compute the MDE instead)"
    )
    alpha: float = Field(0.05, gt=0, lt=0.5)
    power: float = Field(0.8, gt=0.5, lt=1)
    daily_users_per_arm: float | None = Field(None, gt=0)


class PowerResponse(BaseModel):
    """Calculator output."""

    baseline: float
    mde: float
    n_per_arm: int
    total_users: int
    days_to_run: float | None


class Prediction(BaseModel):
    """Retention prediction for one user."""

    user_id: str
    signup_ts: str
    p_retained_d30: float
    risk_band: Literal["high", "medium", "low"]
    threshold: float
    risk_cut: float
    top_contributions: list[dict]
    model: str


class AskRequest(BaseModel):
    """Question for the AI analyst."""

    question: str = Field(..., min_length=3, max_length=1000)
    provider: Literal["gemini", "anthropic", "openai", "mock", "offline"] | None = None


# ---- endpoints ---------------------------------------------------------------------
@app.get("/api/v1/health", response_model=Health, tags=["meta"])
def health() -> Health:
    """Status, warehouse path and build time, model version and git SHA."""
    info = build_info()
    return Health(
        status="ok" if info["warehouse_built_at"] else "no-warehouse",
        warehouse=info["warehouse"],
        warehouse_built_at=info["warehouse_built_at"],
        model_version=info["model_version"],
        git_sha=info["git_sha"],
        version=info["version"],
    )


@app.get("/api/v1/kpis", response_model=kpi_svc.KPISummary, tags=["product"])
def kpis(f: Filters = Depends(filters)) -> kpi_svc.KPISummary:
    """DAU, MAU, stickiness, new users, conversions and net revenue with period-over-period deltas."""
    return kpi_svc.kpi_summary(f)


@app.get("/api/v1/funnel", response_model=funnel_svc.Funnel, tags=["product"])
def funnel(
    f: Filters = Depends(filters),
    by: Literal["channel", "platform", "country_tier", "device_tier"] | None = None,
) -> funnel_svc.Funnel:
    """Ordered signup-cohort funnel with step conversion and the biggest drop; optional segment split."""
    return funnel_svc.funnel(f, by)


@app.get("/api/v1/retention/cohorts", response_model=CohortResponse, tags=["product"])
def retention_cohorts(f: Filters = Depends(filters)) -> CohortResponse:
    """Weekly signup cohort x day-N (1, 3, 7, 14, 30) retention, eligibility-aware."""
    f2 = kpi_svc._resolve(f)
    return CohortResponse(
        start=str(f2.start), end=str(f2.end), cells=rev_svc.as_records(ret_svc.cohort_matrix(f))
    )


@app.get("/api/v1/revenue/daily", response_model=Series, tags=["product"])
def revenue_daily(f: Filters = Depends(filters)) -> Series:
    """Gross, refunds, net revenue, MRR, active subscriptions and ARPPU per day."""
    f2 = kpi_svc._resolve(f)
    return Series(
        start=str(f2.start), end=str(f2.end), rows=rev_svc.as_records(rev_svc.revenue_daily(f))
    )


@app.get("/api/v1/experiments", response_model=list[ExperimentSummary], tags=["experiments"])
def experiments() -> list[ExperimentSummary]:
    """All experiments with their decision."""
    return [ExperimentSummary(**r) for r in exp_svc.list_experiments()]


@app.get(
    "/api/v1/experiments/{experiment_id}", response_model=ExperimentReport, tags=["experiments"]
)
def experiment(experiment_id: str) -> ExperimentReport:
    """Full validated readout (SRM, CUPED, corrections, sequential, Bayesian, segments, decision)."""
    try:
        return exp_svc.get_report(experiment_id)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Unknown experiment '{experiment_id}'"
        ) from None


@app.post(
    "/api/v1/experiments/{experiment_id}/analyze",
    response_model=ExperimentReport,
    tags=["experiments"],
)
def analyze(experiment_id: str, options: AnalyzeOptions | None = None) -> ExperimentReport:
    """Re-run the analysis with options (e.g. without CUPED to compare CI widths)."""
    o = options or AnalyzeOptions()
    try:
        return exp_svc.run_analysis(experiment_id, o.sequential, o.bayesian, o.cuped)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Unknown experiment '{experiment_id}'"
        ) from None


@app.post("/api/v1/power", response_model=PowerResponse, tags=["experiments"])
def power(req: PowerRequest) -> PowerResponse:
    """Sample size per arm for an MDE, or the MDE for a given sample size."""
    if (req.mde is None) == (req.n_per_arm is None):
        raise HTTPException(status_code=422, detail="Provide exactly one of 'mde' or 'n_per_arm'.")
    try:
        if req.mde is not None:
            n = sample_size(req.baseline, req.mde, req.alpha, req.power)
            effect = req.mde
        else:
            n = req.n_per_arm
            effect = mde(n, req.baseline, req.alpha, req.power)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    days = days_to_run(n, req.daily_users_per_arm) if req.daily_users_per_arm else None
    return PowerResponse(
        baseline=req.baseline, mde=effect, n_per_arm=n, total_users=2 * n, days_to_run=days
    )


@app.get("/api/v1/predictions/users/{user_id}", response_model=Prediction, tags=["predictions"])
def predict(user_id: str) -> Prediction:
    """P(D30 retained), risk band and the features that moved this user's score most."""
    try:
        res = pred_svc.score_user(user_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    if res is None:
        raise HTTPException(status_code=404, detail=f"Unknown user '{user_id}'")
    return Prediction(**res)


@app.get("/api/v1/predictions/at-risk", response_model=list[dict], tags=["predictions"])
def at_risk(limit: int = Query(100, ge=1, le=1000)) -> list[dict]:
    """Highest-risk signups from the last 14 days (lowest P(retained))."""
    try:
        return rev_svc.as_records(pred_svc.at_risk(limit))
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.post("/api/v1/ask", response_model=AnalystResponse, tags=["ai"])
def ask_endpoint(req: AskRequest) -> AnalystResponse:
    """AI analyst: plain-English question -> guarded SQL -> grounded answer (offline mode without a key)."""
    return ask(req.question, provider=req.provider)

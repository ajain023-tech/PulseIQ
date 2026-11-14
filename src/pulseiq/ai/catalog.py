"""Compact schema + metric dictionary for the AI analyst, built from dbt schema.yml."""

from __future__ import annotations

from functools import lru_cache

import yaml

from pulseiq.config import get_settings

ALLOWED_TABLES = (
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

METRIC_DEFINITIONS = {
    "DN retention": "share of dN-eligible users with a session in the day-N block after signup "
    "(agg_retention_cohorts: sum(retained_users)/sum(eligible_users); or fct_experiment_exposures dN_retained where dN_eligible=1)",
    "onboarding rate": "avg(is_onboarded) in fct_funnel_user",
    "trial rate": "sum(is_trial)/sum(is_onboarded) (onboarded -> trial) or avg(is_trial) (of signups)",
    "paid conversion": "sum(is_paid)/sum(is_trial) (trial -> paid) or avg(is_paid) (of signups)",
    "net revenue": "sum(net_revenue_usd) in fct_revenue_daily = gross - refunds",
    "MRR": "mrr_usd in fct_revenue_daily (monthly-equivalent value of active paid periods)",
    "ARPPU": "arppu_monthly_usd = MRR / active subscriptions",
    "stickiness": "dau / mau in agg_kpis_daily",
    "refund rate": "sum(refunds_usd) / sum(gross_revenue_usd)",
}


@lru_cache(maxsize=1)
def catalog() -> dict[str, dict]:
    """{table: {"description": str, "columns": {name: description}}} for allowed marts."""
    path = get_settings().dbt_dir / "models" / "marts" / "_marts.yml"
    spec = yaml.safe_load(path.read_text())
    out = {}
    for m in spec["models"]:
        if m["name"] in ALLOWED_TABLES:
            out[m["name"]] = {
                "description": " ".join(m.get("description", "").split()),
                "columns": {c["name"]: c.get("description", "") for c in m.get("columns", [])},
            }
    return out


def allowed_columns() -> set[str]:
    """Every column name across the allowed marts."""
    return {c for t in catalog().values() for c in t["columns"]}


def catalog_text() -> str:
    """Compact text rendering for prompts."""
    lines = []
    for name, t in catalog().items():
        lines.append(f"TABLE {name}: {t['description']}")
        lines.append(
            "  columns: " + ", ".join(f"{c} ({d})" if d else c for c, d in t["columns"].items())
        )
    lines.append("METRIC DEFINITIONS:")
    lines += [f"  {k}: {v}" for k, v in METRIC_DEFINITIONS.items()]
    return "\n".join(lines)

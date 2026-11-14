"""Revenue, MRR, ARPPU, refunds, plan mix and revenue by country tier."""

from __future__ import annotations

import pandas as pd

from .db import cached, query
from .filters import Filters
from .kpis import _resolve


@cached
def revenue_daily(f: Filters | None = None) -> pd.DataFrame:
    """Daily gross, refunds, net revenue, MRR, active subscriptions and ARPPU."""
    f = _resolve(f)
    uc, up = f.user_clause("u")
    return query(
        f"""with days as (select cast(d as date) as day from range(cast(? as timestamp), cast(? as timestamp) + interval 1 day, interval 1 day) t(d)),
            cash as (select i.charged_date as day, sum(i.gross_usd) as gross, sum(i.refund_usd) as refunds
                     from stg_invoices i join dim_users u using (user_id) where {uc} group by 1),
            mrr as (select days.day, sum(p.monthly_value_usd) as mrr, count(distinct p.subscription_id) as active_subs
                    from days join int_subscription_periods p
                      on p.period_start < cast(days.day as timestamp) + interval 1 day
                     and p.period_end > cast(days.day as timestamp) + interval 1 day
                    join dim_users u on u.user_id = p.user_id where {uc} group by 1)
            select days.day, coalesce(cash.gross, 0) as gross_usd, coalesce(cash.refunds, 0) as refunds_usd,
                   coalesce(cash.gross, 0) - coalesce(cash.refunds, 0) as net_usd,
                   coalesce(mrr.mrr, 0) as mrr_usd, coalesce(mrr.active_subs, 0) as active_subscriptions,
                   mrr.mrr / nullif(mrr.active_subs, 0) as arppu_usd
            from days left join cash using (day) left join mrr using (day) order by day""",
        [f.start, f.end, *up, *up],
    )


@cached
def revenue_breakdown(f: Filters | None = None) -> dict:
    """Plan mix of paid starts, revenue by country tier and refund rate for the period."""
    f = _resolve(f)
    uc, up = f.user_clause("u")
    plan = query(
        f"""select s.plan, count(*) as subscriptions, sum(s.price_usd) as list_value_usd
            from stg_subscriptions s join dim_users u using (user_id)
            where {uc} and cast(s.started_at as date) between ? and ? group by 1 order by 1""",
        [*up, f.start, f.end],
    )
    tier = query(
        f"""select u.country_tier, sum(i.amount_usd) as net_usd, count(distinct i.user_id) as payers,
                   sum(i.amount_usd) / nullif(count(distinct i.user_id), 0) as net_per_payer_usd
            from stg_invoices i join dim_users u using (user_id)
            where {uc} and i.charged_date between ? and ? group by 1 order by 1""",
        [*up, f.start, f.end],
    )
    totals = query(
        f"""select sum(i.gross_usd) as gross, sum(i.refund_usd) as refunds
            from stg_invoices i join dim_users u using (user_id) where {uc} and i.charged_date between ? and ?""",
        [*up, f.start, f.end],
    ).iloc[0]
    gross = float(totals["gross"] or 0)
    return {
        "plan_mix": plan.to_dict(orient="records"),
        "by_country_tier": tier.to_dict(orient="records"),
        "gross_usd": gross,
        "refunds_usd": float(totals["refunds"] or 0),
        "refund_rate": (float(totals["refunds"] or 0) / gross) if gross else None,
    }


def as_records(df: pd.DataFrame) -> list[dict]:
    """JSON-friendly records (dates -> ISO strings, NaN -> None)."""
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]) or out[c].dtype == object:
            out[c] = out[c].astype(str).where(out[c].notna(), None)
    return out.astype(object).where(out.notna(), None).to_dict(orient="records")

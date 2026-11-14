"""Offline analyst: deterministic intent templates (no API key needed).

Used automatically when no LLM key is configured, and wrapped by the ``mock``
provider so CI exercises the full agent (guard -> execute -> explain) path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SEGMENT_WORDS = {
    "channel": "acquisition_channel",
    "acquisition": "acquisition_channel",
    "platform": "platform",
    "country": "country_tier",
    "tier": "country_tier",
    "device": "device_tier",
}
CHANNEL_VALUES = ("organic", "paid_social", "search", "referral", "influencer")
DESTRUCTIVE = re.compile(
    r"\b(delete|drop|truncate|insert|update|alter|create|attach|copy|pragma|install|grant)\b"
)
EXPERIMENTS = ("onboarding_flow_v2", "paywall_redesign", "streak_reminder")


@dataclass
class Plan:
    """What the analyst will do for a question."""

    intent: str
    sql: str | None = None
    chart: dict = field(default_factory=dict)
    notes: str = ""
    tool: str | None = None  # e.g. "get_experiment_report"
    tool_args: dict = field(default_factory=dict)
    refuse: str | None = None


def _segment(q: str) -> str | None:
    # Specific words first: "device tier" must not resolve to the generic "tier" (country).
    if re.search(r"\bdevices?\b", q):
        return "device_tier"
    if re.search(r"\bcountr(y|ies)\b", q):
        return "country_tier"
    m = re.search(
        r"\b(?:by|per|across|which|each)\s+(?:\w+\s+)?(channel|acquisition|platform|country|tier|device)",
        q,
    )
    if m:
        return SEGMENT_WORDS[m.group(1)]
    for w, col in SEGMENT_WORDS.items():
        if re.search(rf"\b{w}s?\b", q):
            return col
    return None


def _day_n(q: str) -> int | None:
    m = re.search(r"\bd(?:ay)?[\s-]?(1|3|7|14|30)\b", q)
    return int(m.group(1)) if m else None


def _date_filter(q: str, column: str) -> tuple[str, str]:
    """(SQL predicate, human label) for simple relative/absolute date phrases."""
    m = re.search(r"\b(19|20)\d{2}\b", q)
    if m:
        y = m.group(0)
        return f"year({column}) = {y}", f"in {y}"
    m = re.search(r"last (\d+) days", q)
    if m:
        n = int(m.group(1))
        return (
            f"{column} > (select max({column}) from fct_revenue_daily_dates) - {n}",
            f"in the last {n} days",
        )
    if "last month" in q or "past month" in q:
        return (
            f"{column} > (select max({column}) from fct_revenue_daily_dates) - 30",
            "in the last 30 days",
        )
    if "last week" in q or "past week" in q:
        return (
            f"{column} > (select max({column}) from fct_revenue_daily_dates) - 7",
            "in the last 7 days",
        )
    return "1 = 1", "over the whole period"


def _dates(sql: str, column: str, table: str) -> str:
    return sql.replace("fct_revenue_daily_dates", table).replace(
        f"max({column}) from {table}", f"max({column}) from {table}"
    )


def plan(question: str) -> Plan:
    """Map a question to a templated plan (or a refusal)."""
    q = question.lower().strip()
    if DESTRUCTIVE.search(q) and re.search(r"\b(table|users|data|database|rows?|records?)\b", q):
        return Plan(
            "refuse", refuse="I can only run read-only analysis; I won't modify or delete data."
        )
    if re.search(r"\b(password|api key|secret|ssn|credit card|email address|phone number)\b", q):
        return Plan(
            "refuse",
            refuse="That information is not in the warehouse and I can't help retrieve personal secrets.",
        )
    if re.search(r"ignore (all|previous|the) (instructions|rules)", q):
        return Plan(
            "refuse",
            refuse="I can't change my instructions; ask a question about the product data.",
        )

    exp_id = next((e for e in EXPERIMENTS if e in q or e.replace("_", " ") in q), None)
    if exp_id is None and re.search(r"\b(experiment|a/b|ab test|ship)\b", q):
        if "paywall" in q:
            exp_id = "paywall_redesign"
        elif "streak" in q or "reminder" in q:
            exp_id = "streak_reminder"
        elif "onboarding" in q:
            exp_id = "onboarding_flow_v2"
    if exp_id:
        return Plan(
            "experiment",
            tool="get_experiment_report",
            tool_args={"experiment_id": exp_id},
            notes="Answered by the validated experimentation engine, not by ad-hoc SQL.",
        )
    if re.search(r"\b(experiments|tests)\b", q) and re.search(r"\b(list|which|what|all)\b", q):
        return Plan("experiment_list", tool="list_experiments")

    seg = _segment(q)
    day = _day_n(q)
    if "retention" in q or "retained" in q or day:
        n = day or 7
        if seg:
            sql = (
                f"with r as (select u.{seg} as segment, u.user_id, max(case when x.day_n = {n} then 1 else 0 end) as kept "
                f"from dim_users u left join fct_events x on x.user_id = u.user_id and x.event_name = 'session_start' "
                f"where u.signup_ts + interval {n + 1} day <= cast((select max(kpi_date) from agg_kpis_daily) as timestamp) + interval 1 day "
                f"group by 1, 2) select segment as {seg}, avg(kept) as d{n}_retention, count(*) as eligible_users "
                f"from r group by 1 order by 2 desc"
            )
            return Plan(
                "retention_by_segment",
                sql,
                {"type": "bar", "x": seg, "y": f"d{n}_retention"},
                f"D{n} retention = session in the day-{n} block among eligible users.",
            )
        sql = (
            "select day_n, sum(retained_users) / sum(eligible_users) as retention_rate, sum(eligible_users) as eligible_users "
            "from agg_retention_cohorts group by 1 order by 1"
        )
        if day:
            sql = (
                f"select sum(retained_users) / sum(eligible_users) as d{n}_retention, sum(eligible_users) as eligible_users "
                f"from agg_retention_cohorts where day_n = {n}"
            )
        return Plan(
            "retention",
            sql,
            {"type": "bar" if not day else "metric", "x": "day_n", "y": "retention_rate"},
            "Eligibility-aware exact-day retention.",
        )
    if re.search(r"\b(mrr|recurring)\b", q):
        return Plan(
            "mrr",
            "select revenue_date, mrr_usd, active_subscriptions, arppu_monthly_usd from fct_revenue_daily "
            "order by revenue_date desc limit 1",
            {"type": "metric", "y": "mrr_usd"},
        )
    if "arppu" in q or "per paying" in q:
        return Plan(
            "arppu",
            "select revenue_date, arppu_monthly_usd, active_subscriptions from fct_revenue_daily "
            "order by revenue_date desc limit 1",
            {"type": "metric", "y": "arppu_monthly_usd"},
        )
    if "refund" in q:
        return Plan(
            "refunds",
            "select sum(refunds_usd) / sum(gross_revenue_usd) as refund_rate, sum(refunds_usd) as refunds_usd, "
            "sum(gross_revenue_usd) as gross_revenue_usd from fct_revenue_daily",
            {"type": "metric", "y": "refund_rate"},
        )
    if "revenue" in q:
        if seg:
            return Plan(
                "revenue_by_segment",
                f"select {seg}, sum(lifetime_net_revenue_usd) as net_revenue_usd, "
                f"count(*) filter (where lifetime_net_revenue_usd > 0) as payers from dim_users group by 1 order by 2 desc",
                {"type": "bar", "x": seg, "y": "net_revenue_usd"},
            )
        pred, label = _date_filter(q, "revenue_date")
        sql = _dates(
            f"select sum(gross_revenue_usd) as gross_revenue_usd, sum(refunds_usd) as refunds_usd, "
            f"sum(net_revenue_usd) as net_revenue_usd, count(*) as days from fct_revenue_daily where {pred}",
            "revenue_date",
            "fct_revenue_daily",
        )
        return Plan(
            "revenue", sql, {"type": "metric", "y": "net_revenue_usd"}, f"Net revenue {label}."
        )
    if re.search(r"\b(dau|mau|wau|stickiness|active users)\b", q):
        if re.search(r"\b(trend|over time|daily|by day|chart)\b", q):
            return Plan(
                "dau_trend",
                "select kpi_date, dau, wau, mau, stickiness from agg_kpis_daily order by kpi_date",
                {"type": "line", "x": "kpi_date", "y": "dau"},
            )
        return Plan(
            "engagement",
            "select kpi_date, dau, wau, mau, stickiness from agg_kpis_daily order by kpi_date desc limit 1",
            {"type": "metric", "y": "dau"},
        )
    if re.search(r"\b(drop|bottleneck|leak|lose)\b", q) and "funnel" in q or "biggest drop" in q:
        return Plan(
            "funnel_drop",
            "select count(*) as signed_up, sum(is_onboarded) as onboarded, sum(is_trial) as trial, "
            "sum(is_paid) as paid, 1 - sum(is_onboarded) / count(*) as drop_signup_to_onboarded, "
            "1 - sum(is_trial) / sum(is_onboarded) as drop_onboarded_to_trial, "
            "1 - sum(is_paid) / sum(is_trial) as drop_trial_to_paid from fct_funnel_user",
            {"type": "funnel"},
        )
    if re.search(r"\b(trial|paid|conversion|onboard|funnel|convert)", q):
        if seg:
            metric = (
                "trial_to_paid_rate"
                if "paid" in q and "trial" in q
                else "signup_to_paid_rate"
                if "paid" in q
                else "onboarding_rate"
                if "onboard" in q
                else "onboarded_to_trial_rate"
            )
            channel = next((c for c in CHANNEL_VALUES if c in q or c.replace("_", " ") in q), None)
            where = f"segment_type = '{seg}'" + (
                f" and segment_value = '{channel}'"
                if channel and seg == "acquisition_channel"
                else ""
            )
            return Plan(
                "conversion_by_segment",
                f"select segment_value as {seg}, {metric}, signups, onboarded, trials, paid "
                f"from agg_funnel_by_segment where {where} order by 2 desc",
                {"type": "bar", "x": seg, "y": metric},
            )
        return Plan(
            "funnel",
            "select count(*) as signed_up, sum(is_onboarded) as onboarded, sum(is_trial) as trial, "
            "sum(is_paid) as paid, avg(is_onboarded) as onboarding_rate, sum(is_trial) / sum(is_onboarded) as onboarded_to_trial_rate, "
            "sum(is_paid) / sum(is_trial) as trial_to_paid_rate, avg(is_paid) as signup_to_paid_rate from fct_funnel_user",
            {"type": "funnel"},
        )
    if re.search(r"\b(signups?|new users|users|sign ups?)\b", q):
        if re.search(r"\b(week|weekly|trend|over time|per day|daily)\b", q):
            return Plan(
                "signups_trend",
                "select date_trunc('week', signup_date) as week, sum(signups) as signups "
                "from agg_funnel_daily group by 1 order by 1",
                {"type": "line", "x": "week", "y": "signups"},
            )
        if seg:
            return Plan(
                "users_by_segment",
                f"select {seg}, count(*) as users from dim_users group by 1 order by 2 desc",
                {"type": "bar", "x": seg, "y": "users"},
            )
        return Plan(
            "user_count",
            "select count(*) as users, min(signup_date) as first_signup, max(signup_date) as last_signup from dim_users",
            {"type": "metric", "y": "users"},
        )
    return Plan(
        "unknown",
        refuse="I can't answer that offline. Try asking about funnel, retention, revenue, "
        "active users, signups or an experiment (e.g. 'Should we ship paywall_redesign?').",
    )


SUGGESTED_QUESTIONS = (
    "Where is the biggest drop in the funnel?",
    "Which acquisition channel has the best D7 retention?",
    "What is our net revenue in the last 30 days?",
    "Show the DAU trend",
    "Should we ship paywall_redesign?",
    "What is the trial to paid conversion by platform?",
)

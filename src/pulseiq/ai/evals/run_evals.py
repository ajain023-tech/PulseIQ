"""Run the AI-analyst eval set and report accuracy metrics."""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

import yaml

from pulseiq.ai.agent import ask
from pulseiq.ai.llm import get_client
from pulseiq.services.db import query

HERE = Path(__file__).parent


def _numbers(rows: list[dict]) -> list[float]:
    out = []
    for r in rows:
        for v in r.values():
            if (
                isinstance(v, int | float)
                and not isinstance(v, bool)
                and not (isinstance(v, float) and math.isnan(v))
            ):
                out.append(float(v))
    return out


def grade(item: dict, resp) -> dict:
    """Score one response against its reference."""
    kind = item["kind"]
    ref = None
    if item.get("reference_sql"):
        ref = query(item["reference_sql"]).iloc[0, 0]
    correct = False
    if kind == "number":
        tol = item.get("tol", 1e-3)
        ref_f = float(ref)
        correct = any(
            math.isclose(v, ref_f, rel_tol=tol, abs_tol=1e-9) for v in _numbers(resp.rows)
        )
    elif kind in ("label", "decision"):
        correct = str(ref).lower() in resp.answer.lower()
    elif kind == "refuse":
        correct = resp.refused
    elif kind == "no_data":
        correct = (not resp.refused) and "no data" in resp.answer.lower()
    expects_sql = kind in ("number", "label", "no_data")
    return {
        "id": item["id"],
        "question": item["question"],
        "kind": kind,
        "reference": None
        if ref is None
        else (float(ref) if isinstance(ref, int | float) else str(ref)),
        "correct": bool(correct),
        "refused": resp.refused,
        "sql_valid": (resp.sql is not None) if expects_sql else None,
        "executed": (resp.error is None and not resp.refused)
        if expects_sql or kind == "decision"
        else None,
        "latency_ms": resp.latency_ms,
        "answer": resp.answer[:240],
        "sql": resp.sql,
    }


def run(provider: str = "mock", out_dir: Path | None = None) -> dict:
    """Run every question; write results JSON + markdown if ``out_dir`` is given."""
    items = yaml.safe_load((HERE / "questions.yaml").read_text())["questions"]
    client = get_client(provider)
    results = [grade(i, ask(i["question"], provider=provider, client=client)) for i in items]
    sql_items = [r for r in results if r["sql_valid"] is not None]
    exec_items = [r for r in results if r["executed"] is not None]
    refuse_items = [r for r in results if r["kind"] == "refuse"]
    answer_items = [r for r in results if r["kind"] != "refuse"]
    summary = {
        "provider": client.provider if client else "offline",
        "n_questions": len(results),
        "sql_valid_pct": sum(r["sql_valid"] for r in sql_items) / len(sql_items),
        "execution_success_pct": sum(r["executed"] for r in exec_items) / len(exec_items),
        "answer_correct_pct": sum(r["correct"] for r in answer_items) / len(answer_items),
        "refusal_correct_pct": sum(r["correct"] for r in refuse_items) / len(refuse_items),
        "false_refusals": sum(r["refused"] for r in answer_items),
        "overall_correct_pct": sum(r["correct"] for r in results) / len(results),
        "median_latency_ms": statistics.median(r["latency_ms"] for r in results),
    }
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "ai_eval.json").write_text(
            json.dumps({"summary": summary, "results": results}, indent=2, default=str)
        )
        lines = [
            f"# AI analyst eval — provider `{summary['provider']}`",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Questions | {summary['n_questions']} |",
            f"| SQL valid | {summary['sql_valid_pct']:.0%} |",
            f"| Execution success | {summary['execution_success_pct']:.0%} |",
            f"| Answer correct (non-refusal items) | {summary['answer_correct_pct']:.0%} |",
            f"| Refusal correct | {summary['refusal_correct_pct']:.0%} |",
            f"| False refusals | {summary['false_refusals']} |",
            f"| Overall correct | {summary['overall_correct_pct']:.0%} |",
            f"| Median latency | {summary['median_latency_ms']:.0f} ms |",
            "",
            "| id | kind | correct | question |",
            "|---|---|:-:|---|",
            *[
                f"| {r['id']} | {r['kind']} | {'✔' if r['correct'] else '✘'} | {r['question']} |"
                for r in results
            ],
            "",
        ]
        (out_dir / "ai_eval.md").write_text("\n".join(lines))
    return summary

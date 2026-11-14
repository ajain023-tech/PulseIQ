"""SQL guardrails: single read-only SELECT over allow-listed marts, capped and timed out.

Defence in depth: (1) parse with sqlglot and reject anything but one SELECT,
(2) reject DDL/DML/ATTACH/COPY/PRAGMA/INSTALL/LOAD and file/HTTP table functions,
(3) allow-list tables and columns, (4) enforce LIMIT, (5) execute on a read-only
connection with a timeout.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import duckdb
import pandas as pd
import sqlglot
from sqlglot import exp

from .catalog import ALLOWED_TABLES, allowed_columns

MAX_ROWS = 1000
TIMEOUT_SECONDS = 5.0
FORBIDDEN_FUNCTIONS = {
    "read_csv",
    "read_csv_auto",
    "read_parquet",
    "read_json",
    "read_json_auto",
    "read_ndjson",
    "read_text",
    "read_blob",
    "glob",
    "parquet_scan",
    "csv_scan",
    "httpfs",
    "sqlite_scan",
    "postgres_scan",
    "mysql_scan",
    "iceberg_scan",
    "delta_scan",
    "query_table",
    "query",
    "getenv",
    "current_setting",
    "duckdb_settings",
    "duckdb_extensions",
}
_FORBIDDEN_NODE_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Drop",
    "Create",
    "Alter",
    "Command",
    "Copy",
    "Merge",
    "Pragma",
    "Set",
    "Use",
    "TruncateTable",
    "Attach",
    "Detach",
    "Install",
    "Transaction",
    "Commit",
    "Rollback",
)
FORBIDDEN_NODES = tuple(getattr(exp, n) for n in _FORBIDDEN_NODE_NAMES if hasattr(exp, n))


class GuardError(ValueError):
    """Raised when SQL violates a guardrail (message is safe to show the user/LLM)."""


@dataclass
class GuardedSQL:
    """Validated SQL ready to execute."""

    sql: str
    tables: list[str]


def validate(sql: str) -> GuardedSQL:
    """Validate and normalise ``sql``; raise ``GuardError`` with a helpful message."""
    if not sql or not sql.strip():
        raise GuardError("Empty SQL.")
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise GuardError(f"SQL does not parse: {str(e).splitlines()[0]}") from e
    if len(statements) != 1:
        raise GuardError("Exactly one statement is allowed.")
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        raise GuardError(f"Only SELECT queries are allowed (got {type(tree).__name__.upper()}).")
    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise GuardError(f"Forbidden operation: {type(node).__name__.upper()}.")
        if isinstance(node, exp.Func):
            name = (node.sql_name() if not isinstance(node, exp.Anonymous) else node.name).lower()
            if name in FORBIDDEN_FUNCTIONS or name.startswith("read_"):
                raise GuardError(
                    f"Function {name}() is not allowed (no file, network or settings access)."
                )
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    tables = []
    for t in tree.find_all(exp.Table):
        if isinstance(t.this, exp.Func) or not isinstance(t.this, exp.Identifier):
            raise GuardError("Table functions are not allowed; query the marts directly.")
        name = t.name.lower()
        if t.args.get("db") or t.args.get("catalog"):
            raise GuardError(f"Qualified table names are not allowed: {t.sql()}.")
        if name in ctes:
            continue
        if name not in ALLOWED_TABLES:
            raise GuardError(
                f"Unknown table '{name}'. Allowed tables: {', '.join(ALLOWED_TABLES)}."
            )
        tables.append(name)
    known = allowed_columns()
    aliases = {a.alias.lower() for a in tree.find_all(exp.Alias)} | {
        c.alias_or_name.lower() for c in tree.find_all(exp.CTE)
    }
    for cte in tree.find_all(exp.CTE):
        aliases |= (
            {c.name.lower() for c in cte.args.get("alias").columns}
            if cte.args.get("alias")
            else set()
        )
    for col in tree.find_all(exp.Column):
        name = col.name.lower()
        if name and name != "*" and name not in known and name not in aliases:
            raise GuardError(f"Unknown column '{col.name}'. Check the schema catalog.")
    limit = tree.args.get("limit")
    if limit is None:
        tree = tree.limit(MAX_ROWS)
    else:
        try:
            n = int(limit.expression.name)
            if n > MAX_ROWS:
                tree = tree.limit(MAX_ROWS)
        except (AttributeError, ValueError):
            tree = tree.limit(MAX_ROWS)
    return GuardedSQL(sql=tree.sql(dialect="duckdb"), tables=sorted(set(tables)))


def execute(
    con: duckdb.DuckDBPyConnection, guarded: GuardedSQL, timeout: float = TIMEOUT_SECONDS
) -> pd.DataFrame:
    """Run validated SQL with a timeout (interrupts the query) and a row cap."""
    result: dict = {}

    def run() -> None:
        try:
            result["df"] = con.execute(guarded.sql).df().head(MAX_ROWS)
        except Exception as e:  # noqa: BLE001
            result["error"] = e

    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        con.interrupt()
        th.join(1.0)
        raise GuardError(f"Query exceeded the {timeout:.0f} s timeout.")
    if "error" in result:
        raise GuardError(f"Query failed: {str(result['error']).splitlines()[0]}")
    return result["df"]

"""Read-only warehouse access with a per-process connection and per-call cursors."""

from __future__ import annotations

import threading
import time
from functools import wraps
from pathlib import Path

import duckdb
import pandas as pd

from pulseiq.config import get_settings

_lock = threading.Lock()
_con: duckdb.DuckDBPyConnection | None = None
_con_path: Path | None = None


def connection() -> duckdb.DuckDBPyConnection:
    """Shared read-only connection to the configured warehouse (re-opened if the path changes)."""
    global _con, _con_path
    path = get_settings().warehouse_path
    with _lock:
        if _con is None or _con_path != path:
            if not path.exists():
                raise FileNotFoundError(f"Warehouse not found at {path}. Run `pulseiq build`.")
            if _con is not None:
                _con.close()
            _con = duckdb.connect(str(path), read_only=True)
            _con_path = path
        return _con


def reset() -> None:
    """Close the shared connection (tests, or after a rebuild)."""
    global _con, _con_path
    with _lock:
        if _con is not None:
            _con.close()
        _con, _con_path = None, None
        _CACHE.clear()


def cursor() -> duckdb.DuckDBPyConnection:
    """A thread-safe cursor on the shared read-only connection."""
    return connection().cursor()


def query(sql: str, params: list | None = None) -> pd.DataFrame:
    """Run a parameterised query and return a DataFrame."""
    with cursor() as cur:
        return cur.execute(sql, params or []).df()


_CACHE: dict = {}
TTL_SECONDS = 600


def cached(fn):
    """Small TTL cache keyed by function name + hashable arguments."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        key = (fn.__qualname__, args, tuple(sorted(kwargs.items())))
        hit = _CACHE.get(key)
        now = time.monotonic()
        if hit and now - hit[0] < TTL_SECONDS:
            return hit[1]
        value = fn(*args, **kwargs)
        if len(_CACHE) > 512:
            _CACHE.clear()
        _CACHE[key] = (now, value)
        return value

    return wrapper

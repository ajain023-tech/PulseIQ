"""Latency benchmark for cached API endpoints (in-process TestClient).

Usage: python scripts/bench_api.py [--n 50]
Target: p95 < 300 ms for cached endpoints on the small warehouse.
"""

from __future__ import annotations

import argparse
import statistics
import time

from fastapi.testclient import TestClient

from pulseiq.api.app import app

ENDPOINTS = [
    ("GET", "/api/v1/health", None),
    ("GET", "/api/v1/kpis", None),
    ("GET", "/api/v1/kpis?platform=ios&channel=referral", None),
    ("GET", "/api/v1/funnel?by=channel", None),
    ("GET", "/api/v1/retention/cohorts", None),
    ("GET", "/api/v1/revenue/daily", None),
    ("GET", "/api/v1/experiments", None),
    ("GET", "/api/v1/experiments/paywall_redesign", None),
    ("GET", "/api/v1/predictions/at-risk?limit=50", None),
    ("POST", "/api/v1/power", {"baseline": 0.2, "mde": 0.02}),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50)
    args = parser.parse_args()
    client = TestClient(app)
    print(f"{'endpoint':<48}{'p50 ms':>9}{'p95 ms':>9}")
    worst = 0.0
    for method, path, body in ENDPOINTS:
        client.request(method, path, json=body)  # warm the cache
        times = []
        for _ in range(args.n):
            t = time.perf_counter()
            r = client.request(method, path, json=body)
            times.append((time.perf_counter() - t) * 1000)
            assert r.status_code == 200, (path, r.status_code)
        p95 = statistics.quantiles(times, n=20)[18]
        worst = max(worst, p95)
        print(f"{method + ' ' + path:<48}{statistics.median(times):>9.1f}{p95:>9.1f}")
    print(f"worst p95: {worst:.1f} ms -> {'PASS' if worst < 300 else 'FAIL'} (target < 300 ms)")


if __name__ == "__main__":
    main()

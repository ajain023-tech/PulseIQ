"""Visit every dashboard page in headless Chromium, check for errors, save screenshots.

Usage (with the dashboard running):  python scripts/screenshots.py --url http://localhost:8501
Writes docs/images/<page>.png and prints a pass/fail line per page.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGES = {
    "home": "",
    "funnel": "Funnel",
    "retention": "Retention",
    "revenue": "Revenue",
    "experiments": "Experiments",
    "experiment_designer": "Experiment_Designer",
    "retention_model": "Retention_Model",
    "ai_analyst": "AI_Analyst",
    "data_methods": "Data_&_Methods",
}
OUT = Path(__file__).resolve().parents[1] / "docs" / "images"


def wait_ready(page) -> None:
    page.wait_for_selector("[data-testid='stApp']", timeout=60_000)
    page.wait_for_timeout(1500)
    page.wait_for_function(
        "() => !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=90_000
    )
    page.wait_for_timeout(2500)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8501")
    ap.add_argument("--out", default=str(OUT), help="Directory for the PNGs (default docs/images)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        for name, path in PAGES.items():
            page.goto(f"{args.url}/{path}", wait_until="networkidle")
            wait_ready(page)
            if name == "ai_analyst":
                page.get_by_role("button", name="Where is the biggest drop in the funnel?").click()
                wait_ready(page)
            errors = page.locator("[data-testid='stException']").count()
            title = (
                page.locator("h1").first.inner_text()
                if page.locator("h1").count()
                else "(no title)"
            )
            page.screenshot(path=str(out / f"{name}.png"), full_page=True)
            status = "PASS" if errors == 0 else f"FAIL ({errors} exceptions)"
            failures += errors > 0
            print(f"{name:<22} {status:<10} title={title!r}")
        browser.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

"""
Screenshot the analytics dashboard, one file per section. Author: Ashok Chacko.

Signs in, waits for every Vega chart to finish drawing, then clips each
section to its own PNG at 2x so the images stay sharp in the A10 PDF and on
the poster. Nothing of the browser is in the picture, so there is no browser
bar to crop off afterwards.

Local:
    export DASHBOARD_USER=mohitg2 DASHBOARD_PASSWORD=...
    python docs/a10/make_dashboard_screenshots.py

Production (what to run after deploying):
    python docs/a10/make_dashboard_screenshots.py --base-url https://<host>

Needs playwright: pip install playwright && playwright install chromium
"""

import argparse
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT_DIR = Path(__file__).resolve().parent
SECTIONS = {
    "sec-performance": "a10_dashboard_performance.png",
    "sec-behavior": "a10_dashboard_behavior.png",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8901")
    parser.add_argument("--days", default="all", help="time-range filter to capture")
    parser.add_argument("--width", type=int, default=1500)
    args = parser.parse_args()

    username = os.environ.get("DASHBOARD_USER")
    password = os.environ.get("DASHBOARD_PASSWORD")
    if not username or not password:
        sys.exit("Set DASHBOARD_USER and DASHBOARD_PASSWORD first.")

    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": args.width, "height": 1200},
                                device_scale_factor=2)

        page.goto(f"{args.base_url}/accounts/login/", wait_until="networkidle")
        page.fill("input[name='username']", username)
        page.fill("input[name='password']", password)
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        page.goto(f"{args.base_url}/analytics/?days={args.days}", wait_until="networkidle")

        # vegaEmbed replaces the placeholder with an <svg>; wait for all of them
        # rather than a fixed sleep, or a slow chart lands as an empty panel.
        expected = page.locator(".vega-chart").count()
        page.wait_for_function(
            "n => document.querySelectorAll('.vega-chart svg, .vega-chart canvas').length >= n",
            arg=expected, timeout=30_000)
        page.wait_for_timeout(600)  # let the last animation settle

        for section_id, filename in SECTIONS.items():
            target = OUT_DIR / filename
            page.locator(f"section[aria-labelledby='{section_id}']").screenshot(path=str(target))
            print(f"  wrote {target.relative_to(Path.cwd())}")

        browser.close()
        print(f"  ({expected} charts on the page)")


if __name__ == "__main__":
    main()

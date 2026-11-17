"""
Screenshot the analytics dashboard, one file per section. Author: Ashok Chacko;
safety changes for the final A10 run: Tejas Jaggi.

Signs in, opens /analytics/ with the "Benchmark run" data source and the whole
time range, waits for every Vega chart to finish drawing, then clips the
performance, behavior and cost sections to their own PNGs at 2x. Only the
sections are captured, so the site header (which shows the signed-in user
name) is never in a picture.

Credentials come only from the environment, never from the command line (so
they stay out of shell history and the process list), and are never printed.
Nothing about the session is saved: no cookies, no storage state.

Every run writes new, timestamped files and refuses to overwrite anything, so
committed screenshots are never replaced by accident.

    export DASHBOARD_USER=mohitg2           # bash; PowerShell: $env:DASHBOARD_USER="mohitg2"
    export DASHBOARD_PASSWORD=...           # type it here, not on the command line below
    python docs/a10/make_dashboard_screenshots.py                      # production
    python docs/a10/make_dashboard_screenshots.py --base-url http://127.0.0.1:8000

Needs playwright on the machine you run it from (never on PythonAnywhere):
    pip install playwright && playwright install chromium
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_BASE_URL = "https://tjaggi.pythonanywhere.com"
DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "screenshots"
SECTIONS = ("sec-performance", "sec-behavior", "sec-cost")


def fail(message):
    sys.exit(f"STOPPED: {message}")


def remove_partial(paths):
    """A failed run leaves no half set behind: delete what this run wrote."""
    for path in paths:
        path.unlink(missing_ok=True)
    paths.clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--days", default="all", choices=("7", "30", "90", "all"))
    parser.add_argument("--source", default="benchmark", choices=("benchmark", "live", "simulated", "all"),
                        help='data source filter; "all" leaves it unset (default: benchmark)')
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--width", type=int, default=1500)
    args = parser.parse_args()

    username = os.environ.get("DASHBOARD_USER")
    password = os.environ.get("DASHBOARD_PASSWORD")
    if not username or not password:
        fail("set DASHBOARD_USER and DASHBOARD_PASSWORD in the environment first.")

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        fail("playwright is not installed here: pip install playwright && playwright install chromium")

    base = args.base_url.rstrip("/")
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    targets = {section: out_dir / f"a10_{section.removeprefix('sec-')}_{args.source}_{stamp}.png"
               for section in SECTIONS}
    clashes = [str(path) for path in targets.values() if path.exists()]
    if clashes:
        fail(f"refusing to overwrite {clashes}; wait a second and run again.")

    query = f"days={args.days}" + ("" if args.source == "all" else f"&source={args.source}")
    written = []
    with sync_playwright() as play:
        browser = play.chromium.launch()
        try:
            context = browser.new_context(viewport={"width": args.width, "height": 1200},
                                          device_scale_factor=2)
            page = context.new_page()

            response = page.goto(f"{base}/accounts/login/", wait_until="networkidle")
            if response is None or response.status >= 400:
                fail(f"login page returned HTTP {response.status if response else 'no response'}.")
            # /accounts/login/ is DataPact's own LoginView (Django's AuthenticationForm).
            page.fill("input[name='username']", username)
            page.fill("input[name='password']", password)
            page.click("button[type='submit']")
            page.wait_for_load_state("networkidle")
            if "/accounts/login" in page.url:
                fail("sign-in failed (still on the login page). Check DASHBOARD_USER and "
                     "DASHBOARD_PASSWORD; their values are not shown here.")

            response = page.goto(f"{base}/analytics/?{query}", wait_until="networkidle")
            if response is None or response.status >= 400:
                fail(f"/analytics/ returned HTTP {response.status if response else 'no response'}.")
            if "/accounts/login" in page.url:
                fail("/analytics/ sent us back to the login page; the session was not accepted.")
            if args.source != "all" and page.locator("#f-source").input_value() != args.source:
                fail(f'the data source filter did not apply ("{args.source}").')

            # vegaEmbed replaces each placeholder with an <svg> or <canvas>; wait for all of
            # them rather than a fixed sleep, then refuse to save if any chart failed.
            expected = page.locator(".vega-chart").count()
            if expected == 0:
                fail("no charts on the page (is the range empty, or the A10 code not deployed?).")
            page.wait_for_function(
                "n => document.querySelectorAll('.vega-chart svg, .vega-chart canvas').length >= n",
                arg=expected, timeout=45_000)
            if page.locator(".vega-chart .chart__fallback").count():
                fail("at least one chart failed to render; nothing was saved.")
            page.wait_for_timeout(600)  # let the last transition settle

            for section, target in targets.items():
                image = page.locator(f"section[aria-labelledby='{section}']").screenshot()
                with open(target, "xb") as handle:  # "x": never overwrite an existing file
                    handle.write(image)
                written.append(target)
            print(f"{expected} charts rendered; source={args.source}, days={args.days}, site={base}")
        except PlaywrightError as exc:
            # Playwright messages name selectors and URLs, never the typed values.
            remove_partial(written)
            fail(f"browser step failed: {exc.message.splitlines()[0]}")
        except BaseException:
            remove_partial(written)
            raise
        finally:
            browser.close()

    for path in written:
        print(f"  wrote {path}")


if __name__ == "__main__":
    main()

"""
Render poster.html to a 22" x 36" portrait PDF. Author: Ashok Chacko.

Prints the measured content height first, because the one thing that ruins a
poster is silently spilling onto a second page. The SVG figures stay vector in
the PDF, so the printed poster is sharp at any size.

    python docs/poster/make_poster_pdf.py

Needs playwright: pip install playwright && playwright install chromium
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "poster.html"
TARGET = HERE / "DataPact_poster_22x36.pdf"

PAGE_W_IN, PAGE_H_IN = 22, 36
PX_PER_IN = 96  # CSS pixels per inch


def main():
    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": PAGE_W_IN * PX_PER_IN,
                                          "height": PAGE_H_IN * PX_PER_IN})
        page.goto(SOURCE.as_uri(), wait_until="networkidle")

        missing = page.evaluate(
            "Array.from(document.images).filter(i => !i.complete || !i.naturalWidth)"
            ".map(i => i.getAttribute('src'))")
        if missing:
            raise SystemExit(f"These images did not load: {missing}")

        content_px = page.evaluate("document.documentElement.scrollHeight")
        content_in = content_px / PX_PER_IN
        print(f"  content height: {content_in:.2f} in of {PAGE_H_IN} in "
              f"({content_in / PAGE_H_IN * 100:.0f}% of the page)")
        if content_in > PAGE_H_IN:
            print(f"  *** OVERFLOWS by {content_in - PAGE_H_IN:.2f} in - it will print on "
                  f"two pages. Shrink something. ***")
        elif content_in < PAGE_H_IN * 0.88:
            print(f"  *** {PAGE_H_IN - content_in:.2f} in of empty space at the bottom. "
                  f"Scale something up. ***")

        page.pdf(path=str(TARGET), width=f"{PAGE_W_IN}in", height=f"{PAGE_H_IN}in",
                 print_background=True,
                 margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        browser.close()

    size_mb = TARGET.stat().st_size / 1_048_576
    print(f"  wrote {TARGET.relative_to(Path.cwd())} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()

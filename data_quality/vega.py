"""
Vega-Lite chart specifications - A4 Part 1, Tejas Jaggi.

Each spec is built here as a plain dict and served two ways: as JSON from its
own endpoint under /vega-lite/, and embedded into the charts page, which fetches
that same endpoint. One definition, so the published spec and the rendered chart
can never drift apart.

Neither spec carries data. Both point at an internal JSON API through
``data: {"url": ...}``, which is what A4 asks for - inline data would freeze a
copy of the database into the chart and stop reflecting new validation runs.
"""

from django.urls import reverse

VEGA_LITE_SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"

# The status colours the rest of the site uses (the badges in the tables and the
# Matplotlib chart from A3), so an outcome keeps one colour everywhere. Stage 3E:
# the Pass / Fail / Warn inks of DESIGN.md (--pass-ink, --fail-ink, --warn-ink);
# they were the pre-redesign #1d6b36, #a12a2a, #855c11.
OUTCOME_RANGE = ["#1a5f32", "#9f2718", "#7a5207"]
OUTCOME_DOMAIN = ["Passed", "Failed", "Error"]
# On the scatter the outcome is a shape too, so colour is never the only cue.
OUTCOME_SHAPES = ["circle", "square", "triangle-up"]

# Stage 3E: the design system's type and inks, in every spec. Archivo is the
# site's self-hosted interface face; the charts page waits for it to load before
# drawing (a canvas or SVG does not pick a font up from CSS by itself), and the
# rest of the stack is the same fallback the stylesheet uses.
FONT = "Archivo, 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif"
INK = "#121b20"          # --ink, Graphite
INK_SOFT = "#46545b"     # --ink-soft, Soft Graphite
LINE = "#dde3e3"         # --line, Rule Line (gridlines)
LINE_STRONG = "#77878d"  # --line-strong, Field Edge (axis domain and ticks)

CHART_CONFIG = {
    "font": FONT,
    "background": "#ffffff",
    "view": {"stroke": None},
    "title": {
        "font": FONT, "fontSize": 15, "fontWeight": 650, "color": INK, "anchor": "start", "offset": 12,
        "subtitleFont": FONT, "subtitleFontSize": 13, "subtitleColor": INK_SOFT, "subtitlePadding": 4,
    },
    "axis": {
        "labelFont": FONT, "labelFontSize": 12, "labelColor": INK_SOFT, "labelPadding": 6,
        "titleFont": FONT, "titleFontSize": 12, "titleFontWeight": 600, "titleColor": INK, "titlePadding": 10,
        "gridColor": LINE, "domainColor": LINE_STRONG, "tickColor": LINE_STRONG,
    },
    # Above the plot in one row, its title above the entries: a legend at the
    # side took a fixed column and, on a phone, squeezed the bars into about
    # 140px; a title beside the entries left no room for the third one.
    "legend": {
        "orient": "top", "direction": "horizontal", "titleOrient": "top",
        "labelFont": FONT, "labelFontSize": 12, "labelColor": INK,
        "titleFont": FONT, "titleFontSize": 12, "titleFontWeight": 600, "titleColor": INK,
        "symbolSize": 110, "columnPadding": 14,
    },
}


def run_outcomes_bar_spec():
    """Bar chart: how many validation runs ended in each outcome."""
    return {
        "$schema": VEGA_LITE_SCHEMA,
        "title": {
            "text": "Validation run outcomes",
            # Two short lines: a Vega title never wraps, and one long line was
            # cut off on a phone (Stage 3E).
            "subtitle": ["Every file DataPact has checked,", "grouped by result"],
            "anchor": "start",
        },
        "data": {"url": reverse("data_quality:api-run-outcomes")},
        "width": "container",
        "height": 280,
        "mark": {"type": "bar", "tooltip": True},
        "encoding": {
            "x": {
                "field": "outcome",
                "type": "nominal",
                "title": "Outcome",
                "sort": OUTCOME_DOMAIN,
                "axis": {"labelAngle": 0},
            },
            "y": {
                "field": "runs",
                "type": "quantitative",
                "title": "Validation runs",
                "axis": {"tickMinStep": 1},
            },
            "color": {
                "field": "outcome",
                "type": "nominal",
                "title": "Outcome",
                "scale": {"domain": OUTCOME_DOMAIN, "range": OUTCOME_RANGE},
            },
        },
        "config": CHART_CONFIG,
    }


def rows_vs_failures_scatter_spec():
    """
    Scatter: rows checked against rows that failed, one point per run.

    The question it answers is whether big files are the ones that break. On the
    demo data they are not - the largest runs pass, and the worst failure is a
    mid-sized file - which is the argument for validating every file rather than
    only the large ones.
    """
    return {
        "$schema": VEGA_LITE_SCHEMA,
        "title": {
            "text": "Rows checked vs rows failed",
            "subtitle": ["One point per validation run;", "colour and shape show the outcome"],
            "anchor": "start",
        },
        "data": {"url": reverse("data_quality:api-run-volume")},
        "width": "container",
        "height": 280,
        # Full opacity, so a point shows the outcome's exact ink (Vega-Lite's
        # default of 0.7 lightened it); a white edge keeps overlapping points apart.
        "mark": {"type": "point", "filled": True, "size": 110, "tooltip": True,
                 "opacity": 1, "stroke": "#ffffff", "strokeWidth": 1},
        "encoding": {
            "x": {
                "field": "rows_checked",
                "type": "quantitative",
                "title": "Rows checked in the file",
                "scale": {"zero": False, "nice": True},
            },
            "y": {
                "field": "rows_failed",
                "type": "quantitative",
                "title": "Rows that failed a rule",
                "axis": {"tickMinStep": 1},
            },
            "color": {
                "field": "outcome",
                "type": "nominal",
                "title": "Outcome",
                "scale": {"domain": OUTCOME_DOMAIN, "range": OUTCOME_RANGE},
            },
            "shape": {
                "field": "outcome",
                "type": "nominal",
                "title": "Outcome",
                "scale": {"domain": OUTCOME_DOMAIN, "range": OUTCOME_SHAPES},
            },
            "tooltip": [
                {"field": "file_name", "type": "nominal", "title": "File"},
                {"field": "dataset", "type": "nominal", "title": "Dataset"},
                {"field": "rows_checked", "type": "quantitative", "title": "Rows checked"},
                {"field": "rows_failed", "type": "quantitative", "title": "Rows failed"},
                {"field": "outcome", "type": "nominal", "title": "Outcome"},
            ],
        },
        "config": CHART_CONFIG,
    }


# Keyed by the number used in the published URLs (/vega-lite/chart1.json).
CHART_SPECS = {
    1: run_outcomes_bar_spec,
    2: rows_vs_failures_scatter_spec,
}

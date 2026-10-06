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

# The status colours the rest of the site already uses (the badges in the tables
# and the Matplotlib chart from A3), so an outcome keeps one colour everywhere.
OUTCOME_RANGE = ["#1d6b36", "#a12a2a", "#855c11"]
OUTCOME_DOMAIN = ["Passed", "Failed", "Error"]


def run_outcomes_bar_spec():
    """Bar chart: how many validation runs ended in each outcome."""
    return {
        "$schema": VEGA_LITE_SCHEMA,
        "title": {
            "text": "Validation Run Outcomes",
            "subtitle": "Every file DataPact has checked, grouped by result",
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
            "text": "Rows Checked vs Rows Failed",
            "subtitle": "One point per validation run; colour is the outcome",
            "anchor": "start",
        },
        "data": {"url": reverse("data_quality:api-run-volume")},
        "width": "container",
        "height": 280,
        "mark": {"type": "point", "filled": True, "size": 110, "tooltip": True},
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
            "tooltip": [
                {"field": "file_name", "type": "nominal", "title": "File"},
                {"field": "dataset", "type": "nominal", "title": "Dataset"},
                {"field": "rows_checked", "type": "quantitative", "title": "Rows checked"},
                {"field": "rows_failed", "type": "quantitative", "title": "Rows failed"},
                {"field": "outcome", "type": "nominal", "title": "Outcome"},
            ],
        },
    }


# Keyed by the number used in the published URLs (/vega-lite/chart1.json).
CHART_SPECS = {
    1: run_outcomes_bar_spec,
    2: rows_vs_failures_scatter_spec,
}

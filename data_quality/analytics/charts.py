"""
Small helpers shared by the dashboard sections (A10, Connor Slattery).

Charts are Vega-Lite specs with their data inline. The dashboard renders each
spec with vegaEmbed, the same library the A4 charts page uses, loaded from a
CDN so nothing is added to requirements.

Use chart(...) to wrap a spec for a template partial:

    {"id": "cost-by-engine", "title": "...", "caption": "...", "spec": {...}}

and include analytics/_chart.html with chart=that dict.
"""

import copy

from django.db.models import Avg, Count, Sum

from ..models import AIRequestLog
from ..vega import CHART_CONFIG

VEGA_LITE_SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"

# One colour per engine everywhere on the dashboard. Stage 3I: frozen as they
# are, so the dashboard keeps matching the figures in the A10 report and poster.
ENGINE_DOMAIN = ["local", "groq", "ollama"]
ENGINE_RANGE = ["#2f5d8a", "#c2662d", "#6b8f3a"]
ENGINE_LABELS = {"local": "Local (SmolLM2)", "groq": "Groq API", "ollama": "Ollama"}

# Stage 3I: a legend names each engine in the filter's words (AIRequestLog.Engine
# labels: "Local model", "Groq API", "Ollama (benchmark)"). Only the legend's text
# changes; the data keeps the stored values, and so do the colours.
ENGINE_LEGEND_LABELS = " : ".join(
    f"datum.value === '{value}' ? '{label}'" for value, label in AIRequestLog.Engine.choices
) + " : datum.value"


def engine_color(title="Engine"):
    return {"field": "engine", "type": "nominal", "title": title,
            "scale": {"domain": ENGINE_DOMAIN, "range": ENGINE_RANGE},
            "legend": {"labelExpr": ENGINE_LEGEND_LABELS}}


def base_spec(values, height=260):
    # Stage 3I: the design system's chart settings (vega.CHART_CONFIG, from
    # Stage 3E): Archivo, the site's inks, legends above the plot. It already
    # holds the two settings this used to set (no view outline, 12px axis text).
    return {
        "$schema": VEGA_LITE_SCHEMA,
        "data": {"values": values},
        "width": "container",
        "height": height,
        "config": copy.deepcopy(CHART_CONFIG),
    }


def chart(chart_id, title, caption, spec, wide=False):
    return {"id": chart_id, "title": title, "caption": caption, "spec": spec, "wide": wide}


def percentile(values, pct):
    """pct-th percentile of a list of numbers (linear interpolation), or 0 for none."""
    data = sorted(values)
    if not data:
        return 0.0
    k = (len(data) - 1) * pct / 100
    low = int(k)
    high = min(low + 1, len(data) - 1)
    return data[low] + (data[high] - data[low]) * (k - low)


def totals(qs):
    """Counts and sums most sections want, in one query."""
    return qs.aggregate(requests=Count("id"), cost=Sum("cost_usd"), latency=Avg("latency_ms"),
                        prompt=Sum("prompt_tokens"), completion=Sum("completion_tokens"))

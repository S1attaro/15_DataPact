"""
AI analytics dashboard - A10 (Connor Slattery; performance and behavior
sections by Ashok Chacko).

One page, three sections, each built from the same filtered AIRequestLog
queryset by its own module in data_quality/analytics/. The filters are plain
GET parameters, so a filtered view can be bookmarked or linked:

    ?days=7|30|90|all   time range, counted back from the newest row
    ?engine=local|groq|ollama
    ?source=live|benchmark|simulated

Signed-in users only, like every other page that shows project data.
"""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .analytics.behavior import behavior_context
from .analytics.cost import cost_context
from .analytics.performance import performance_context
from .models import AIRequestLog

DAY_CHOICES = (("7", "Last 7 days"), ("30", "Last 30 days"), ("90", "Last 90 days"), ("all", "All time"))
DEFAULT_DAYS = "30"


def filtered_logs(params):
    """The rows the page shows, and the filters it applied (bad values fall back to defaults)."""
    qs = AIRequestLog.objects.all()
    days = params.get("days", DEFAULT_DAYS)
    if days not in dict(DAY_CHOICES):
        days = DEFAULT_DAYS
    engine = params.get("engine", "")
    if engine not in AIRequestLog.Engine.values:
        engine = ""
    source = params.get("source", "")
    if source not in AIRequestLog.Source.values:
        source = ""

    if engine:
        qs = qs.filter(engine=engine)
    if source:
        qs = qs.filter(source=source)
    if days != "all":
        # Counted back from the newest row, not from today, so a loaded
        # benchmark file still shows up a week after it was recorded.
        newest = qs.aggregate(newest=Max("created_at"))["newest"]
        if newest is not None:
            qs = qs.filter(created_at__gt=newest - timedelta(days=int(days)))
    return qs, {"days": days, "engine": engine, "source": source}


@login_required
@require_GET
def analytics_dashboard(request):
    qs, filters = filtered_logs(request.GET)
    context = {
        "filters": filters,
        "day_choices": DAY_CHOICES,
        "engine_choices": AIRequestLog.Engine.choices,
        "source_choices": AIRequestLog.Source.choices,
        "row_count": qs.count(),
        "all_count": AIRequestLog.objects.count(),
        "performance": performance_context(qs),
        "behavior": behavior_context(qs),
        "cost": cost_context(qs),
    }
    return render(request, "data_quality/analytics/dashboard.html", context)

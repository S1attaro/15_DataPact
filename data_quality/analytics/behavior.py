"""
User behavior section of the A10 dashboard. OWNER: Ashok Chacko.

Questions it answers (docs/a10/analytics_design.md, B1-B3):
  B1  How often are the AI features used per day, and is use growing?
  B2  Which feature and which topics do users ask about most?
  B3  How often does the handbook fail to answer, and does the setup change
      how it fails?

B3 is drawn as shares rather than counts. Every setup answered the same 68
questions, so raw bars would be four columns of the same height and the
difference in how they fail would not show.

query_type holds a topic for handbook rows ("rules", "out_of_scope", ...) and
the rule type for explain rows ("RANGE", ...), so charts that mix the two
features label each bar with its feature.
"""

from collections import defaultdict
from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate

from .charts import base_spec, chart
from .performance import model_label

# Shown left to right, best outcome first.
STATUS_DOMAIN = ["ok", "not_found", "no_passages", "invalid"]
STATUS_RANGE = ["#3f7a3f", "#7f93a6", "#c9a227", "#b3462f"]
STATUS_LABELS = {
    "ok": "Answered",
    "not_found": "Said it did not know",
    "no_passages": "No passage matched",
    "invalid": "Reply failed checks",
}
FAILURE_STATUSES = ("not_found", "no_passages", "invalid")


def requests_per_day(qs):
    """
    Requests per day and feature, with quiet days written in as zero.

    Without the zeros a line chart joins the day before a gap straight to the
    day after it, drawing traffic on days that had none.
    """
    counts = defaultdict(int)
    for row in qs.annotate(day=TruncDate("created_at")).values("day", "feature"):
        counts[(row["day"], row["feature"])] += 1
    if not counts:
        return []
    days = {day for day, _ in counts}
    features = {feature for _, feature in counts}
    first, last = min(days), max(days)
    span = [first + timedelta(days=offset) for offset in range((last - first).days + 1)]
    return [{"day": day.isoformat(), "feature": feature, "requests": counts[(day, feature)]}
            for day in span for feature in sorted(features)]


def requests_by_topic(qs):
    counts = defaultdict(int)
    for row in qs.values("feature", "query_type"):
        counts[(row["feature"], row["query_type"] or "other")] += 1
    return [{"topic": topic, "feature": feature, "requests": n}
            for (feature, topic), n in sorted(counts.items(), key=lambda item: -item[1])]


def handbook_outcomes(qs):
    counts = defaultdict(int)
    for row in qs.filter(feature="handbook").values("engine", "model_name", "status"):
        counts[(row["engine"], row["model_name"], row["status"])] += 1
    return [{"model": model_label(engine, model), "status": STATUS_LABELS.get(status, status),
             "order": STATUS_DOMAIN.index(status) if status in STATUS_DOMAIN else len(STATUS_DOMAIN),
             "requests": n}
            for (engine, model, status), n in sorted(counts.items())]


# Out-of-scope outcomes, kept apart because they are different things: only
# not_found is the model declining. no_passages never reached a model, and
# invalid is a reply the model did write that our checks then threw out.
OUT_OF_SCOPE_OUTCOMES = (
    ("no_passages", "Not answered: no passage matched (model not called)"),
    ("not_found", "Not answered: model said it did not know"),
    ("invalid", "Not answered: reply failed our checks"),
    ("ok", "Answered anyway (should have declined)"),
)
OUT_OF_SCOPE_LABELS = dict(OUT_OF_SCOPE_OUTCOMES)


def out_of_scope_handling(qs):
    """
    Questions the handbook should decline, split by how each one ended.

    An answered out-of-scope question is the guardrail failing, so this is the
    one chart where the "Answered anyway" bar is the bad outcome.
    """
    counts = defaultdict(int)
    for row in qs.filter(feature="handbook", query_type="out_of_scope").values(
            "engine", "model_name", "status"):
        counts[(row["engine"], row["model_name"], row["status"])] += 1
    order = [status for status, _ in OUT_OF_SCOPE_OUTCOMES]
    return [{"model": model_label(engine, model),
             "outcome": OUT_OF_SCOPE_LABELS.get(status, status),
             "order": order.index(status) if status in order else len(order),
             "requests": n}
            for (engine, model, status), n in sorted(counts.items())]


def failure_rate(qs):
    handbook = qs.filter(feature="handbook")
    total = handbook.count()
    if not total:
        return 0.0
    return handbook.filter(status__in=FAILURE_STATUSES).count() / total * 100


def behavior_context(qs):
    by_feature = list(qs.values("feature").annotate(n=Count("id")).order_by("-n"))

    daily_spec = base_spec(requests_per_day(qs), height=240)
    daily_spec.update({
        "mark": {"type": "line", "point": True, "tooltip": True},
        "encoding": {
            "x": {"field": "day", "type": "temporal", "title": None},
            "y": {"field": "requests", "type": "quantitative", "title": "Requests per day"},
            "color": {"field": "feature", "type": "nominal", "title": "Feature",
                      "scale": {"domain": ["explain", "handbook"],
                                "range": ["#8a6d9c", "#2f5d8a"]}},
            "tooltip": [{"field": "day", "type": "temporal"}, {"field": "feature"},
                        {"field": "requests"}],
        },
    })

    topic_spec = base_spec(requests_by_topic(qs), height=300)
    topic_spec.update({
        "mark": {"type": "bar", "tooltip": True, "cornerRadiusEnd": 3},
        "encoding": {
            "y": {"field": "topic", "type": "nominal", "title": None, "sort": "-x"},
            "x": {"field": "requests", "type": "quantitative", "title": "Requests"},
            "color": {"field": "feature", "type": "nominal", "title": "Feature",
                      "scale": {"domain": ["explain", "handbook"],
                                "range": ["#8a6d9c", "#2f5d8a"]}},
            "tooltip": [{"field": "topic"}, {"field": "feature"}, {"field": "requests"}],
        },
    })

    outcome_spec = base_spec(handbook_outcomes(qs), height=240)
    outcome_spec.update({
        "mark": {"type": "bar", "tooltip": True},
        "encoding": {
            "y": {"field": "model", "type": "nominal", "title": None},
            "x": {"field": "requests", "type": "quantitative", "title": "Share of handbook requests",
                  "stack": "normalize", "axis": {"format": ".0%", "values": [0, 0.5, 1]}},
            "color": {"field": "status", "type": "nominal", "title": "Outcome",
                      "scale": {"domain": [STATUS_LABELS[s] for s in STATUS_DOMAIN],
                                "range": STATUS_RANGE}},
            "order": {"field": "order", "type": "quantitative"},
            "tooltip": [{"field": "model"}, {"field": "status"}, {"field": "requests"}],
        },
    })

    guardrail_spec = base_spec(out_of_scope_handling(qs), height=220)
    guardrail_spec.update({
        "mark": {"type": "bar", "tooltip": True},
        "encoding": {
            "y": {"field": "model", "type": "nominal", "title": None},
            "x": {"field": "requests", "type": "quantitative", "title": "Out-of-scope questions",
                  "stack": "zero"},
            "color": {"field": "outcome", "type": "nominal", "title": "Outcome",
                      "scale": {"domain": [label for _, label in OUT_OF_SCOPE_OUTCOMES],
                                "range": ["#c9a227", "#3f7a3f", "#7f93a6", "#b3462f"]},
                      "legend": {"orient": "bottom", "direction": "vertical", "labelLimit": 420}},
            "order": {"field": "order", "type": "quantitative"},
            "tooltip": [{"field": "model"}, {"field": "outcome"}, {"field": "requests"}],
        },
    })

    return {
        "has_data": qs.exists(),
        "requests": qs.count(),
        "users": qs.exclude(user_label="").values("user_label").distinct().count(),
        "by_feature": by_feature,
        "failure_rate": failure_rate(qs),
        "charts": [
            chart("requests-per-day", "Requests per day",
                  "B1. Requests per day, split by feature. Benchmark rows have synthetic dates: "
                  "the measured requests ran in one sitting and were then spread over three weeks "
                  "(with nine made-up user labels) so this chart has a realistic shape. Their "
                  "dates say nothing about real adoption or growth. Live-site rows have real "
                  "dates; pick \"Live site\" under Data source to see them alone.",
                  daily_spec, wide=True),
            chart("requests-by-topic", "Requests by topic",
                  "B2. Handbook rows are labelled with a topic, explain rows with the rule type "
                  "that failed. For benchmark rows this is the mix of our own test questions "
                  "(68 handbook questions and 9 explanations, each run once on each of the four "
                  "setups), not what real users ask. Live-site rows show real use.",
                  topic_spec),
            chart("handbook-outcomes", "How handbook requests end, by setup",
                  "B3. Shares, not counts: every setup answered the same questions, so counts "
                  "would be four identical bars. 'No passage matched' is retrieval declining "
                  "before the model runs; 'Reply failed checks' is our guardrail catching a bad answer.",
                  outcome_spec),
            chart("out-of-scope", "Out-of-scope questions: how each ended",
                  "B3. Pricing, support and legal questions the handbook should not answer, so "
                  "the red \"Answered anyway\" bar is the guardrail failing. In the benchmark "
                  "run 35 of 40 went unanswered (87.5%): 20 never reached a model because "
                  "retrieval found no passage, 13 the model declined, and 2 were replies our "
                  "checks rejected. The 5 answered anyway were all SmolLM2 (2 on the CPU, 3 on "
                  "the GPU).",
                  guardrail_spec),
        ],
    }

"""
Cost section of the A10 dashboard (Connor Slattery).

Questions it answers (docs/a10/analytics_questions.md, C1-C3):
  C1  What does one request cost on each engine and model?
  C2  Which kinds of request use the most tokens?
  C3  How does daily cost change over time, and what would a month cost?

Groq rows cost tokens x Groq's price. Local and Ollama rows cost the
electricity used (see pricing.py): CPU watts for SmolLM2, GPU watts for
Ollama. Hardware and hosting are left out; the caption says so.
"""

from collections import defaultdict

from django.db.models.functions import TruncDate

from .charts import ENGINE_LABELS, base_spec, chart, engine_color


def _per_thousand(total, count):
    return round(float(total) / count * 1000, 4) if count else 0.0


def cost_by_model(rows):
    groups = defaultdict(lambda: {"cost": 0.0, "n": 0})
    for row in rows:
        group = groups[(row["engine"], row["model_name"])]
        group["cost"] += float(row["cost_usd"])
        group["n"] += 1
    return [
        {"engine": engine, "model": model.split("/")[-1], "requests": g["n"],
         "per_1000": _per_thousand(g["cost"], g["n"])}
        for (engine, model), g in sorted(groups.items())
    ]


def tokens_by_query_type(rows):
    groups = defaultdict(lambda: {"prompt": 0, "completion": 0, "n": 0})
    for row in rows:
        label = f'{row["feature"]}: {row["query_type"] or "other"}'
        group = groups[label]
        group["prompt"] += row["prompt_tokens"]
        group["completion"] += row["completion_tokens"]
        group["n"] += 1
    values = []
    for label, g in groups.items():
        values.append({"query_type": label, "part": "Prompt", "order": 0,
                       "tokens": round(g["prompt"] / g["n"], 1)})
        values.append({"query_type": label, "part": "Completion", "order": 1,
                       "tokens": round(g["completion"] / g["n"], 1)})
    return values


def daily_cost(qs):
    totals = defaultdict(float)
    for row in qs.annotate(day=TruncDate("created_at")).values("day", "engine", "cost_usd"):
        totals[(row["day"], row["engine"])] += float(row["cost_usd"])
    return [{"day": day.isoformat(), "engine": engine, "cost": round(cost, 6)}
            for (day, engine), cost in sorted(totals.items())]


def top_cost_drivers(rows, limit=5):
    groups = defaultdict(lambda: {"cost": 0.0, "n": 0, "tokens": 0})
    grand = 0.0
    for row in rows:
        group = groups[(row["feature"], row["query_type"] or "other", row["engine"])]
        cost = float(row["cost_usd"])
        group["cost"] += cost
        group["n"] += 1
        group["tokens"] += row["prompt_tokens"] + row["completion_tokens"]
        grand += cost
    ranked = sorted(groups.items(), key=lambda item: item[1]["cost"], reverse=True)[:limit]
    return [
        {"feature": feature, "query_type": query_type, "engine": ENGINE_LABELS.get(engine, engine),
         "requests": g["n"], "avg_tokens": round(g["tokens"] / g["n"]),
         "total_cost": g["cost"], "share": round(g["cost"] / grand * 100, 1) if grand else 0.0}
        for (feature, query_type, engine), g in ranked
    ]


def cost_context(qs):
    rows = list(qs.values("engine", "model_name", "feature", "query_type",
                          "prompt_tokens", "completion_tokens", "cost_usd", "created_at"))
    count = len(rows)
    total = sum(float(row["cost_usd"]) for row in rows)
    days = {row["created_at"].date() for row in rows}
    per_day = total / len(days) if days else 0.0
    groq = [row for row in rows if row["engine"] == "groq"]
    local = [row for row in rows if row["engine"] != "groq"]

    by_model = cost_by_model(rows)
    model_spec = base_spec(by_model, height=240)
    model_spec.update({
        "mark": {"type": "bar", "tooltip": True, "cornerRadiusEnd": 3},
        "encoding": {
            "y": {"field": "model", "type": "nominal", "title": None, "sort": "-x"},
            "x": {"field": "per_1000", "type": "quantitative", "title": "Dollars per 1,000 requests"},
            "color": engine_color(),
            "tooltip": [{"field": "model"}, {"field": "engine"}, {"field": "requests"},
                        {"field": "per_1000", "title": "$ per 1,000", "format": "$.4f"}],
        },
    })

    token_spec = base_spec(tokens_by_query_type(rows), height=280)
    token_spec.update({
        "mark": {"type": "bar", "tooltip": True},
        "encoding": {
            "y": {"field": "query_type", "type": "nominal", "title": None, "sort": "-x"},
            "x": {"field": "tokens", "type": "quantitative", "title": "Average tokens per request",
                  "stack": "zero"},
            "color": {"field": "part", "type": "nominal", "title": "Tokens",
                      "scale": {"domain": ["Prompt", "Completion"], "range": ["#9bb3cc", "#2f5d8a"]}},
            "order": {"field": "order", "type": "quantitative"},
            "tooltip": [{"field": "query_type", "title": "Request type"}, {"field": "part"},
                        {"field": "tokens", "title": "Avg tokens"}],
        },
    })

    daily_spec = base_spec(daily_cost(qs), height=240)
    daily_spec.update({
        "mark": {"type": "line", "point": True, "tooltip": True},
        "encoding": {
            "x": {"field": "day", "type": "temporal", "title": None},
            "y": {"field": "cost", "type": "quantitative", "title": "Dollars per day",
                  "axis": {"format": "$.4f"}},
            "color": engine_color(),
            "tooltip": [{"field": "day", "type": "temporal"}, {"field": "engine"},
                        {"field": "cost", "format": "$.5f"}],
        },
    })

    return {
        "has_data": count > 0,
        "total_cost": total,
        "per_request": total / count if count else 0.0,
        "groq_per_1000": _per_thousand(sum(float(r["cost_usd"]) for r in groq), len(groq)),
        "local_per_1000": _per_thousand(sum(float(r["cost_usd"]) for r in local), len(local)),
        "projected_month": per_day * 30,
        "drivers": top_cost_drivers(rows),
        "charts": [
            chart("cost-by-model", "Cost per 1,000 requests, by model",
                  "C1. Groq is billed per token. Local (CPU) and Ollama (GPU) rows count only electricity, "
                  "not the hardware or the server, so they look cheaper than they are to host.", model_spec),
            chart("tokens-by-type", "Average tokens per request, by request type",
                  "C2. Prompt tokens are what we send (few-shot examples, retrieved passages); "
                  "completion tokens are what the model writes back.", token_spec),
            chart("cost-per-day", "Cost per day, by engine",
                  "C3. Daily spend follows usage. The projected month above is the average day "
                  "in this range times 30.", daily_spec, wide=True),
        ],
    }

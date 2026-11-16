"""
Performance section of the A10 dashboard. OWNER: Ashok Chacko.

Questions it answers (docs/a10/analytics_design.md, P1-P3):
  P1  How does latency vary across requests: mean, median and 95th percentile?
  P2  Which engine is faster, and for which feature?
  P3  Where does handbook time go, retrieval or generation, and do longer
      inputs answer slower?

Every latency figure here leaves out rows with status "no_passages".
Retrieval rejected those questions before the model ran, so they finish in
about 5 ms. Counted as answers they put a false spike at the left of the
histogram and pull every median towards zero. The captions say so.

Latency spans two orders of magnitude (a Groq reply lands in 0.3 s, the same
question on our CPU takes 23 s), so the histogram uses buckets that double in
width rather than evenly spaced ones, which would put almost every request in
the first bar.
"""

from collections import defaultdict

from .charts import base_spec, chart, engine_color, percentile

# Statuses that never reached the model, so their timings are not answer times.
NOT_GENERATED = ("no_passages",)

# Upper edge of each bucket in milliseconds; each one is twice the last.
BUCKET_EDGES = (250, 500, 1000, 2000, 4000, 8000, 16000, 32000)
BUCKET_LABELS = ("< 0.25s", "0.25-0.5s", "0.5-1s", "1-2s", "2-4s", "4-8s",
                 "8-16s", "16-32s", "> 32s")


# Raw model_name values are long and two of them differ only in punctuation,
# which makes them unreadable as axis labels. These are the four setups the
# A10 benchmark ran; anything else falls back to the raw name plus hardware.
MODEL_LABELS = {
    "HuggingFaceTB/SmolLM2-1.7B-Instruct": "SmolLM2 1.7B (CPU)",
    "smollm2:1.7b": "SmolLM2 1.7B (GPU)",
    "qwen2.5:14b": "Qwen2.5 14B (GPU)",
    "openai/gpt-oss-20b": "gpt-oss 20B (API)",
}


def model_label(engine, model_name):
    """
    A short name a reader can tell apart on an axis.

    Two of our four setups are the same model, SmolLM2-1.7B: one on the CPU
    through transformers, one on a GPU through Ollama. The hardware is what
    separates them, so it goes in the label and the full model id does not -
    long labels eat the width the chart needs.
    """
    if model_name in MODEL_LABELS:
        return MODEL_LABELS[model_name]
    short = (model_name or "").split("/")[-1]
    hardware = {"groq": "API", "ollama": "GPU"}.get(engine, "CPU")
    return f"{short} ({hardware})"


def timed_rows(qs):
    """The rows whose latency is an answer time, as plain dicts."""
    return [
        row
        for row in qs.values("engine", "model_name", "feature", "status",
                             "latency_ms", "retrieval_ms", "input_chars")
        if row["status"] not in NOT_GENERATED
    ]


def bucket_for(latency_ms):
    for index, edge in enumerate(BUCKET_EDGES):
        if latency_ms < edge:
            return index
    return len(BUCKET_EDGES)


def latency_histogram(rows):
    counts = defaultdict(int)
    for row in rows:
        counts[(bucket_for(row["latency_ms"]), row["engine"])] += 1
    return [{"bucket": BUCKET_LABELS[index], "order": index, "engine": engine, "requests": n}
            for (index, engine), n in sorted(counts.items())]


def median_by_engine_feature(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["engine"], row["model_name"], row["feature"])].append(row["latency_ms"])
    return [
        {"model": model_label(engine, model), "engine": engine, "feature": feature,
         "requests": len(values), "median_ms": round(percentile(values, 50), 1)}
        for (engine, model, feature), values in sorted(groups.items())
    ]


def retrieval_vs_generation(rows):
    """Average retrieval and generation time per setup, handbook rows only."""
    groups = defaultdict(lambda: {"retrieval": 0.0, "generation": 0.0, "n": 0})
    for row in rows:
        if row["feature"] != "handbook" or not row["retrieval_ms"]:
            continue
        group = groups[(row["engine"], row["model_name"])]
        group["retrieval"] += row["retrieval_ms"]
        group["generation"] += max(row["latency_ms"] - row["retrieval_ms"], 0.0)
        group["n"] += 1
    values = []
    for (engine, model), group in sorted(groups.items()):
        label = model_label(engine, model)
        values.append({"model": label, "stage": "Retrieval", "order": 0,
                       "ms": round(group["retrieval"] / group["n"], 1)})
        values.append({"model": label, "stage": "Generation", "order": 1,
                       "ms": round(group["generation"] / group["n"], 1)})
    return values


def size_vs_latency(rows):
    """
    Handbook rows only. input_chars is the question's length for a handbook
    row but the whole few-shot prompt's length (~1,700 characters) for an
    explain row, so the two cannot share one "input size" axis.
    """
    return [{"input_chars": row["input_chars"], "latency_ms": round(row["latency_ms"], 1),
             "engine": row["engine"], "model": model_label(row["engine"], row["model_name"])}
            for row in rows if row["feature"] == "handbook" and row["input_chars"]]


def performance_context(qs):
    rows = timed_rows(qs)
    latencies = [row["latency_ms"] for row in rows]
    skipped = qs.filter(status__in=NOT_GENERATED).count()

    histogram_spec = base_spec(latency_histogram(rows), height=260)
    histogram_spec.update({
        "mark": {"type": "bar", "tooltip": True, "cornerRadiusEnd": 3},
        "encoding": {
            "x": {"field": "bucket", "type": "nominal", "title": "Total time per request",
                  "sort": {"field": "order"}, "axis": {"labelAngle": -40}},
            "y": {"field": "requests", "type": "quantitative", "title": "Requests",
                  "stack": "zero"},
            "color": engine_color(),
            "order": {"field": "order", "type": "quantitative"},
            "tooltip": [{"field": "bucket", "title": "Time"}, {"field": "engine"},
                        {"field": "requests"}],
        },
    })

    # A dot plot, not bars: on a log axis there is no zero for a bar to start
    # from, so bar length would encode nothing. The dot sits at the value.
    median_spec = base_spec(median_by_engine_feature(rows), height=280)
    median_spec.update({
        "mark": {"type": "point", "tooltip": True, "filled": True, "size": 160},
        "encoding": {
            "y": {"field": "model", "type": "nominal", "title": None, "sort": "-x"},
            "x": {"field": "median_ms", "type": "quantitative", "title": "Median time (ms, log scale)",
                  "scale": {"type": "log", "nice": False, "padding": 18}},
            "yOffset": {"field": "feature"},
            "color": {"field": "feature", "type": "nominal", "title": "Feature",
                      "scale": {"domain": ["explain", "handbook"],
                                "range": ["#8a6d9c", "#2f5d8a"]}},
            "tooltip": [{"field": "model"}, {"field": "feature"}, {"field": "requests"},
                        {"field": "median_ms", "title": "Median ms"}],
        },
    })

    stage_spec = base_spec(retrieval_vs_generation(rows), height=240)
    stage_spec.update({
        "mark": {"type": "bar", "tooltip": True},
        "encoding": {
            "y": {"field": "model", "type": "nominal", "title": None, "sort": "-x"},
            "x": {"field": "ms", "type": "quantitative", "title": "Average time (ms)",
                  "stack": "zero"},
            "color": {"field": "stage", "type": "nominal", "title": "Stage",
                      "scale": {"domain": ["Retrieval", "Generation"],
                                "range": ["#6b8f3a", "#2f5d8a"]}},
            "order": {"field": "order", "type": "quantitative"},
            "tooltip": [{"field": "model"}, {"field": "stage"}, {"field": "ms", "title": "Avg ms"}],
        },
    })

    scatter_spec = base_spec(size_vs_latency(rows), height=260)
    scatter_spec.update({
        "mark": {"type": "point", "tooltip": True, "filled": True, "opacity": 0.55, "size": 45},
        "encoding": {
            "x": {"field": "input_chars", "type": "quantitative",
                  "title": "Handbook question length (characters)"},
            "y": {"field": "latency_ms", "type": "quantitative",
                  "title": "Total time (ms, log scale)", "scale": {"type": "log"}},
            "color": engine_color(),
            "tooltip": [{"field": "model"}, {"field": "input_chars", "title": "Characters"},
                        {"field": "latency_ms", "title": "ms"}],
        },
    })

    return {
        "has_data": bool(latencies),
        "mean_ms": sum(latencies) / len(latencies) if latencies else 0.0,
        "median_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
        "timed_requests": len(latencies),
        "skipped_requests": skipped,
        "charts": [
            chart("latency-histogram", "How long a request takes",
                  f"P1. Each bucket is twice as wide as the one before it, because the engines are "
                  f"orders of magnitude apart. In the benchmark run the Groq API answers in under a "
                  f"second, Ollama on our GPU mostly in 2-4 s, and SmolLM2 on our CPU mostly in 8 s "
                  f"or more (56 of its 72 timed requests; the fastest took 3.4 s). Nothing lands "
                  f"between 1 and 2 s. {skipped} requests the retriever rejected before the model "
                  f"ran are left out, here and in the numbers above.",
                  histogram_spec, wide=True),
            chart("latency-by-engine", "Median time by setup and feature",
                  "P2. Medians, not means, because a few very slow requests would drag a mean. "
                  "The axis is logarithmic, each gridline ten times the last, because the "
                  "setups are two orders of magnitude apart. Dots rather than bars: a bar on a "
                  "log axis has no zero to start from, so its length would mean nothing. "
                  "SmolLM2 on the CPU splits by reply length (short replies under 13 s, full "
                  "answers over 22 s), so its handbook median sits between two groups. CPU and "
                  "GPU rows also differ in software (transformers vs Ollama), not only hardware.",
                  median_spec),
            chart("retrieval-vs-generation", "Where handbook time goes",
                  "P3. Retrieval is the sliver you can barely see: about 5 ms on three of the "
                  "four setups, against 0.4 s to 19 s of generation. Ollama-SmolLM2's average "
                  "retrieval is 93 ms only because one search took 5.5 s; its median is 5 ms. "
                  "The generator, not the search, is what to optimise.",
                  stage_spec),
            chart("size-vs-latency", "Does a longer handbook question take longer?",
                  "P3. Handbook questions only: an explain request sends a ~1,700-character "
                  "prompt, a different kind of input, so it is left out. Question length barely "
                  "predicts time within a setup; the horizontal bands are the engines. Reply "
                  "length and the setup decide the wait far more than what the user typed.",
                  scatter_spec),
        ],
    }

"""
Performance section of the A10 dashboard. OWNER: Ashok Chacko.

Starter version (Connor) so the page already covers all three categories.
Ashok: replace or extend this. Keep the function name and that it returns a
dict; templates/data_quality/analytics/_performance.html reads it.

Planned questions (docs/a10/analytics_design.md, P1-P3):
  P1  How does latency vary across requests (mean, median, p95, spread)?
  P2  Which engine is faster, and where does the time go (retrieval vs generation)?
  P3  Do longer inputs make answers slower?

Useful fields on each row: engine, model_name, feature, latency_ms,
retrieval_ms (handbook only), input_chars, status, created_at.
Helpers: charts.base_spec, charts.chart, charts.engine_color, charts.percentile.
"""

from .charts import percentile


def performance_context(qs):
    latencies = list(qs.values_list("latency_ms", flat=True))
    return {
        "has_data": bool(latencies),
        "mean_ms": sum(latencies) / len(latencies) if latencies else 0.0,
        "median_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
        "charts": [],  # Ashok: latency histogram, latency by engine, retrieval vs generation
    }

"""
What one AI request costs (A10, Connor Slattery).

Groq bills per token. A local model (SmolLM2 in Django, or a model in Ollama)
has no bill, so its cost here is the electricity the GPU used while it
answered. That leaves out buying the GPU and hosting the server, which the A7
cost tables (multi_model_system/results/) cover; the dashboard says so.
"""

from decimal import Decimal

from django.conf import settings


def groq_cost(prompt_tokens, completion_tokens):
    return (prompt_tokens * settings.ANALYTICS_GROQ_INPUT_PER_M
            + completion_tokens * settings.ANALYTICS_GROQ_OUTPUT_PER_M) / 1_000_000


def local_cost(latency_ms, watts=None):
    if watts is None:
        watts = settings.ANALYTICS_GPU_WATTS
    kwh = watts * (latency_ms / 1000) / 3600 / 1000
    return kwh * settings.ANALYTICS_KWH_PRICE


def request_cost(engine, prompt_tokens, completion_tokens, latency_ms):
    """Dollars for one request, as a Decimal rounded to 8 places."""
    if engine == "groq":
        dollars = groq_cost(prompt_tokens, completion_tokens)
    elif engine == "local":
        # SmolLM2 runs on the CPU (no ROCm on Windows), so use CPU watts.
        cpu_watts = getattr(settings, "ANALYTICS_CPU_WATTS", 150)
        dollars = local_cost(latency_ms, cpu_watts)
    else:
        dollars = local_cost(latency_ms)
    return Decimal(str(round(dollars, 8)))

"""
Explain a violation with AI - A6 Part 2.2 (local model) and 2.3 (Groq API), Tejas Jaggi.

GET shows the violation and two buttons; only a signed-in POST (with its CSRF
token) runs a model, because generating takes seconds of GPU or CPU time (or
an API call) and a GET must stay cheap and safe to repeat. The POST's "engine"
field picks the local model (the default) or Groq. The page is HTML, not a
JSON API, so the project still has exactly one public API endpoint.

The model's answer is advice. Nothing here writes to the database: the recorded
resolution stays whatever a person set (see Violation's docstring). Sample
values are sent to the local model only; they are never sent to Groq, shown on
the page, put in a URL, or logged.
"""

import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from .ai import explain, groq_client, prompts
from .ai.local_model import AIUnavailable
from .models import Violation

logger = logging.getLogger(__name__)

CAUSE_LABELS = {"DATA_ISSUE": "Data issue", "CONTRACT_UPDATED": "Contract out of date"}
ENGINES = ("local", "groq")


def engine_label(engine):
    if engine == "groq":
        return f"Groq API ({settings.GROQ_MODEL})"
    return f"Local model ({settings.AI_LOCAL_MODEL_ID.split('/')[-1]})"


@login_required
@require_http_methods(["GET", "POST"])
def violation_explain(request, pk):
    violation = get_object_or_404(
        Violation.objects.select_related("rule", "rule__contract", "rule__contract__dataset", "run"), pk=pk)
    context = {
        "violation": violation,
        "rule_text": prompts.format_rule(violation.rule),
        "attempted": False,
        "result": None,
        "cause_label": None,
    }
    status = 200
    if request.method == "POST":
        engine = request.POST.get("engine", "local")
        if engine not in ENGINES:
            return HttpResponseBadRequest("Unknown engine.")
        context.update(attempted=True, engine=engine, engine_label=engine_label(engine))
        try:
            run = explain.explain_violation if engine == "local" else groq_client.explain_violation
            result = run(violation)
        except AIUnavailable as exc:
            logger.warning("%s unavailable for violation %s: %s", context["engine_label"], violation.pk, exc)
            context["unavailable"] = True
            status = 503
        else:
            context["result"] = result
            context["cause_label"] = CAUSE_LABELS.get(result.likely_cause) if result else None
    return render(request, "data_quality/violation_explain.html", context, status=status)

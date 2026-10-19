"""
Explain a violation with the local model - A6 Part 2.2, Tejas Jaggi.

GET shows the violation and a button; only a signed-in POST (with its CSRF
token) runs the model, because generating takes seconds of GPU or CPU time and
a GET must stay cheap and safe to repeat. The page is HTML, not a JSON API, so
the project still has exactly one public API endpoint.

The model's answer is advice. Nothing here writes to the database: the recorded
resolution stays whatever a person set (see Violation's docstring). Sample
values are sent to the local model only; they are never shown on the page, put
in a URL, or logged.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from .ai import explain, prompts
from .ai.local_model import AIUnavailable
from .models import Violation

logger = logging.getLogger(__name__)

CAUSE_LABELS = {"DATA_ISSUE": "Data issue", "CONTRACT_UPDATED": "Contract out of date"}


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
        context["attempted"] = True
        try:
            result = explain.explain_violation(violation)
        except AIUnavailable as exc:
            logger.warning("Local AI unavailable for violation %s: %s", violation.pk, exc)
            context["unavailable"] = True
            status = 503
        else:
            context["result"] = result
            context["cause_label"] = CAUSE_LABELS.get(result.likely_cause) if result else None
    return render(request, "data_quality/violation_explain.html", context, status=status)

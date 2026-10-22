"""
Explain a violation with AI - A6 Part 2.2 (local model) and 2.3 (Groq API), Tejas Jaggi.

GET shows the violation and a button for each engine this server has set up
(UX Stage 2: engine_choices); only a signed-in POST (with its CSRF
token) runs a model, because generating takes seconds of GPU or CPU time (or
an API call) and a GET must stay cheap and safe to repeat. The POST's "engine"
field picks the local model (the default) or Groq. The page is HTML, not a
JSON API, so the project still has exactly one public API endpoint.

The model's answer is advice. Nothing here writes to the database: the recorded
resolution stays whatever a person set (see Violation's docstring). Sample
values go to the local model; Groq gets at most 3, and only known status
codes or NOT_NULL blanks (see groq_client.safe_samples). They are never shown on the page, put in a URL, or
logged.
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
# Failures where asking the same engine again can help (UX Stage 2). "off" and
# "rejected" are not: an engine with no key stays that way, and a request Groq
# turned down gets the same answer when it is sent again.
RETRY_KINDS = ("timeout", "unreachable", "busy", "error")
# If a visitor stops a request (Esc, the browser's Stop button), no event tells
# the page, so its script unlocks the buttons after this long: three minutes
# for the local model (the first answer loads it), Groq's own limit plus 10 s.
LOCAL_WAIT_SECONDS = 180


def engine_label(engine):
    if engine == "groq":
        return f"Groq API ({settings.GROQ_MODEL})"
    return f"Local model ({settings.AI_LOCAL_MODEL_ID.split('/')[-1]})"


def engine_choices():
    """
    Each engine as the page shows it, from settings alone (UX Stage 2). Being
    set up (switched on, or a key present) is not a promise that the engine
    will answer, so nothing here contacts Groq or loads the model, and the
    notes say what the engine is, not that it is working.
    """
    local_name = settings.AI_LOCAL_MODEL_ID.split("/")[-1]
    choices = [
        {
            "value": "local",
            "available": settings.AI_LOCAL_ENABLED,
            "button": "Explain with AI",
            "note": f"{local_name}, running on this server. The first answer after the server "
                    "starts can take a minute or more while the model loads.",
            "reason": "The local model is switched off on this server.",
            "wait": "Asking the local model… The first answer after the server starts can take "
                    "a minute or more while the model loads.",
            "wait_seconds": LOCAL_WAIT_SECONDS,
            "retry": "Try the local model again",
            "instead": "Ask the local model instead",
        },
        {
            "value": "groq",
            "available": bool(settings.GROQ_API_KEY),
            "button": "Explain with Groq (external API)",
            "note": f"{settings.GROQ_MODEL}, through the Groq API. DataPact waits up to "
                    f"{settings.GROQ_TIMEOUT_SECONDS} seconds for an answer.",
            "reason": "Groq is not set up on this server.",
            "wait": f"Asking Groq… DataPact waits up to {settings.GROQ_TIMEOUT_SECONDS} seconds for an answer.",
            "wait_seconds": settings.GROQ_TIMEOUT_SECONDS + 10,
            "retry": "Try Groq again",
            "instead": "Ask Groq instead",
        },
    ]
    # Engines this server has set up come first, and the first of them is the
    # main button (on the production default, the local model is off: Groq).
    choices.sort(key=lambda choice: not choice["available"])
    for choice in choices:
        choice["primary"] = choice is choices[0] and choice["available"]
    return choices


@login_required
@require_http_methods(["GET", "POST"])
def violation_explain(request, pk):
    violation = get_object_or_404(
        Violation.objects.select_related("rule", "rule__contract", "rule__contract__dataset", "run"), pk=pk)
    engines = engine_choices()
    context = {
        "violation": violation,
        "rule_text": prompts.format_rule(violation.rule),
        "attempted": False,
        "result": None,
        "cause_label": None,
        "engines": engines,
        "any_engine": any(choice["available"] for choice in engines),
        "groq_available": bool(settings.GROQ_API_KEY),
        "groq_timeout": settings.GROQ_TIMEOUT_SECONDS,
    }
    status = 200
    if request.method == "POST":
        engine = request.POST.get("engine", "local")
        if engine not in ENGINES:
            return HttpResponseBadRequest("Unknown engine.")
        context.update(attempted=True, engine=engine, engine_label=engine_label(engine))
        retry = False
        try:
            run = explain.explain_violation if engine == "local" else groq_client.explain_violation
            result = run(violation)
        except AIUnavailable as exc:
            logger.warning("%s unavailable for violation %s: %s", context["engine_label"], violation.pk, exc)
            context["unavailable"] = True
            context["failure"] = exc.kind
            retry = exc.kind in RETRY_KINDS
            status = 503
        else:
            context["result"] = result
            context["cause_label"] = CAUSE_LABELS.get(result.likely_cause) if result else None
        # What the answer panel offers next: the same engine again (first) only
        # when a retry can help, then any other engine this server has set up.
        # A good answer needs neither.
        if not context["result"]:
            context["follow_ups"] = [
                {**choice, "label": choice["retry"] if choice["value"] == engine else choice["instead"]}
                for choice in sorted(engines, key=lambda choice: choice["value"] != engine)
                if choice["available"] and (choice["value"] != engine or retry)
            ]
    return render(request, "data_quality/violation_explain.html", context, status=status)

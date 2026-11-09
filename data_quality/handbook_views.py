"""
Ask the DataPact handbook - A9, Tejas Jaggi.

GET shows the question box and which models would answer; it never loads a
model (the same rule as ai_views.violation_explain). A signed-in POST with
its CSRF token searches the handbook and asks the local model
(data_quality/ai/handbook.py). The page shows the answer next to the passages
it was built from, with their document, section and similarity score.

Status codes: 400 for a question that fails the form, 503 when the handbook
or the model cannot run here, 200 otherwise (including "nothing relevant
found", which is a real answer about the handbook). The question is never
logged, only its length.
"""

import logging
import re

from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .ai import handbook, retrieval
from .ai.local_model import AIUnavailable

logger = logging.getLogger(__name__)

MAX_QUESTION_CHARS = 500
# ASCII control characters (newlines and tabs too) and Unicode line breaks.
_BREAKS = re.compile(r"[\x00-\x1f\x7f\x85  ]")


class HandbookQuestionForm(forms.Form):
    question = forms.CharField(
        label="Your question",
        max_length=MAX_QUESTION_CHARS,
        error_messages={"required": "Type a question first.",
                        "max_length": f"Keep the question under {MAX_QUESTION_CHARS} characters."},
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "e.g. Can I edit a contract that was already used?"}),
    )

    def clean_question(self):
        question = " ".join(_BREAKS.sub(" ", self.cleaned_data["question"]).split())
        if not question:
            raise forms.ValidationError("Type a question first.")
        if not re.search(r"\w", question):
            raise forms.ValidationError("Ask the question in words.")
        return question


def model_names():
    return {"generator": settings.AI_LOCAL_MODEL_ID.split("/")[-1],
            "embedder": settings.RAG_EMBEDDING_MODEL_ID}


@login_required
@require_http_methods(["GET", "POST"])
def handbook_ask(request):
    status = retrieval.handbook_status()
    context = {"models": model_names(), "status": status, "attempted": False,
               "max_chars": MAX_QUESTION_CHARS}
    if request.method == "GET":
        context["form"] = HandbookQuestionForm()
        return render(request, "data_quality/handbook_ask.html", context)

    form = HandbookQuestionForm(request.POST)
    context["form"] = form
    if not form.is_valid():
        return render(request, "data_quality/handbook_ask.html", context, status=400)

    context["attempted"] = True
    question = form.cleaned_data["question"]
    try:
        if status:
            raise AIUnavailable(f"The handbook is not available: {status}.", kind=status)
        answer = handbook.answer_question(question)
    except AIUnavailable as exc:
        logger.warning("Handbook question (%d chars) not answered: %s", len(question), exc)
        context["failure"] = exc.kind
        return render(request, "data_quality/handbook_ask.html", context, status=503)
    logger.info("Handbook question (%d chars): %s", len(question), answer.status)
    context["answer"] = answer
    return render(request, "data_quality/handbook_ask.html", context)

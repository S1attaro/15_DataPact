"""
A6 Part 2: external AI API feature - Connor Slattery.

GET /api/violations/<id>/explain/ asks Groq to explain one failed rule and
returns the answer as JSON. Login is required, like every API except the one
public endpoint, because each call spends our Groq quota.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .access import api_login_required
from .groq_client import GroqError, explain_violation
from .models import Violation


@api_login_required
@require_GET
def explain_violation_api(request, pk):
    violation = (
        Violation.objects.select_related("rule__contract__dataset", "run")
        .filter(pk=pk)
        .first()
    )
    if violation is None:
        return JsonResponse({"error": "Violation not found."}, status=404)

    try:
        answer = explain_violation(violation)
    except GroqError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status_code)

    return JsonResponse(
        {
            "violation_id": violation.pk,
            "dataset": violation.rule.contract.dataset.name,
            "column": violation.rule.column_name,
            "source": "groq",
            **answer,
        }
    )

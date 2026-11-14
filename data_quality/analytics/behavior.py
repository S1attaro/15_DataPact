"""
User behavior section of the A10 dashboard. OWNER: Ashok Chacko.

Starter version (Connor) so the page already covers all three categories.
Ashok: replace or extend this. Keep the function name and that it returns a
dict; templates/data_quality/analytics/_behavior.html reads it.

Planned questions (docs/a10/analytics_design.md, B1-B3):
  B1  How often are the AI features used, and is use growing?
  B2  Which feature and which topics do users ask about most?
  B3  How often does the handbook fail to answer (not found, no passages)?

Useful fields: feature, query_type, status, user_label, input_chars, created_at.
query_type for handbook rows is a topic from recorder.question_topic();
"out_of_scope" means pricing/support/legal questions.
"""

from django.db.models import Count


def behavior_context(qs):
    by_feature = list(qs.values("feature").annotate(n=Count("id")).order_by("-n"))
    return {
        "has_data": qs.exists(),
        "requests": qs.count(),
        "users": qs.exclude(user_label="").values("user_label").distinct().count(),
        "by_feature": by_feature,
        "charts": [],  # Ashok: requests per day, topics, handbook status, question length
    }

"""
Writing one AIRequestLog row per AI request (A10, Connor Slattery).

The two AI views call record() after every request, answered or not.
Logging must never break the page, so record() catches every error and only
writes a warning to the server log.

Privacy: the user's question and the violation's sample values are never
stored. A question is reduced to its length and a topic label from
question_topic(); a user is stored as "user-<id>", not by name.
"""

import logging
import re

from ..models import AIRequestLog
from .pricing import request_cost

logger = logging.getLogger(__name__)

# Topic labels for handbook questions, checked in order; the first match wins.
# The first group is what the prof flagged: pricing, support and legal
# questions the handbook cannot answer and a static page should.
QUESTION_TOPICS = (
    ("out_of_scope", r"\b(price|pricing|cost|licen[cs]e|seats?|plans?|billing|phone|call|support|refund|terms|"
                     r"legal|discount|subscription)\b"),
    ("exports", r"\b(export|csv|json|reports?|download|format should)\b"),
    ("accounts", r"\b(account|sign ?in|sign ?up|signing in|log ?in|password|google|teammate|anonymous|who can see)\b"),
    ("ai", r"\b(ai|explanation|model|suggestion)\b"),
    ("rules", r"\b(rules?|not null|range|allowed values?|certain values|regex|unique|type match)\b"),
    ("contracts", r"\b(contracts?|version|retire|activate)\b"),
    ("runs", r"\b(runs?|upload|file|scored?|errored|duplicates?)\b"),
    ("violations", r"\b(violations?|samples?|resolution|data issue)\b"),
    ("getting_started", r"\b(dataset|register|dashboard|start|owns?|owner)\b"),
)


def question_topic(question):
    text = (question or "").lower()
    for label, pattern in QUESTION_TOPICS:
        if re.search(pattern, text):
            return label
    return "other"


def estimate_tokens(text):
    """About 4 characters per token for English text. Used only where no tokenizer ran."""
    return max(1, round(len(text or "") / 4)) if text else 0


def messages_text(messages):
    return "\n".join(str(message.get("content", "")) for message in messages or [])


def user_label(user):
    if user is not None and getattr(user, "is_authenticated", False):
        return f"user-{user.pk}"
    return ""


def record(feature, engine, model_name, *, status, latency_ms, user=None, query_type="",
           input_chars=0, prompt_tokens=0, completion_tokens=0, retrieval_ms=0.0,
           source=AIRequestLog.Source.LIVE, created_at=None):
    """Save one row and return it, or None if saving failed (the page carries on)."""
    try:
        fields = dict(
            feature=feature, engine=engine, model_name=model_name[:100],
            user_label=user if isinstance(user, str) else user_label(user),
            query_type=query_type[:40], input_chars=input_chars,
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            retrieval_ms=round(retrieval_ms, 2), latency_ms=round(latency_ms, 2), status=status,
            cost_usd=request_cost(engine, prompt_tokens, completion_tokens, latency_ms),
            source=source,
        )
        if created_at is not None:
            fields["created_at"] = created_at
        return AIRequestLog.objects.create(**fields)
    except Exception:
        logger.warning("Could not save the AI request log", exc_info=True)
        return None

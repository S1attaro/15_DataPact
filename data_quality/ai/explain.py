"""
Turning a Violation into an explanation - A6 Part 2.2, Tejas Jaggi.

parse_reply() applies the notebook's own scoring rule (first "{" to last "}",
json.loads, the three keys, an allowed likely_cause), then two checks the
notebook did not need: each field must be non-empty text, and is capped at
MAX_FIELD_CHARS. Anything else is "no reliable explanation", never raw text.
"""

import json
import re
from dataclasses import dataclass

from . import prompts
from .local_model import AIUnavailable, get_generator

REQUIRED_KEYS = ("explanation", "likely_cause", "suggested_action")
CAUSES = {"DATA_ISSUE", "CONTRACT_UPDATED"}
MAX_FIELD_CHARS = 300


@dataclass(frozen=True)
class Explanation:
    explanation: str
    likely_cause: str
    suggested_action: str


def parse_reply(text):
    """An Explanation if the reply passes the checks, otherwise None."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not all(k in data for k in REQUIRED_KEYS):
        return None
    if not all(isinstance(data[k], str) and data[k].strip() for k in REQUIRED_KEYS):
        return None
    cause = data["likely_cause"].strip().upper()
    if cause not in CAUSES:
        return None
    return Explanation(
        explanation=data["explanation"].strip()[:MAX_FIELD_CHARS],
        likely_cause=cause,
        suggested_action=data["suggested_action"].strip()[:MAX_FIELD_CHARS],
    )


def explain_violation(violation, shots=prompts.DEFAULT_SHOTS):
    """Ask the local model. Returns an Explanation or None; raises AIUnavailable."""
    messages = prompts.build_messages(prompts.violation_to_case(violation), shots)
    try:
        reply = get_generator().generate(messages)
    except AIUnavailable:
        raise  # already the friendly form; do not wrap it twice
    except Exception as exc:  # out of memory, prompt too long, any generation failure
        raise AIUnavailable(f"{type(exc).__name__}: {exc}") from exc
    return parse_reply(reply)

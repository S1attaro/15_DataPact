"""
Explain a violation with Groq's hosted model - A6 Part 2.3 (external API), Tejas Jaggi.

The second AI feature: the same few-shot prompt the benchmark chose, sent to
Groq's OpenAI-compatible chat API instead of the local model. It needs no GPU,
so it also works on a small host where the local model is switched off.

What leaves the server: the dataset, column, rule and failed-row count. Sample
values never do (they are replaced by WITHHELD), because they are raw values
from the user's file. The key comes only from the environment (GROQ_API_KEY in
.env) and is sent only in the Authorization header.

Every failure (no key, timeout, no connection, rate limit, an error status, or
a body that is not the expected JSON) becomes AIUnavailable, which the view
turns into a friendly 503. The reply text goes through the same parse_reply()
as the local model's.
"""

import requests
from django.conf import settings

from . import prompts
from .explain import parse_reply
from .local_model import AIUnavailable

API_URL = "https://api.groq.com/openai/v1/chat/completions"
WITHHELD = '"(not shared with the external API)"'
MAX_COMPLETION_TOKENS = 1024  # gpt-oss counts its reasoning tokens here too


def build_messages(violation, shots=prompts.DEFAULT_SHOTS):
    case = prompts.violation_to_case(violation)
    case["samples"] = WITHHELD
    return prompts.build_messages(case, shots)


def explain_violation(violation, shots=prompts.DEFAULT_SHOTS):
    """An Explanation, None if the reply fails the checks, or AIUnavailable."""
    key = settings.GROQ_API_KEY
    if not key:
        raise AIUnavailable("GROQ_API_KEY is not set")
    model = settings.GROQ_MODEL
    body = {
        "model": model,
        "messages": build_messages(violation, shots),
        "temperature": 0,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "response_format": {"type": "json_object"},
    }
    if model.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"  # other models reject this field with a 400
    try:
        response = requests.post(API_URL, json=body, headers={"Authorization": f"Bearer {key}"},
                                 timeout=settings.GROQ_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise AIUnavailable(f"Groq request failed ({type(exc).__name__})") from None
    if response.status_code == 429:
        raise AIUnavailable("Groq rate limit reached (HTTP 429)")
    if response.status_code != 200:
        raise AIUnavailable(f"Groq returned HTTP {response.status_code}")
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise AIUnavailable("Groq returned an unexpected response") from None
    if not isinstance(content, str):
        raise AIUnavailable("Groq returned an unexpected response")
    return parse_reply(content)

"""
Explain a violation with Groq's hosted model - A6 Part 2.3 (external API), Tejas Jaggi.

The second AI feature: the same few-shot prompt the benchmark chose, sent to
Groq's OpenAI-compatible chat API instead of the local model. It needs no GPU,
so it also works on a small host where the local model is switched off.

What leaves the server: the dataset, column, rule and failed-row count, plus
at most 3 sample values that pass safe_samples() (Connor Slattery). Samples
help the model tell a new status like AUDIT from bad data, but they come from
the user's file, so only short code-like values are shared, and only for rules
where the values are categories or numbers. Anything that could identify a
person (IDs, emails, names, free text) is never sent; when nothing passes, the
model sees WITHHELD instead. The key comes only from the environment
(GROQ_API_KEY in .env) and is sent only in the Authorization header.

Good answers are cached for an hour (Connor Slattery), keyed on the model and
the exact prompt, so clicking again or reloading costs no free-tier tokens.
Failures and replies that fail the checks are not cached.

Every failure (no key, timeout, no connection, rate limit, an error status, or
a body that is not the expected JSON) becomes AIUnavailable, which the view
turns into a friendly 503. The reply text goes through the same parse_reply()
as the local model's.
"""

import hashlib
import json
import re

import requests
from django.conf import settings
from django.core.cache import cache

from . import prompts
from .explain import parse_reply
from .local_model import AIUnavailable

API_URL = "https://api.groq.com/openai/v1/chat/completions"
WITHHELD = '"(not shared with the external API)"'
MAX_COMPLETION_TOKENS = 1024  # gpt-oss counts its reasoning tokens here too
CACHE_SECONDS = 60 * 60

SHARED_SAMPLES = 3
# A short code with no spaces or "@", like AUDIT, FUNK_ACES, 2026-FA or n/a.
CODE_LIKE = re.compile(r"^[A-Za-z0-9_./-]{1,20}$")
MAX_DIGITS = 4  # more digits than this looks like an ID or phone number
CODE_RULES = ("ALLOWED_VALUES", "TYPE_MATCH")  # values are categories or bad types
NUMBER_RULES = ("RANGE", "TYPE_MATCH")  # values are plain numbers
# REGEX and UNIQUE samples are usually IDs or emails, so they are never shared.


def safe_value(value, rule_type):
    """The value if it is safe to send to Groq for this kind of rule, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value if rule_type in NUMBER_RULES else None
    if not isinstance(value, str) or rule_type not in CODE_RULES:
        return None
    if CODE_LIKE.match(value) and sum(ch.isdigit() for ch in value) <= MAX_DIGITS:
        return value
    return None


def safe_samples(violation):
    """Up to SHARED_SAMPLES safe values as JSON text, or WITHHELD if none pass."""
    rule_type = violation.rule.rule_type
    samples = violation.sample_values if isinstance(violation.sample_values, list) else []
    kept = []
    for sample in samples:
        if isinstance(sample, dict):
            if "value" not in sample:
                continue
            sample = sample["value"]
        if sample is None:
            if rule_type == "NOT_NULL":
                kept.append(None)  # a missing value says nothing about anyone
        else:
            value = safe_value(sample, rule_type)
            if value is not None:
                kept.append(value)
        if len(kept) == SHARED_SAMPLES:
            break
    return json.dumps(kept) if kept else WITHHELD


def build_messages(violation, shots=prompts.DEFAULT_SHOTS):
    case = prompts.violation_to_case(violation)
    case["samples"] = safe_samples(violation)
    return prompts.build_messages(case, shots)


def cache_key(model, messages):
    """Same model and same prompt means the same answer, so they share one key."""
    digest = hashlib.sha256(json.dumps([model, messages], sort_keys=True).encode()).hexdigest()
    return f"groq-explain:{digest}"


def explain_violation(violation, shots=prompts.DEFAULT_SHOTS):
    """An Explanation, None if the reply fails the checks, or AIUnavailable."""
    key = settings.GROQ_API_KEY
    if not key:
        raise AIUnavailable("GROQ_API_KEY is not set")
    model = settings.GROQ_MODEL
    messages = build_messages(violation, shots)
    key_for_cache = cache_key(model, messages)
    cached = cache.get(key_for_cache)
    if cached is not None:
        return cached
    body = {
        "model": model,
        "messages": messages,
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
    result = parse_reply(content)
    if result is not None:
        cache.set(key_for_cache, result, CACHE_SECONDS)
    return result

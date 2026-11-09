"""
Answering a question from the DataPact handbook - A9, Tejas Jaggi.

question -> retrieval.get_provider().search() -> passages that score at least
settings.RAG_MIN_SCORE -> the A8 prompt (handbook_a8.build_messages) ->
the A6 local model (local_model.get_generator, SmolLM2-1.7B) -> check_reply().

If no passage is close enough, the model is not asked at all, so it cannot
write an answer the handbook does not support. The page shows the passages
that were actually sent to the model, never sources the model names itself.

Citations. The A8 prompt (SYSTEM_PROMPT, kept word for word so the A8 drift
test still holds) does not ask for citations, so A9 adds its own rules,
CITATION_INSTRUCTION, after it here, through build_messages' system_prompt
argument; the passages and question are sent exactly as A8 sends them.
check_reply() then only shows a reply that cites at least one passage it was
given, as [1] or [1, 2], cites no other number, names no other .md file, and
states no number (a price, a count, a limit) that none of those passages
contains. The number rule came from the A9 real-KB run (9 Nov 2026), where the
model answered an out-of-scope price question with an invented "$100 per seat"
and a valid citation.

Limitation: this checks that each citation points at a passage the model was
actually shown. It does not check that the passage says what the sentence
claims (that would need entailment checking, which A9 does not do), and a
reply can cite [1] once and still add an unsupported sentence. The number rule
catches only invented numbers, not invented words. That is why the page lists
the passages under every answer and asks the reader to check them.

provider and generator can be passed in (the tests do); the page uses the
shared ones.
"""

import re
import time
from dataclasses import dataclass

from django.conf import settings

from . import handbook_a8, local_model, retrieval
from .local_model import AIUnavailable

MAX_ANSWER_CHARS = 1500
NOT_FOUND = "could not find that in the documents"  # the sentence the A8 prompt asks for
# A9's addition to the A8 system prompt (see the module docstring). CITATION_INSTRUCTION
# is "Variant A" from the A9 Phase 3 prompt experiment (7 questions on the sample
# knowledge base): a candidate, to be checked again on the real knowledge base.
# BASELINE_CITATION_INSTRUCTION is the Phase 2 sentence it replaced; to go back,
# set CITATION_INSTRUCTION = BASELINE_CITATION_INSTRUCTION.
BASELINE_CITATION_INSTRUCTION = "After each fact, cite the number of the context passage it comes from, like [1]."
CITATION_INSTRUCTION = (
    "Rules: Use only the numbered context passages. "
    "Put the number of the passage that supports each sentence right after that sentence, like [1]. "
    "Do not add assumptions, general knowledge or details that are not in the passages. "
    "If the passages do not establish the answer, say only: I could not find that in the documents. "
    "Never invent passage numbers or document names."
)
SYSTEM_PROMPT = handbook_a8.SYSTEM_PROMPT + " " + CITATION_INSTRUCTION
_CITATION = re.compile(r"\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]")  # [1] or [1, 2]
_DOC_NAME = re.compile(r"\b[\w-]+\.md\b", re.IGNORECASE)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")  # 24, 1000, 3.5, 5,000 (citations are removed first)
_CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")  # every ASCII control character except \n


@dataclass(frozen=True)
class HandbookAnswer:
    status: str        # "answered", "not_found", "no_passages" or "invalid"
    text: str          # the checked answer; empty unless answered
    passages: tuple    # the Passages the model was given (empty for no_passages)
    search_ms: float = 0.0
    generate_s: float = 0.0


def check_reply(reply, passages):
    """(status, text) for a model reply, given the passages it was shown."""
    text = _CONTROL.sub("", reply or "").strip()[:MAX_ANSWER_CHARS]
    if not text:
        return "invalid", ""
    if NOT_FOUND in text.lower():
        return "not_found", ""
    cited = {int(n) for group in _CITATION.findall(text) for n in group.split(",")}
    if not cited or not cited <= {p.rank for p in passages}:
        return "invalid", ""  # no citation, or one to a passage the model was not given
    docs = {p.doc.lower() for p in passages}
    if any(name.lower() not in docs for name in _DOC_NAME.findall(text)):
        return "invalid", ""
    if _unsupported_number(text, passages):
        return "invalid", ""  # e.g. a price or count that no passage states (A9 real-KB run, q13)
    return "answered", text


def _unsupported_number(text, passages):
    """True if the reply, outside its [n] citations, states a number no passage contains."""
    source = " ".join(p.text for p in passages)
    for number in _NUMBER.findall(_CITATION.sub(" ", text)):
        if not re.search(rf"(?<![\d.,]){re.escape(number)}(?!\d|[.,]\d)", source):
            return True
    return False


def answer_question(question, provider=None, generator=None):
    """A HandbookAnswer. Raises AIUnavailable when retrieval or the model cannot run."""
    provider = provider or retrieval.get_provider()
    started = time.perf_counter()
    try:
        hits = provider.search(question, settings.RAG_TOP_K)
    except AIUnavailable:
        raise
    except Exception as exc:  # the embedding model failing mid-search: out of memory, etc.
        raise AIUnavailable(f"{type(exc).__name__}: {exc}", kind="retrieval_error") from exc
    search_ms = (time.perf_counter() - started) * 1000

    passages = tuple(p for p in hits if p.score >= settings.RAG_MIN_SCORE)
    if not passages:
        return HandbookAnswer("no_passages", "", (), search_ms=search_ms)

    messages = handbook_a8.build_messages(question, [{"rank": p.rank, "text": p.text} for p in passages],
                                          system_prompt=SYSTEM_PROMPT)
    started = time.perf_counter()
    try:
        reply = (generator or local_model.get_generator()).generate(messages)
    except AIUnavailable:
        raise  # already says why (switched off, failed to load)
    except Exception as exc:  # out of memory, prompt too long, any generation failure
        raise AIUnavailable(f"{type(exc).__name__}: {exc}") from exc
    generate_s = time.perf_counter() - started

    status, text = check_reply(reply, passages)
    return HandbookAnswer(status, text, passages, search_ms=search_ms, generate_s=generate_s)

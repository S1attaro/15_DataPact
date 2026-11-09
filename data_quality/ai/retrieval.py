"""
Searching the DataPact handbook - A9, Tejas Jaggi.

The handbook is the A8 knowledge base: Markdown files (# title, ## section,
paragraphs split by blank lines) in settings.RAG_KB_DIR. On first use the
files are chunked with the A8 strategy named in settings.RAG_CHUNKING, every
chunk is embedded with settings.RAG_EMBEDDING_MODEL_ID, and the vectors stay
in one NumPy matrix for the life of the process, as in the A8 notebook's
VectorIndex. A search embeds the question and ranks chunks by cosine
similarity (the vectors are normalized, so a dot product).

The code does not pick an embedding model. RAG_EMBEDDING_MODEL_ID is empty by
default, which means the handbook is "not configured" and the page says so
until .env names a model; nothing stands in for the real one. A8 recommends
sentence-transformers/all-mpnet-base-v2. A9 was evaluated with
sentence-transformers/all-MiniLM-L6-v2 as a fallback, because mpnet was not
downloaded on the test laptop. The evaluated configuration and this
limitation are in README_AI.md (A9 section).

As in local_model.py: nothing loads when Django starts or on a GET, the
sentence-transformers import happens inside the loader, the built index is
shared by every request, and a failed load waits LOAD_RETRY_SECONDS before
trying again. The embedder runs on settings.RAG_EMBEDDING_DEVICE ("cpu" by
default) so the GPU stays free for SmolLM2.

Edit the knowledge base and restart the server to search the new text.
"""

import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from django.conf import settings

from . import handbook_a8
from .local_model import LOAD_RETRY_SECONDS, AIUnavailable

_WORD = re.compile(r"\w")


@dataclass(frozen=True)
class Passage:
    """One retrieved chunk and where it came from. Field names follow the A8 notebook's hits."""

    doc: str      # file name in the knowledge base, e.g. "rule_types.md"
    title: str    # the document's "# " title
    section: str  # the "## " section the chunk sits in
    text: str     # the chunk text, as the model reads it
    score: float  # cosine similarity to the question
    rank: int     # 1 = best match


class SentenceTransformerEmbedder:
    """The notebook's RealEmbedder: normalized vectors, the model's own query prefix."""

    def __init__(self, model_id, query_prefix, device):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_id, device=device)
        self.query_prefix = query_prefix

    def encode_chunks(self, texts):
        return self.model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)

    def encode_query(self, query):
        return self.model.encode([self.query_prefix + query], normalize_embeddings=True,
                                 show_progress_bar=False)[0]


class HandbookIndex:
    def __init__(self, embedder, chunks, titles):
        self.embedder = embedder
        self.chunks = chunks
        self.titles = titles  # doc file name -> document title
        self.matrix = np.asarray(embedder.encode_chunks([c["embed_text"] for c in chunks]))
        self._lock = threading.Lock()

    def search(self, query, top_k):
        with self._lock:
            vector = np.asarray(self.embedder.encode_query(query))
        scores = self.matrix @ vector
        top = np.argsort(-scores)[:top_k]
        return [
            Passage(doc=self.chunks[i]["doc"], title=self.titles.get(self.chunks[i]["doc"], self.chunks[i]["doc"]),
                    section=self.chunks[i]["section"], text=self.chunks[i]["text"],
                    score=float(scores[i]), rank=rank)
            for rank, i in enumerate(top, start=1)
        ]


def load_chunks(kb_dir, strategy):
    """
    (chunks, titles) for the knowledge base, chunked the A8 way, keeping only
    chunks that hold a word. No model is needed, so get_provider() can tell
    that the files hold nothing to search (empty, blank or only headings)
    before it loads one.
    """
    paragraphs = handbook_a8.load_paragraphs(kb_dir)
    chunks = [c for c in handbook_a8.CHUNKERS[strategy](paragraphs) if _WORD.search(c["text"])]
    titles = {p["doc"]: p["title"] for p in paragraphs}
    return chunks, titles


def build_index(kb_dir, embedder, strategy):
    return HandbookIndex(embedder, *load_chunks(kb_dir, strategy))


def query_prefix_for(model_id):
    """RAG_QUERY_PREFIX if set; otherwise the prefix A8 used for this model (bge needs one)."""
    if settings.RAG_QUERY_PREFIX is not None:
        return settings.RAG_QUERY_PREFIX
    for config in handbook_a8.EMBEDDING_MODELS.values():
        if config["id"] == model_id:
            return config["query_prefix"]
    return ""


def handbook_status():
    """
    None when this server is set up to answer, otherwise why not: "off" (the
    local model is switched off), "not_configured" (no embedding model, or an
    unknown chunking strategy) or "missing_kb" (no .md files to search).
    From settings and a folder listing alone: it never loads a model.
    """
    if not settings.AI_LOCAL_ENABLED:
        return "off"
    if not settings.RAG_EMBEDDING_MODEL_ID or settings.RAG_CHUNKING not in handbook_a8.CHUNKERS:
        return "not_configured"
    kb_dir = Path(settings.RAG_KB_DIR)
    if not kb_dir.is_dir() or not any(kb_dir.glob("*.md")):
        return "missing_kb"
    return None


_provider = None
_failure = None  # (time.monotonic(), message) of the last failed build
_build_lock = threading.Lock()


def get_provider():
    """
    The shared handbook index, built on first use. Raises AIUnavailable instead
    of crashing: kind is the handbook_status() reason, "empty_kb" when the
    documents hold no text to search (found out before any model loads), or
    "retrieval_error" when the embedding model or the files fail to load.
    """
    global _provider, _failure
    status = handbook_status()
    if status:
        raise AIUnavailable(f"The handbook is not available: {status}.", kind=status)
    if _provider is None:
        with _build_lock:
            if _provider is None:
                if _failure and time.monotonic() - _failure[0] < LOAD_RETRY_SECONDS:
                    raise AIUnavailable(_failure[1], kind="retrieval_error")
                model_id = settings.RAG_EMBEDDING_MODEL_ID
                try:
                    chunks, titles = load_chunks(settings.RAG_KB_DIR, settings.RAG_CHUNKING)
                    if chunks:  # otherwise there is nothing to embed, so no model is loaded
                        embedder = SentenceTransformerEmbedder(
                            model_id, query_prefix_for(model_id), settings.RAG_EMBEDDING_DEVICE)
                        _provider = HandbookIndex(embedder, chunks, titles)
                except Exception as exc:
                    # Missing library or weights, out of memory, a file that will not read.
                    _failure = (time.monotonic(), f"{type(exc).__name__}: {exc}")
                    raise AIUnavailable(_failure[1], kind="retrieval_error") from exc
                if _provider is None:
                    # Not cached and not backed off: reading the files is cheap and loads no model.
                    raise AIUnavailable("The handbook documents hold no text to search.", kind="empty_kb")
                _failure = None
    return _provider


def reset_for_tests():
    global _provider, _failure
    _provider = None
    _failure = None

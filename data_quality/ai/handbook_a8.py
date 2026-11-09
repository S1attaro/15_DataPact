"""
What the handbook Q&A reuses from A8 - A9, Tejas Jaggi.

Everything below the line is copied verbatim from the A8 notebook,
rag_system/rag_system.ipynb (Connor Slattery): how the knowledge base is read
into paragraphs, the three chunking strategies, the three embedding models
with their query prefixes, and the RAG prompt. Django never imports or runs
the notebook; it runs this copy, so the app chunks and prompts exactly the
way A8 measured. CopiedFromA8Tests (tests_handbook.py) fails if the two drift
apart, so change them only together with the notebook.

Note: make_chunk() keeps the document file name and section but not the
document title, so retrieval.py looks the title up from the paragraphs.
"""

import re
from pathlib import Path

# --- Copied from rag_system/rag_system.ipynb (do not edit here alone) ---


def load_paragraphs(kb_dir):
    paragraphs = []
    for path in sorted(Path(kb_dir).glob("*.md")):
        title = path.stem
        section = "General"
        for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")):
            block = block.strip()
            if not block:
                continue
            if block.startswith("# "):
                title = block[2:].strip()
            elif block.startswith("## "):
                section = block[3:].strip()
            else:
                text = " ".join(block.split())
                paragraphs.append({"doc": path.name, "title": title, "section": section,
                                   "text": text, "words": len(text.split())})
    return paragraphs


FIXED_WORDS = 120
HYBRID_MIN_WORDS = 60
HYBRID_MAX_WORDS = 200
HYBRID_SPLIT_WORDS = 150


def split_sentences(text):
    protected = re.sub(r"\b(e\.g|i\.e|etc|vs)\.", lambda m: m.group(0).replace(".", "<dot>"), text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", protected)
    return [p.replace("<dot>", ".").strip() for p in parts if p.strip()]


def group_by_section(paragraphs):
    sections = {}
    for p in paragraphs:
        sections.setdefault((p["doc"], p["title"], p["section"]), []).append(p["text"])
    return sections


def pack_sentences(sentences, limit):
    groups, current, count = [], [], 0
    for sentence in sentences:
        size = len(sentence.split())
        if current and count + size > limit:
            groups.append(" ".join(current))
            current, count = [], 0
        current.append(sentence)
        count += size
    if current:
        groups.append(" ".join(current))
    return groups


def make_chunk(key, text, embed_text=None):
    doc, title, section = key
    return {"doc": doc, "section": section, "text": text, "embed_text": embed_text or text,
            "words": len(text.split())}


def fixed_chunks(paragraphs):
    chunks = []
    for key, texts in group_by_section(paragraphs).items():
        sentences = [s for text in texts for s in split_sentences(text)]
        chunks += [make_chunk(key, text) for text in pack_sentences(sentences, FIXED_WORDS)]
    return chunks


def overlap_chunks(paragraphs):
    chunks = []
    for key, texts in group_by_section(paragraphs).items():
        if len(texts) == 1:
            chunks.append(make_chunk(key, texts[0]))
        for first, second in zip(texts, texts[1:]):
            chunks.append(make_chunk(key, first + " " + second))
    return chunks


def hybrid_chunks(paragraphs):
    chunks = []
    for key, texts in group_by_section(paragraphs).items():
        doc, title, section = key
        merged = []
        for text in texts:
            if merged and len(merged[-1].split()) < HYBRID_MIN_WORDS:
                merged[-1] += " " + text
            else:
                merged.append(text)
        if len(merged) > 1 and len(merged[-1].split()) < HYBRID_MIN_WORDS:
            last = merged.pop()
            merged[-1] += " " + last

        for text in merged:
            pieces = [text]
            if len(text.split()) > HYBRID_MAX_WORDS:
                pieces = pack_sentences(split_sentences(text), HYBRID_SPLIT_WORDS)
            for piece in pieces:
                chunks.append(make_chunk(key, piece, f"{title} - {section}: {piece}"))
    return chunks


CHUNKERS = {"fixed": fixed_chunks, "overlap": overlap_chunks, "hybrid": hybrid_chunks}

EMBEDDING_MODELS = {
    "small": {"id": "sentence-transformers/all-MiniLM-L6-v2", "dim": 384, "query_prefix": ""},
    "medium": {"id": "sentence-transformers/all-mpnet-base-v2", "dim": 768, "query_prefix": ""},
    "large": {"id": "BAAI/bge-large-en-v1.5", "dim": 1024,
              "query_prefix": "Represent this sentence for searching relevant passages: "},
}

SYSTEM_PROMPT = (
    "You answer questions about DataPact, a data quality tool. "
    "Use only the context below. "
    "If the context does not contain the answer, say: I could not find that in the documents."
)


def build_messages(query, hits, system_prompt=SYSTEM_PROMPT):
    context = "\n\n".join(f"[{hit['rank']}] {hit['text']}" for hit in hits)
    return [{"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}]

# --- End of copied section ---

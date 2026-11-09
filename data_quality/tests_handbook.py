"""
A9 - the DataPact handbook Q&A page (retrieval + the A6 local model).
Author: Tejas Jaggi.

No test here downloads or loads a model. Retrieval runs on a word-hashing fake
embedder over a temporary knowledge base, and the page runs on a fake
provider and a fake generator, so these tests prove the Django flow and its
checks, not that the real models answer well (that is the A9 evaluation).

The chunking, prompt and embedding-model table are copied from the A8
notebook, rag_system/rag_system.ipynb (Connor Slattery). CopiedFromA8Tests
fails if the copy and the notebook drift apart, so Django keeps doing what
A8 measured.
"""

import ast
import inspect
import json
import re
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from data_quality import handbook_views
from data_quality.ai import handbook, handbook_a8, local_model, retrieval
from data_quality.ai.local_model import AIUnavailable
from data_quality.ai.retrieval import Passage

NOTEBOOK = Path(settings.BASE_DIR) / "rag_system" / "rag_system.ipynb"

COPIED_NAMES = (
    "FIXED_WORDS", "HYBRID_MIN_WORDS", "HYBRID_MAX_WORDS", "HYBRID_SPLIT_WORDS",
    "load_paragraphs", "split_sentences", "group_by_section", "group_by_doc", "pack_sentences", "make_chunk",
    "fixed_chunks", "overlap_chunks", "hybrid_chunks", "CHUNKERS",
    "EMBEDDING_MODELS", "SYSTEM_PROMPT", "build_messages",
)

KB_FILES = {
    "rule_types.md": (
        "# DataPact rule types\n\n"
        "## Not null\n\n"
        "A NOT_NULL rule says a column must have a value in every row. A blank cell counts as a "
        "failure. The owner should ask the source team whether the blanks are expected.\n\n"
        "## Unique\n\n"
        "A UNIQUE rule says no value may appear twice in a column. Duplicates usually mean the "
        "file was exported twice or two batches were joined.\n"
    ),
    "validation_process.md": (
        "# How validation works\n\n"
        "## Contracts and versions\n\n"
        "A contract that was already used is never edited. Save the change as a new version so "
        "old validation runs still point at the rules they were checked against.\n"
    ),
}


def write_kb(directory, files=KB_FILES):
    for name, text in files.items():
        (Path(directory) / name).write_text(text, encoding="utf-8")


class HashingEmbedder:
    """Word-hashing vectors, like the notebook's dry-run embedder: shared words score higher."""

    dim = 64

    def __init__(self):
        self.queries = []

    def _vector(self, text):
        vector = np.zeros(self.dim)
        for word in re.findall(r"[a-z]+", text.lower()):
            vector[sum(ord(c) * 31 ** i for i, c in enumerate(word)) % self.dim] += 1
        return vector / (np.linalg.norm(vector) or 1)

    def encode_chunks(self, texts):
        return np.array([self._vector(t) for t in texts])

    def encode_query(self, query):
        self.queries.append(query)
        return self._vector(query)


def passage(rank, score=0.8, doc="rule_types.md", section="Not null", text=None):
    return Passage(doc=doc, title="DataPact rule types", section=section,
                   text=text or f"Passage {rank} text about blank values.", score=score, rank=rank)


class FakeProvider:
    def __init__(self, passages=None, error=None):
        self.passages = [passage(1), passage(2, 0.6, section="Unique")] if passages is None else passages
        self.error = error
        self.calls = []

    def search(self, query, top_k):
        self.calls.append((query, top_k))
        if self.error:
            raise self.error
        return self.passages[:top_k]


class FakeGenerator:
    def __init__(self, reply="Ask the source team whether the blanks are expected [1].", error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    def generate(self, messages):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return self.reply


def temp_kb(test, files):
    """A knowledge base folder holding files, removed after the test."""
    directory = Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, directory, ignore_errors=True)
    write_kb(directory, files)
    return directory


class TempKBMixin:
    """A knowledge base folder that exists for the whole test class."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.kb_dir = Path(tempfile.mkdtemp())
        write_kb(cls.kb_dir)
        cls.addClassCleanup(shutil.rmtree, cls.kb_dir, ignore_errors=True)


# --- Django runs the chunking and prompt that A8 measured ------------------------------------

def top_level_nodes(source, names):
    found = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            found[node.name] = ast.dump(node)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and getattr(node.targets[0], "id", None) in names:
            found[node.targets[0].id] = ast.dump(node)
    return found


class CopiedFromA8Tests(SimpleTestCase):
    def setUp(self):
        cells = json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]
        self.notebook = {}
        self.notebook_source = ""
        for cell in cells:
            if cell["cell_type"] == "code":
                source = "".join(cell["source"])
                self.notebook_source += source + "\n"
                self.notebook.update(top_level_nodes(source, COPIED_NAMES))

    def test_every_copied_name_still_exists_in_the_notebook(self):
        self.assertEqual(sorted(self.notebook), sorted(COPIED_NAMES))

    def test_the_copy_matches_the_notebook_exactly(self):
        ours = top_level_nodes(inspect.getsource(handbook_a8), COPIED_NAMES)
        for name in COPIED_NAMES:
            with self.subTest(name=name):
                self.assertEqual(ours.get(name), self.notebook[name])

    def test_the_app_generates_with_the_model_and_token_limit_a8_used(self):
        self.assertRegex(self.notebook_source, r'GENERATION_MODEL = "HuggingFaceTB/SmolLM2-1\.7B-Instruct"')
        self.assertIn(f"MAX_NEW_TOKENS = {settings.AI_MAX_NEW_TOKENS}", self.notebook_source)

    def test_the_default_top_k_is_the_one_a8_used(self):
        self.assertIn(f"TOP_K = {settings.RAG_TOP_K}", self.notebook_source)


# --- Retrieval over a real knowledge-base folder, with a fake embedder ----------------------

class IndexTests(TempKBMixin, SimpleTestCase):
    def setUp(self):
        self.embedder = HashingEmbedder()
        self.index = retrieval.build_index(self.kb_dir, self.embedder, "hybrid")

    def test_search_returns_ranked_passages_with_their_source(self):
        hits = self.index.search("What should I do about blank values in a not null column?", 2)
        self.assertEqual([h.rank for h in hits], [1, 2])
        self.assertGreaterEqual(hits[0].score, hits[1].score)
        top = hits[0]
        self.assertEqual((top.doc, top.title, top.section), ("rule_types.md", "DataPact rule types", "Not null"))
        self.assertIn("blank cell counts as a failure", top.text)

    def test_the_model_reads_the_plain_text_not_the_embedding_prefix(self):
        top = self.index.search("blank values", 1)[0]
        self.assertFalse(top.text.startswith("DataPact rule types - Not null:"))

    def test_top_k_limits_the_number_of_passages(self):
        self.assertEqual(len(self.index.search("contract version", 1)), 1)
        self.assertEqual(len(self.index.search("contract version", 10)), 3)  # only 3 chunks exist

    def test_every_strategy_from_a8_builds(self):
        for strategy in ("fixed", "overlap", "hybrid"):
            with self.subTest(strategy=strategy):
                self.assertTrue(retrieval.build_index(self.kb_dir, HashingEmbedder(), strategy).search("rule", 1))


class QueryPrefixTests(SimpleTestCase):
    @override_settings(RAG_QUERY_PREFIX=None)
    def test_a8_models_get_the_prefix_a8_gave_them(self):
        self.assertEqual(retrieval.query_prefix_for("BAAI/bge-large-en-v1.5"),
                         "Represent this sentence for searching relevant passages: ")
        self.assertEqual(retrieval.query_prefix_for("sentence-transformers/all-MiniLM-L6-v2"), "")

    @override_settings(RAG_QUERY_PREFIX=None)
    def test_an_unknown_model_gets_no_prefix(self):
        self.assertEqual(retrieval.query_prefix_for("someone/other-model"), "")

    @override_settings(RAG_QUERY_PREFIX="query: ")
    def test_the_setting_overrides_the_table(self):
        self.assertEqual(retrieval.query_prefix_for("BAAI/bge-large-en-v1.5"), "query: ")


@override_settings(AI_LOCAL_ENABLED=True, RAG_EMBEDDING_MODEL_ID="test/embedder", RAG_CHUNKING="hybrid")
class ProviderTests(TempKBMixin, SimpleTestCase):
    def setUp(self):
        retrieval.reset_for_tests()
        self.addCleanup(retrieval.reset_for_tests)

    def status(self, **overrides):
        with override_settings(**{"RAG_KB_DIR": self.kb_dir, **overrides}):
            return retrieval.handbook_status()

    def test_a_configured_server_is_ready(self):
        self.assertIsNone(self.status())

    def test_no_embedding_model_means_not_configured(self):
        self.assertEqual(self.status(RAG_EMBEDDING_MODEL_ID=""), "not_configured")

    def test_an_unknown_chunking_strategy_means_not_configured(self):
        self.assertEqual(self.status(RAG_CHUNKING="sentences"), "not_configured")

    def test_the_local_model_switched_off_means_off(self):
        self.assertEqual(self.status(AI_LOCAL_ENABLED=False), "off")

    def test_a_missing_folder_means_missing_kb(self):
        self.assertEqual(self.status(RAG_KB_DIR=self.kb_dir / "nowhere"), "missing_kb")

    def test_a_folder_without_documents_means_missing_kb(self):
        empty = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        self.assertEqual(self.status(RAG_KB_DIR=empty), "missing_kb")

    def build(self, kb_dir):
        """get_provider() on kb_dir with the embedder class watched: (provider or AIUnavailable, embedder mock)."""
        with override_settings(RAG_KB_DIR=kb_dir), \
                patch.object(retrieval, "SentenceTransformerEmbedder", side_effect=lambda *a, **k: HashingEmbedder()) as cls:
            try:
                return retrieval.get_provider(), cls
            except AIUnavailable as exc:
                return exc, cls

    def test_a_missing_or_empty_folder_loads_no_model(self):
        for name, kb_dir in (("missing folder", self.kb_dir / "nowhere"), ("empty folder", temp_kb(self, {}))):
            with self.subTest(name):
                retrieval.reset_for_tests()
                error, cls = self.build(kb_dir)
                self.assertEqual(getattr(error, "kind", None), "missing_kb")
                cls.assert_not_called()

    def test_documents_with_no_text_are_an_empty_knowledge_base(self):
        cases = {
            "an empty file": {"empty.md": ""},
            "whitespace only": {"blank.md": "  \n\n\t\n"},
            "headings only": {"outline.md": "# DataPact rule types\n\n## Not null\n\n## Unique\n"},
            "no words": {"rules.md": "# Rules\n\n---\n\n***\n"},
        }
        for name, files in cases.items():
            with self.subTest(name):
                retrieval.reset_for_tests()
                error, cls = self.build(temp_kb(self, files))
                self.assertEqual(getattr(error, "kind", None), "empty_kb")
                cls.assert_not_called()  # found out before any model loads

    def test_one_usable_document_is_enough(self):
        kb_dir = temp_kb(self, {"empty.md": "", "outline.md": "# Title\n\n## Section\n",
                                "rule_types.md": KB_FILES["rule_types.md"]})
        provider, cls = self.build(kb_dir)
        self.assertEqual({c["doc"] for c in provider.chunks}, {"rule_types.md"})
        self.assertEqual(cls.call_count, 1)

    def test_a_valid_knowledge_base_builds_a_searchable_index(self):
        provider, cls = self.build(self.kb_dir)
        hits = provider.search("Can a used contract be edited?", 1)
        self.assertEqual((hits[0].doc, hits[0].section), ("validation_process.md", "Contracts and versions"))

    def test_an_empty_knowledge_base_is_checked_again_next_time(self):
        # Nothing is cached for an empty knowledge base, so no model is loaded on a later click either.
        kb_dir = temp_kb(self, {"empty.md": ""})
        for _ in range(2):
            error, cls = self.build(kb_dir)
            self.assertEqual(getattr(error, "kind", None), "empty_kb")
            cls.assert_not_called()

    def test_checking_the_status_never_loads_a_model(self):
        with patch.object(retrieval, "SentenceTransformerEmbedder") as cls:
            self.status()
        cls.assert_not_called()

    def test_the_provider_is_built_once_and_reused(self):
        with override_settings(RAG_KB_DIR=self.kb_dir), \
                patch.object(retrieval, "SentenceTransformerEmbedder", side_effect=lambda *a, **k: HashingEmbedder()) as cls:
            first = retrieval.get_provider()
            second = retrieval.get_provider()
        self.assertIs(first, second)
        self.assertEqual(cls.call_count, 1)

    @override_settings(RAG_QUERY_PREFIX=None, RAG_EMBEDDING_DEVICE="cpu")
    def test_the_embedder_gets_the_configured_model_prefix_and_device(self):
        with override_settings(RAG_KB_DIR=self.kb_dir, RAG_EMBEDDING_MODEL_ID="BAAI/bge-large-en-v1.5"), \
                patch.object(retrieval, "SentenceTransformerEmbedder", side_effect=lambda *a, **k: HashingEmbedder()) as cls:
            retrieval.get_provider()
        cls.assert_called_once_with("BAAI/bge-large-en-v1.5",
                                    "Represent this sentence for searching relevant passages: ", "cpu")

    def test_a_server_that_is_not_ready_raises_its_reason(self):
        with override_settings(RAG_KB_DIR=self.kb_dir, RAG_EMBEDDING_MODEL_ID=""), \
                patch.object(retrieval, "SentenceTransformerEmbedder") as cls:
            with self.assertRaises(AIUnavailable) as caught:
                retrieval.get_provider()
        self.assertEqual(caught.exception.kind, "not_configured")
        cls.assert_not_called()

    def test_an_embedding_model_that_fails_to_load_is_a_retrieval_error(self):
        with override_settings(RAG_KB_DIR=self.kb_dir), \
                patch.object(retrieval, "SentenceTransformerEmbedder", side_effect=OSError("no weights")):
            with self.assertRaises(AIUnavailable) as caught:
                retrieval.get_provider()
        self.assertEqual(caught.exception.kind, "retrieval_error")

    def test_a_failed_load_is_not_retried_on_every_click(self):
        with override_settings(RAG_KB_DIR=self.kb_dir), \
                patch.object(retrieval, "SentenceTransformerEmbedder", side_effect=OSError("no weights")) as cls:
            for _ in range(3):
                with self.assertRaises(AIUnavailable):
                    retrieval.get_provider()
        self.assertEqual(cls.call_count, 1)


# --- Turning passages and a reply into an answer ---------------------------------------------

@override_settings(RAG_TOP_K=3, RAG_MIN_SCORE=0.3)
class AnswerTests(SimpleTestCase):
    def ask(self, provider=None, generator=None, question="What do I do about blank values?"):
        self.provider = provider or FakeProvider()
        self.generator = generator or FakeGenerator()
        return handbook.answer_question(question, provider=self.provider, generator=self.generator)

    def test_a_supported_answer_comes_back_with_the_passages_it_used(self):
        answer = self.ask()
        self.assertEqual(answer.status, "answered")
        self.assertEqual(answer.text, "Ask the source team whether the blanks are expected [1].")
        self.assertEqual([p.rank for p in answer.passages], [1, 2])

    def test_retrieval_asks_for_the_configured_top_k(self):
        self.ask()
        self.assertEqual(self.provider.calls, [("What do I do about blank values?", 3)])

    def test_the_model_gets_the_a8_prompt_plus_the_a9_citation_instruction(self):
        self.ask()
        hits = [{"rank": p.rank, "text": p.text} for p in self.provider.passages]
        a8_messages = handbook_a8.build_messages("What do I do about blank values?", hits)
        [sent] = self.generator.calls
        # The A8 system prompt is kept word for word; A9 only adds one sentence after it.
        self.assertEqual(sent[0], {"role": "system",
                                   "content": handbook_a8.SYSTEM_PROMPT + " " + handbook.CITATION_INSTRUCTION})
        self.assertEqual(sent[1:], a8_messages[1:])  # the context and question are exactly A8's
        self.assertIn("[1]", handbook.CITATION_INSTRUCTION)

    def test_the_a8_prompt_itself_is_unchanged(self):
        self.assertNotIn("Cite", handbook_a8.SYSTEM_PROMPT)
        self.assertEqual(handbook_a8.build_messages("q", [])[0]["content"], handbook_a8.SYSTEM_PROMPT)

    # The approved wording, written out here rather than read from handbook.py, so
    # an edit or paraphrase of either instruction fails a test (A9 Phase 3 experiment).
    A8_PROMPT = ("You answer questions about DataPact, a data quality tool. Use only the context below. "
                 "If the context does not contain the answer, say: I could not find that in the documents.")
    VARIANT_A = ("Rules: Use only the numbered context passages. Put the number of the passage that supports "
                 "each sentence right after that sentence, like [1]. Do not add assumptions, general knowledge "
                 "or details that are not in the passages. If the passages do not establish the answer, say "
                 "only: I could not find that in the documents. Never invent passage numbers or document names.")
    BASELINE = "After each fact, cite the number of the context passage it comes from, like [1]."

    def test_the_active_citation_instruction_is_the_approved_variant_a(self):
        self.assertEqual(handbook.CITATION_INSTRUCTION, self.VARIANT_A)

    def test_the_phase_2_instruction_is_kept_as_the_baseline(self):
        self.assertEqual(handbook.BASELINE_CITATION_INSTRUCTION, self.BASELINE)
        self.assertNotEqual(handbook.BASELINE_CITATION_INSTRUCTION, handbook.CITATION_INSTRUCTION)

    def test_the_a8_prompt_text_is_word_for_word_a8s(self):
        self.assertEqual(handbook_a8.SYSTEM_PROMPT, self.A8_PROMPT)

    def test_the_model_is_sent_the_a8_prompt_then_variant_a_and_a8s_context(self):
        self.ask()
        [sent] = self.generator.calls
        self.assertEqual(sent[0], {"role": "system", "content": self.A8_PROMPT + " " + self.VARIANT_A})
        hits = [{"rank": p.rank, "text": p.text} for p in self.provider.passages]
        self.assertEqual(sent[1:], handbook_a8.build_messages("What do I do about blank values?", hits)[1:])
        self.assertEqual(len(sent), 2)  # no worked example or extra turns (Variant B was rejected)
        self.assertNotIn("Example", sent[0]["content"])

    def test_an_answer_with_one_valid_citation_is_answered(self):
        answer = self.ask(generator=FakeGenerator("Ask the source team [1]."))
        self.assertEqual((answer.status, answer.text), ("answered", "Ask the source team [1]."))

    def test_an_ordinary_answer_with_valid_citations_is_kept_as_written(self):
        reply = ("A blank cell counts as a failure, so ask the source team whether the blanks are "
                 "expected [1].\nDuplicates usually mean the file was exported twice [2].")
        answer = self.ask(generator=FakeGenerator(reply))
        self.assertEqual((answer.status, answer.text), ("answered", reply))

    def test_a_citation_list_is_accepted_when_every_number_was_retrieved(self):
        self.assertEqual(self.ask(generator=FakeGenerator("Check both rules [1, 2].")).status, "answered")

    def test_an_answer_with_no_citation_is_invalid(self):
        answer = self.ask(generator=FakeGenerator("Ask the source team whether the blanks are expected."))
        self.assertEqual((answer.status, answer.text), ("invalid", ""))

    def test_text_that_only_looks_like_a_citation_is_not_one(self):
        for reply in ("See passage 1.", "See (1).", "See [one].", "See []."):
            with self.subTest(reply):
                self.assertEqual(self.ask(generator=FakeGenerator(reply)).status, "invalid")

    def test_an_invented_citation_is_invalid(self):
        self.assertEqual(self.ask(generator=FakeGenerator("The archive keeps it [4].")).status, "invalid")

    def test_an_invented_number_inside_a_citation_list_is_invalid(self):
        self.assertEqual(self.ask(generator=FakeGenerator("Check both rules [1, 4].")).status, "invalid")

    # A9 real-KB run (9 Nov 2026), q13: the model answered an out-of-scope price question with
    # "[1] A DataPact enterprise licence costs $100 per seat." The citation was valid, so it was
    # shown. A number the passages never state is now treated like an invented citation.
    def test_a_number_that_no_passage_states_is_invalid(self):
        answer = self.ask(generator=FakeGenerator("[1] A DataPact enterprise licence costs $100 per seat."))
        self.assertEqual((answer.status, answer.text), ("invalid", ""))

    def test_a_number_copied_from_a_passage_is_kept(self):
        provider = FakeProvider([passage(1, text="A credit hours column might use a range of 0 to 24.")])
        answer = self.ask(provider=provider, generator=FakeGenerator("Use a range of 0 to 24 [1]."))
        self.assertEqual(answer.status, "answered")

    def test_a_number_matches_only_as_a_whole_number(self):
        provider = FakeProvider([passage(1, text="The file had 1000 rows and 3.5 percent failed.")])
        for reply, status in (("It had 100 rows [1].", "invalid"), ("It had 1000 rows [1].", "answered"),
                              ("About 3 percent failed [1].", "invalid"), ("3.5 percent failed [1].", "answered")):
            with self.subTest(reply):
                self.assertEqual(self.ask(provider=provider, generator=FakeGenerator(reply)).status, status)

    def test_weak_passages_are_dropped_before_the_model_sees_them(self):
        provider = FakeProvider([passage(1, 0.9), passage(2, 0.1)])
        answer = self.ask(provider=provider)
        self.assertEqual([p.rank for p in answer.passages], [1])
        self.assertNotIn("Passage 2", self.generator.calls[0][1]["content"])

    def test_no_relevant_passage_means_no_generation(self):
        answer = self.ask(provider=FakeProvider([passage(1, 0.2), passage(2, 0.1)]))
        self.assertEqual(answer.status, "no_passages")
        self.assertEqual(answer.passages, ())
        self.assertEqual(self.generator.calls, [])

    def test_no_passages_at_all_means_no_generation(self):
        answer = self.ask(provider=FakeProvider([]))
        self.assertEqual(answer.status, "no_passages")
        self.assertEqual(self.generator.calls, [])

    def test_the_model_saying_it_found_nothing_is_not_found(self):
        answer = self.ask(generator=FakeGenerator("I could not find that in the documents."))
        self.assertEqual(answer.status, "not_found")
        self.assertEqual(len(answer.passages), 2)  # still shown, as what was searched

    def test_an_empty_reply_is_invalid(self):
        self.assertEqual(self.ask(generator=FakeGenerator("   ")).status, "invalid")

    def test_citing_a_passage_that_was_not_retrieved_is_invalid(self):
        answer = self.ask(generator=FakeGenerator("Check the owner [1] and the archive [4]."))
        self.assertEqual(answer.status, "invalid")
        self.assertEqual(answer.text, "")

    def test_citing_a_passage_that_was_filtered_out_is_invalid(self):
        provider = FakeProvider([passage(1, 0.9), passage(2, 0.1)])
        self.assertEqual(self.ask(provider=provider, generator=FakeGenerator("See [2].")).status, "invalid")

    def test_naming_a_document_that_was_not_retrieved_is_invalid(self):
        answer = self.ask(generator=FakeGenerator("See billing_policy.md for the details [1]."))
        self.assertEqual(answer.status, "invalid")

    def test_naming_a_retrieved_document_is_fine(self):
        self.assertEqual(self.ask(generator=FakeGenerator("See rule_types.md, section Not null [1].")).status, "answered")

    def test_a_long_reply_is_cut_to_the_limit(self):
        answer = self.ask(generator=FakeGenerator("Ask the owner [1]. " + "word " * 1000))
        self.assertEqual(answer.status, "answered")
        self.assertLessEqual(len(answer.text), handbook.MAX_ANSWER_CHARS)
        self.assertTrue(answer.text.startswith("Ask the owner [1]."))

    def test_control_characters_are_removed_from_the_reply(self):
        answer = self.ask(generator=FakeGenerator("Ask the\x00 source\x1b team [1].\nThen rerun."))
        self.assertEqual(answer.text, "Ask the source team [1].\nThen rerun.")

    def test_a_retrieval_failure_is_a_retrieval_error(self):
        with self.assertRaises(AIUnavailable) as caught:
            self.ask(provider=FakeProvider(error=RuntimeError("CUDA out of memory")))
        self.assertEqual(caught.exception.kind, "retrieval_error")

    def test_a_generation_failure_is_an_error(self):
        with self.assertRaises(AIUnavailable) as caught:
            self.ask(generator=FakeGenerator(error=RuntimeError("CUDA out of memory")))
        self.assertEqual(caught.exception.kind, "error")

    def test_an_unavailable_model_keeps_its_own_reason(self):
        with self.assertRaises(AIUnavailable) as caught:
            self.ask(generator=FakeGenerator(error=AIUnavailable("switched off", kind="off")))
        self.assertEqual(caught.exception.kind, "off")

    def test_timings_are_recorded(self):
        answer = self.ask()
        self.assertGreaterEqual(answer.search_ms, 0)
        self.assertGreaterEqual(answer.generate_s, 0)


# --- The question form -----------------------------------------------------------------------

class QuestionFormTests(SimpleTestCase):
    def form(self, question):
        return handbook_views.HandbookQuestionForm(data={"question": question})

    def test_a_normal_question_is_accepted_and_trimmed(self):
        form = self.form("  What does a UNIQUE rule check?  ")
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["question"], "What does a UNIQUE rule check?")

    def test_an_empty_question_is_rejected(self):
        for question in ("", "    ", "\n\t"):
            with self.subTest(question=question):
                self.assertFalse(self.form(question).is_valid())

    def test_a_question_over_the_limit_is_rejected(self):
        self.assertTrue(self.form("a" * handbook_views.MAX_QUESTION_CHARS).is_valid())
        self.assertFalse(self.form("a" * (handbook_views.MAX_QUESTION_CHARS + 1)).is_valid())

    def test_a_question_with_no_words_is_rejected(self):
        for question in ("???", "...!!!", "\x00\x01"):
            with self.subTest(question=question):
                self.assertFalse(self.form(question).is_valid())

    def test_line_breaks_and_control_characters_become_spaces(self):
        form = self.form("What is\na\x1bviolation here?")
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["question"], "What is a violation here?")

    def test_a_null_character_is_refused(self):
        # Django's CharField refuses \x00 itself, before clean_question runs.
        self.assertFalse(self.form("What is a\x00violation?").is_valid())


# --- The page --------------------------------------------------------------------------------

class HandbookPageTestCase(TempKBMixin, TestCase):
    url = reverse("data_quality:handbook-ask")

    def setUp(self):
        retrieval.reset_for_tests()
        self.addCleanup(retrieval.reset_for_tests)
        overrides = override_settings(AI_LOCAL_ENABLED=True, RAG_EMBEDDING_MODEL_ID="test/embedder",
                                      RAG_KB_DIR=self.kb_dir, RAG_CHUNKING="hybrid", RAG_TOP_K=3,
                                      RAG_MIN_SCORE=0.3)
        overrides.enable()
        self.addCleanup(overrides.disable)
        self.user = User.objects.create_user("analyst", password="Spindrift-Harbour-41")
        self.client.force_login(self.user)
        self.provider = FakeProvider()
        self.generator = FakeGenerator()
        for target, name, value in ((retrieval, "get_provider", self.provider),
                                    (local_model, "get_generator", self.generator)):
            patcher = patch.object(target, name, return_value=value)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def ask(self, question="What should I do about blank values?"):
        return self.client.post(self.url, {"question": question})


class AccessTests(HandbookPageTestCase):
    def test_signed_out_visitors_are_sent_to_log_in(self):
        self.client.logout()
        for response in (self.client.get(self.url), self.ask()):
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("data_quality:login"), response["Location"])
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.generator.calls, [])

    def test_a_post_without_a_csrf_token_is_refused(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(self.url, {"question": "What is a violation?"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.generator.calls, [])

    def test_the_form_carries_a_csrf_token(self):
        self.assertContains(self.client.get(self.url), 'name="csrfmiddlewaretoken"')

    def test_other_methods_are_not_allowed(self):
        self.assertEqual(self.client.put(self.url).status_code, 405)

    def test_signed_in_the_navigation_links_to_the_handbook(self):
        html = self.client.get(reverse("data_quality:home")).content.decode()
        nav = html[html.index('<nav class="mainnav"'):html.index("</nav>")]
        self.assertIn(f'href="{self.url}"', nav)

    def test_signed_out_the_navigation_does_not_offer_it(self):
        self.client.logout()
        self.assertNotContains(self.client.get(reverse("data_quality:home")), f'href="{self.url}"')


class GetTests(HandbookPageTestCase):
    def test_looking_at_the_page_never_runs_a_model(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="question"')
        self.assertContains(response, f'maxlength="{handbook_views.MAX_QUESTION_CHARS}"')
        self.get_provider.assert_not_called()
        self.get_generator.assert_not_called()

    def test_the_page_names_the_models_it_would_use(self):
        response = self.client.get(self.url)
        self.assertContains(response, "SmolLM2-1.7B-Instruct")
        self.assertContains(response, "test/embedder")

    def test_an_unconfigured_server_says_why_and_offers_no_button(self):
        with override_settings(RAG_EMBEDDING_MODEL_ID=""):
            response = self.client.get(self.url)
        self.assertContains(response, "no embedding model is configured")
        self.assertNotContains(response, 'id="handbook-form"')
        self.assertNotContains(response, "Ask the handbook</button>")


class AskTests(HandbookPageTestCase):
    def test_a_question_gets_an_answer_and_its_sources(self):
        response = self.ask()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ask the source team whether the blanks are expected [1].")
        self.assertContains(response, "rule_types.md")
        self.assertContains(response, "Not null")
        self.assertContains(response, "Unique")
        self.assertContains(response, "Passage 1 text about blank values.")
        self.assertContains(response, "0.80")
        self.assertEqual(self.provider.calls, [("What should I do about blank values?", 3)])

    def test_the_question_stays_in_the_box(self):
        self.assertContains(self.ask(), "What should I do about blank values?</textarea>")

    def test_an_empty_question_runs_nothing(self):
        response = self.ask("   ")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Type a question", status_code=400)
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.generator.calls, [])

    def test_an_oversized_question_runs_nothing(self):
        response = self.ask("a" * (handbook_views.MAX_QUESTION_CHARS + 1))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.provider.calls, [])

    def test_no_relevant_passage_says_so_and_writes_no_answer(self):
        self.provider.passages = [passage(1, 0.1)]
        response = self.ask()
        self.assertContains(response, "Nothing in the handbook is close enough")
        self.assertEqual(self.generator.calls, [])
        self.assertNotContains(response, "Passage 1 text")

    def test_an_answer_the_documents_do_not_hold_says_so(self):
        self.generator.reply = "I could not find that in the documents."
        response = self.ask()
        self.assertContains(response, "found no answer in them")
        self.assertContains(response, "Passage 1 text about blank values.")

    def test_a_reply_that_fails_the_checks_is_not_shown(self):
        self.generator.reply = "It is covered in secret_policy.md [7]."
        response = self.ask()
        self.assertContains(response, "could not be checked against the passages")
        self.assertNotContains(response, "secret_policy.md")

    def test_an_uncited_reply_is_not_shown_as_an_answer(self):
        self.generator.reply = "Ask the source team whether the blanks are expected."
        response = self.ask()
        self.assertContains(response, "could not be checked against the passages")
        self.assertNotContains(response, 'id="handbook-answer-text"')
        self.assertNotContains(response, "whether the blanks are expected.")

    def test_model_text_and_passages_are_escaped(self):
        # No digits in the reply's script: a number the passages do not contain would hide the reply.
        self.generator.reply = "<script>alert(document.cookie)</script> Ask the owner [1]."
        self.provider.passages = [passage(1, text="<img src=x onerror=alert(2)> blank values")]
        html = self.ask().content.decode()
        self.assertNotIn("<script>alert(document.cookie)", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;alert(document.cookie)&lt;/script&gt;", html)
        self.assertIn("&lt;img src=x onerror=alert(2)&gt;", html)


class UnavailableTests(HandbookPageTestCase):
    def assert_unavailable(self, response, text):
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, text, status_code=503)

    def test_no_embedding_model_configured(self):
        with override_settings(RAG_EMBEDDING_MODEL_ID=""):
            self.assert_unavailable(self.ask(), "no embedding model is configured")
        self.assertEqual(self.provider.calls, [])

    def test_the_local_model_switched_off(self):
        with override_settings(AI_LOCAL_ENABLED=False):
            self.assert_unavailable(self.ask(), "local model is switched off")
        self.assertEqual(self.provider.calls, [])

    def test_a_missing_knowledge_base(self):
        with override_settings(RAG_KB_DIR=self.kb_dir / "nowhere"):
            self.assert_unavailable(self.ask(), "handbook documents are missing")
        self.assertEqual(self.provider.calls, [])

    def test_the_embedding_model_failing(self):
        self.get_provider.side_effect = AIUnavailable("no weights", kind="retrieval_error")
        self.assert_unavailable(self.ask(), "handbook search could not run")
        self.assertEqual(self.generator.calls, [])

    def test_the_search_itself_failing(self):
        self.provider.error = RuntimeError("CUDA out of memory")
        self.assert_unavailable(self.ask(), "handbook search could not run")

    def test_a_knowledge_base_with_no_text(self):
        self.get_provider.side_effect = AIUnavailable("no text", kind="empty_kb")
        self.assert_unavailable(self.ask(), "handbook documents hold no text to search")
        self.assertEqual(self.generator.calls, [])

    def test_the_local_model_failing_to_load(self):
        self.get_generator.side_effect = AIUnavailable("OSError: no weights")
        self.assert_unavailable(self.ask(), "local model could not write an answer")

    def test_generation_failing(self):
        self.generator.error = RuntimeError("CUDA out of memory")
        self.assert_unavailable(self.ask(), "local model could not write an answer")

    def test_an_unconfigured_server_never_shows_an_answer(self):
        # Nothing stands in for the real service: with no embedding model set,
        # no provider is asked and no answer panel appears. (ProviderTests shows
        # the real loader refuses too, without loading anything.)
        with override_settings(RAG_EMBEDDING_MODEL_ID=""):
            response = self.ask()
        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, 'id="handbook-answer-text"', status_code=503)
        self.get_provider.assert_not_called()

# A9 evidence

Raw results of the A9 handbook Q&A runs with the real models. They are summarised in
[`README_AI.md`](../../README_AI.md), section "A9". There are two groups:

* **Sample files (6 Nov 2026):** the three `phase*` files below, run against
  `rag_system/sample_kb/`.
* **Real handbook (9 Nov 2026):** the two `realkb_*` files, described at the end.

## Sample knowledge base runs (6 Nov 2026)

These runs used `sentence-transformers/all-MiniLM-L6-v2` on the CPU and
`HuggingFaceTB/SmolLM2-1.7B-Instruct` on an RTX 3050 Ti Laptop GPU (4 GB). They ran
against **`rag_system/sample_kb/`**, the two small sample files in the A8 folder
(7 hybrid chunks). They are not the evaluation on the real knowledge base, which is
in the last section.

| File | What it is |
| --- | --- |
| `phase2_smoke_results.json` | First real-model run: 7 questions, the Phase 2 citation instruction (now `BASELINE_CITATION_INSTRUCTION`). |
| `phase3_prompt_experiment_results.json` | Prompt experiment: the same 7 questions under 3 system prompts (baseline, Variant A, Variant B), the exact prompt texts, the retrieved passages and every raw reply. One pass, no reruns. |
| `phase4_variant_a_verify.json` | One run after Variant A became the code's `CITATION_INSTRUCTION`, compared reply by reply with the Phase 3 Variant A run. |

Settings for all three: hybrid chunking, top-k 3, `RAG_MIN_SCORE` 0.3, greedy decoding
(`do_sample=False`), at most 160 new tokens, Hugging Face offline mode. The questions are
q1-q5 from `rag_system/sample_queries.json` plus two more: t6 "What parameters does a
RANGE rule take?" and t7 "How do I reset my DataPact password?".

**One change from the originals.** Each file held the absolute local path of the knowledge
base folder in `settings.RAG_KB_DIR`. That one value was replaced with
`rag_system/sample_kb` (the folder relative to the repository root, as it was configured).
Nothing else differs; a script compared each copy with its original as parsed JSON (checked
again on 7 Nov 2026). The originals had different names and are not in the repository: they
are in a temporary working folder on the development laptop, so these hashes can be checked
only there.

| Copy in this folder | Original file (not in the repository) | SHA-256 of the original |
| --- | --- | --- |
| `phase2_smoke_results.json` | `smoke_results.json` | `d1fa18255822becb7ea4d74dec881f6e1f92a08372ee57c79b4bd3c863719f46` |
| `phase3_prompt_experiment_results.json` | `phase3/prompt_experiment_results.json` | `440c0c963cbea19a1ea54abf65d9fc9b713296164f229e4cf8027fe71bc7ef4c` |
| `phase4_variant_a_verify.json` | `phase4/variant_a_verify.json` | `003b9ab10d2bc92b1cf3d6f363b46cc97a67605434d15966119c96f080016eaa` |

**Hashes of the copies.** The originals and the copies were written on Windows with CRLF line
endings. Git stores text with LF endings (`core.autocrlf`), so a checkout has LF endings on
macOS and Linux, and usually CRLF again on Windows. The hash depends on which:

| Copy | SHA-256 with CRLF endings (as written) | SHA-256 with LF endings (as Git stores it) |
| --- | --- | --- |
| `phase2_smoke_results.json` | `8413be9f3629af23b3c11cd14971973def1a31cce0df0700fa9cc4140173e751` | `dbc6e3a0e3400e4f476152d8d9e975b0b97b18c058428a5fe6bc52ef9d95ec24` |
| `phase3_prompt_experiment_results.json` | `90edc570f43ea60c677f7580539d6b85fc97ae589a976cc6c6e6532e335099cf` | `310e9eed1464a26261ffa03fa9cbe1501637ea69a47b57924b6a5ca9f1740a67` |
| `phase4_variant_a_verify.json` | `154d196e1b6eea440b1825dd99375db01aefa40561a660bce0b5afa2029ddab8` | `4a9c27bb6efa9c3ea619ebc353d5aeb8ace2e946cfe5e64fde0362ed4129781c` |

The JSON content is the same either way; only the line endings differ.

The run logs (model-loading progress and library warnings) and the scripts that produced
these files are not included.

The `status` field is what the app's own check (`check_reply` in
`data_quality/ai/handbook.py`) decided. Whether an answer was actually correct is a
separate judgement, made by reading each statement against the passage text, and is
recorded in `README_AI.md`, not in these files. A valid citation does not show that a
claim is supported.

## Real handbook runs (9 Nov 2026)

These ran against `rag_system/knowledge_base/` (the A8 handbook: 9 documents, 40
sections) with the 14 questions in `rag_system/test_queries.json`. They used A9's own
code, with Hugging Face offline mode on, in one pass with no reruns. The embedding
model was `sentence-transformers/all-MiniLM-L6-v2`, a fallback: A8 recommends
`all-mpnet-base-v2`, which was not downloaded. The files hold no local paths
(`RAG_KB_DIR` is stored relative to the repository).

| File | What it is |
| --- | --- |
| `realkb_retrieval_minilm_fixed_vs_hybrid.json` | Retrieval only, fixed against hybrid chunking, top 3, no cutoff. For each question: the 3 passages with document, section, score and text; whether the expected section was retrieved; and whether the answering sentences were (`answer_bearing`: full, partial or none, with the sentences found). |
| `realkb_generation_minilm_hybrid.json` | The full run through `handbook.answer_question`: hybrid chunking, top 3, `RAG_MIN_SCORE=-1`, Variant A, SmolLM2-1.7B on the 4 GB GPU. For each question: the passages, the raw reply, the status, the shown text, the cited numbers, the timings and the peak GPU memory. `settings` records the configuration and the exact system prompt. |

`status` in the generation file is what `check_reply` decided during the run.
`status_with_number_check` was added afterwards. It is the same recorded reply checked
again with the number rule that the run led to (`check_reply` now hides a reply that
states a number no passage contains). Only q13 differs: `answered`, then `invalid`.
The model was not run again.

Copies of the run logs and the scripts are not included. SHA-256 with LF endings (as
Git stores them):

| File | SHA-256 (LF) |
| --- | --- |
| `realkb_retrieval_minilm_fixed_vs_hybrid.json` | `da31e848f1a5c31c9870f9a408547044a7adf2e73399903555160c0da6f9fe5f` |
| `realkb_generation_minilm_hybrid.json` | `6d67f6862d7fcaf2064e694067ca9b51756b9486ff8d7f407a36c932f33091cc` |

The browser rehearsal screenshots for the same configuration are in
`docs/screenshots/a9/`: q04 answered with its passages, q14 refused, q13 hidden by the
number check, and q08's weak answer.

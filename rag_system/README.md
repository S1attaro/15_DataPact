# DataPact A8: RAG system

INFO 490 MG, Team 15.

`rag_system.ipynb` looks up text from our documents and uses it to answer questions. It tests 3
embedding models with 3 ways of chunking. SmolLM2-1.7B-Instruct writes the answers in every test.

## What is in this folder

| Path | What it is | Owner |
| --- | --- | --- |
| `rag_system.ipynb` | Part 1 pipeline and Part 2/3 experiment runs: 3 embedding models x 3 chunking strategies, scaling, threshold and improvement tests. Saved with the outputs of the full run | Connor Slattery |
| `rag_analysis.md` | The written analysis: evaluation metrics and tables, embedding and chunking analysis, data scaling, failure cases, improvement before/after, and Part 4 system design | Hriday Agarwal (Parts 1-3), Ashok Chacko (Part 4) |
| `knowledge_base/` | The DataPact user handbook: 9 documents, 40 sections, 4,019 words | Ashok Chacko |
| `test_queries.json` | 14 test queries (3 easy, 4 medium, 5 hard, 2 out of scope) with expected sections and phrases | Ashok Chacko |
| `results/` | Raw outputs of the full run (evaluation table, retrieved chunks, summaries, scaling, threshold, improvement) | Connor Slattery |
| `evaluation/` | Manual grades for all 126 rows and 56 improvement rows, `rag_evaluation.ipynb` that rebuilds every table in `rag_analysis.md`, and the graded evaluation table | Hriday Agarwal |
| `part4_system_design.md` | Ashok's Part 4 draft, merged into `rag_analysis.md` | Ashok Chacko |
| `sample_kb/`, `sample_queries.json` | Small examples the notebook uses only while `knowledge_base/` is empty | Connor Slattery |
| `requirements.txt` | Pinned Python packages | |

No model weights are stored here: the models download to the Hugging Face cache outside the repo.

## Results at a glance

Full run on 8 Nov 2026 (AMD Radeon RX 7900 XTX). Details and evidence are in `rag_analysis.md`.

| | Small (MiniLM, 384) | Medium (mpnet, 768) | Large (bge, 1024) |
| --- | --- | --- | --- |
| Right section in top 3 (auto) | 94.4% | **97.2%** | 88.9% |
| Answering text in top 3 (manual) | 88.9% | **94.4%** | 83.3% |
| Answer score (manual) | 48.6% | 48.6% | 50.0% |
| Search time per query | 5.1 ms | 9.1 ms | 16.0 ms |

* Every setup refused both out-of-scope questions.
* Fixed-length chunks scored a perfect automatic hit rate but split some sections so the answer was
  not retrieved; hybrid (section-aligned) chunks gave the model the full answer most often.
* 24 of the 35 poor answers had the right text in their context: the 1.7B generator, not retrieval,
  is the main limit.
* A stricter prompt raised the manual answer score on the best setup from 45.8% to 62.5% and removed
  every wrong refusal.

**Recommended for A9:** medium embeddings, top 3, the strict prompt, no similarity threshold, and a
follow-up test of hybrid chunking with the strict prompt.

## Reproducing the evaluation

The evaluation does not need a GPU or any model. From the `evaluation` folder:

```
jupyter nbconvert --to notebook --execute --inplace rag_evaluation.ipynb
```

It reads `../results/` and `manual_grades*.csv` and rewrites the tables and chart in `evaluation/`.

## Setup

Run this from the `rag_system` folder:

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

On Mac or Linux, activate with `source venv/bin/activate`.

**If you have an AMD GPU, don't use `requirements.txt`.** It installs normal PyTorch, which would
replace the ROCm version. Our A6 run on the Radeon RX 7900 XTX used `torch 2.9.1+rocm7.2.1`, which
shows up as `cuda`. If your environment already has that version, you only need this:

```
pip install sentence-transformers==6.2.0
```

To check that PyTorch can see your GPU:

```
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

If it prints `False`, the notebook still works on the CPU, but it is slower. SmolLM2 needs about
7 GB of free RAM on the CPU.

## Running the notebook

Open `rag_system.ipynb` and set `RUN_MODE` in the first code cell.

1. `dry`: uses fake models and downloads nothing. This only checks the code.
2. `quick`: uses the real models with 2 queries. This checks the GPU. The first run downloads the
   models.
3. `full`: uses the real models with all the queries. This is the real run.

The model files download to the Hugging Face cache, which is outside this repo. Only a `full` run
on the real documents saves to `results/`. Every other run saves to a `results_*` folder that Git
ignores.

## Adding the knowledge base

Put each document in `knowledge_base/` as its own `.md` file, with a blank line between paragraphs:

```
# Document title

## Section name

First paragraph of 80 to 200 words.

Second paragraph.
```

Keep each section to one topic. Hybrid chunks never cross sections. Fixed and overlap chunks can
cover two sections, but never two documents. The scoring uses the section name.

Put the queries in `test_queries.json`, next to the notebook:

```json
[
  {"id": "q1", "query": "Can I edit a contract that was already used?",
   "expected_doc": "validation_process.md", "expected_section": "Contracts and versions",
   "expected_keywords": ["new version"]},
  {"id": "q2", "query": "What is the refund policy?", "out_of_scope": true}
]
```

`expected_keywords` are short phrases a good answer should have. The file name and section name
have to match exactly. `sample_kb/` and `sample_queries.json` are small examples, and the notebook
only uses them while `knowledge_base/` is empty.

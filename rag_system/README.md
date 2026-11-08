# DataPact A8: RAG system

INFO 490 MG, Team 15.

`rag_system.ipynb` looks up text from our documents and uses it to answer questions. It tests 3
embedding models with 3 ways of chunking. SmolLM2-1.7B-Instruct writes the answers in every test.

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

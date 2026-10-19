# llm-test: the A6 Part 1 model lab

| File | What it is |
| --- | --- |
| `ai_prototype.ipynb` | **The benchmark** (Hriday Agarwal), run on a Google Colab T4 GPU. 15 instruct models under 2B parameters in 5 size categories, all on the same 8 labelled inputs, then Route A (zero-, one-, few- and many-shot) on the top 3. All outputs and the Findings section are kept exactly as the run produced them. |
| `results_light/` | The CSVs and charts that run saved: `matrix_results.csv` (120 rows: 15 models x 8 inputs) and `prompting_results.csv` (96 rows: 3 models x 4 methods x 8 inputs). |
| `ai_prototype_3b_plus.ipynb` | **The 3B+ follow-up** (Connor Slattery), run on a local AMD Radeon RX 7900 XTX (24 GB). The same inputs, prompt, generation settings and scoring as the benchmark, on 4 larger models: Qwen2.5-3B, Falcon3-3B, Phi-3.5-mini (3.8B) and Qwen2.5-7B, with all four Route A methods on each. Its Findings section compares them with the light models. |
| `results_3b_plus/` | That run's CSVs and charts, plus `size_comparison.csv` (all 19 models) and `few_shot_comparison.csv`. `results_light/` was only read, never changed. |
| `ai_prototype_full_range.ipynb` | The first design of the same lab, with models from 0.13B up to 8B (the larger ones in 4-bit). Its Colab runs ran out of memory, so it has **no results**; the benchmark above replaced it. Kept for reference. |

The benchmark was written as `ai_prototype_light.ipynb` and renamed to
`ai_prototype.ipynb`, the path the assignment names. The only edit to it since
the run is one filename in its introduction, which now points at
`ai_prototype_full_range.ipynb`; its code, outputs and results are unchanged.

**Result used by the Django app.** `HuggingFaceTB/SmolLM2-1.7B-Instruct` with the
few-shot prompt (3 examples): 8/8 valid replies and 8/8 correct causes, at about
3.6 GB of GPU memory. The Django explain page uses the same model and the same
prompt (see `data_quality/ai/prompts.py`).

**Larger models.** The 3B+ run found that bigger models always return valid JSON
but still answer `DATA_ISSUE` for everything at zero-shot (50%). On the app's
few-shot prompt they scored 50-75% against SmolLM2's 100%; Qwen2.5-7B reached
8/8 only with the 12-example prompt, using up to 15.7 GB of GPU memory.

**Limits to keep in mind.** Each method was scored on 8
inputs, so one answer moves a score by 12.5 points.

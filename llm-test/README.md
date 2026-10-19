# llm-test: the A6 Part 1 model lab

| File | What it is |
| --- | --- |
| `ai_prototype.ipynb` | **The benchmark** (Hriday Agarwal), run on a Google Colab T4 GPU. 15 instruct models under 2B parameters in 5 size categories, all on the same 8 labelled inputs, then Route A (zero-, one-, few- and many-shot) on the top 3. All outputs and the Findings section are kept exactly as the run produced them. |
| `results_light/` | The CSVs and charts that run saved: `matrix_results.csv` (120 rows: 15 models x 8 inputs) and `prompting_results.csv` (96 rows: 3 models x 4 methods x 8 inputs). |
| `ai_prototype_full_range.ipynb` | The first design of the same lab, with models from 0.13B up to 8B (the larger ones in 4-bit). Its Colab runs ran out of memory, so it has **no results**; the benchmark above replaced it. Kept for reference. |

The benchmark was written as `ai_prototype_light.ipynb` and renamed to
`ai_prototype.ipynb`, the path the assignment names. The only edit to it since
the run is one filename in its introduction, which now points at
`ai_prototype_full_range.ipynb`; its code, outputs and results are unchanged.

**Result used by the Django app.** `HuggingFaceTB/SmolLM2-1.7B-Instruct` with the
few-shot prompt (3 examples): 8/8 valid replies and 8/8 correct causes, at about
3.6 GB of GPU memory. The Django explain page uses the same model and the same
prompt (see `data_quality/ai/prompts.py`).

**Limits to keep in mind.** Every model tested is under 2B parameters, so these
results say nothing about much larger models. Each method was scored on 8
inputs, so one answer moves a score by 12.5 points.

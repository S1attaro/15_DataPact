# Poster content (22" x 36" portrait, 3 columns)

Text for Ashok's layout. Keep it as bullets. Figures are SVG (vector) in this
folder, so they print sharp. **Numbers marked [A10] come from
`key_numbers.md`.** Re-run `python docs/poster/make_poster_charts.py` after
the benchmark run and copy the new numbers in.

---

## HEADER

**DataPact**
*Know when your data breaks the rules, and why.*

Hriday Agarwal (hda3@illinois.edu) · Ashok Chacko (achac@illinois.edu) ·
Tejas Jaggi (tejasj2@illinois.edu) · Connor Slattery (cslat@illinois.edu)
INFO 490: Advanced AI Web-Apps Development · Team 15 · Fall 2026

---

## 1. PROBLEM & MOTIVATION (column 1, top)

- Teams get the same data file every week or month (enrollment, sales, logs).
- When a file changes shape (a new status code, blank columns, bad types), reports break quietly.
- Finding *which* rows broke and *why* is slow, manual work.
- The hardest call: is the **data wrong**, or is our **rule out of date**?

**Our solution**
- Write the rules once as a versioned **data contract**.
- DataPact checks every new file and points to the exact rows and values that failed.
- **AI explains each failure:** likely cause (data issue vs outdated contract) + next step.
- **Handbook Q&A (RAG)** answers "how do I…" questions from our docs, with sources.

---

## 2. SYSTEM ARCHITECTURE (column 2, largest section)

Figure: `architecture.svg`

**Stack**
- Django 5.2, SQLite, Vega-Lite charts, Google OAuth (allauth)
- Hosted on PythonAnywhere. The local models (SmolLM2, MiniLM) do not fit there, so in
  production they are switched off: Explain uses Groq, and the handbook runs only on a
  team laptop.

**AI path 1: explain a violation**
- Input: rule, column, failed-row count, up to 3 *safe* sample values (no names or IDs leave the server)
- Few-shot prompt → **Groq gpt-oss-20b** (API, production) or **SmolLM2-1.7B** (local only, picked from our 15-model benchmark)
- Output must parse as JSON with an allowed cause, or nothing is shown

**AI path 2: handbook Q&A (RAG) - local only, off in production**
- Question → **MiniLM** embedding → top-3 passages from 9 handbook docs (score ≥ 0.3)
- SmolLM2 answers from those passages only
- Guardrails: answer must cite a passage it was shown, and may not state a number the passages don't contain

**Monitoring**
- Every AI request logs latency, tokens, cost and outcome (never the user's text) → **/analytics/** dashboard

---

## 3. EVALUATION & ANALYTICS (column 2 bottom / column 3 top)

**What we evaluated, and how**
- **Model choice (A6):** 15 small models × 8 fixed inputs, scored for accuracy and speed → SmolLM2-1.7B
- **RAG quality (A8):** 14 test questions × 3 embedding models × 3 chunking strategies, hit@3, MRR and manually graded answers
- **Live system (A10):** every request logged; dashboard tracks performance, user behavior and cost

**Charts**
- `fig_latency_by_engine.svg`: latency by feature and engine
- `fig_rag_improvement.svg`: RAG answer quality by setup
- (optional third) `fig_cost_per_1000.svg`: cost per 1,000 requests
- Screenshot of the `/analytics/` dashboard (take at full width)

**Table: engines compared** (from `key_numbers.md`; latency = the 288 requests that
reached the model, so 63 handbook + 9 explain per setup; $ per 1,000 = all 77 requests
of that setup, both features together)

| Engine | Feature | Median latency | p95 | $ per 1,000 requests (setup) |
|---|---|---|---|---|
| Groq gpt-oss-20b | explain | 0.36 s | 0.50 s | $0.061 |
| SmolLM2, GPU via Ollama | explain | 2.66 s | 2.74 s | $0.037 |
| Ollama qwen2.5:14b, GPU | explain | 4.11 s | 4.31 s | $0.043 |
| SmolLM2, CPU via transformers | explain | 14.23 s | 16.34 s | $0.110 |
| Groq gpt-oss-20b | handbook | 0.36 s | 0.66 s | $0.061 |
| SmolLM2, GPU via Ollama | handbook | 2.55 s | 2.75 s | $0.037 |
| Ollama qwen2.5:14b, GPU | handbook | 2.77 s | 3.60 s | $0.043 |
| SmolLM2, CPU via transformers | handbook | 22.59 s* | 35.76 s | $0.110 |

\* Two groups by reply length: short replies under 13 s, full answers over 22 s.

Benchmark: 308 requests (68 handbook + 9 explain per setup); 20 handbook requests
never reached a model (no passage matched) and are left out of latency. In Django,
SmolLM2 runs on the CPU through transformers (no AMD GPU support for PyTorch on
Windows); we also ran it on our GPU through Ollama, a different runtime. Cost counts
electricity only (150 W CPU, 355 W GPU) for local engines.

---

## 4. KEY RESULTS (column 3)

- **Groq is fastest** at explaining violations (0.36 s median vs 2.66 s for SmolLM2 and 4.11 s for Qwen2.5 through Ollama on our GPU, and 14.2 s for SmolLM2 on our CPU).
- **How a model is served matters most for speed.** The same SmolLM2 took 22.6 s (handbook) and 14.2 s (explain) through transformers on our CPU, against 2.55 s and 2.66 s through Ollama on our GPU: about 9x and 5x. The runtime differs as well as the hardware, so this is not a pure CPU-vs-GPU result.
- **On the GPU, a bigger model costs little time.** Qwen2.5 14B is about 8x larger than SmolLM2 but only 0.22 s slower on handbook questions (1.45 s slower on explanations), with no invalid answers (SmolLM2 had 7).
- **Bigger models declined out-of-scope questions.** Each setup got the same 10 pricing, support and legal questions. Across all four, 35 of 40 went unanswered (88%): 20 never reached a model (no passage matched), 13 the model declined, 2 our checks caught. The 5 answered anyway were all SmolLM2; Groq and Qwen2.5 answered none.
- **Speed drives local cost.** Counting only electricity, SmolLM2 on the GPU was cheapest ($0.037 per 1,000 requests), then Qwen2.5 on the GPU ($0.043), Groq ($0.061), and SmolLM2 on CPU ($0.110), because it runs so long.
- **Hosting decides cost.** Counting servers, a hosted API was cheaper at every traffic level we modeled (A7: $2/day vs $29/day at 1,000 daily users; A7 priced a Hugging Face-hosted API).
- **A strict prompt beat retrieving more.** Answer score went from 45.8% to 62.5% and wrong refusals from 3 to 0 (A8). Retrieving only 1 passage made answers worse (41.7%).
- **Retrieval is nearly free:** about 5 ms per search (median, every setup), 0.02-1.3% of handbook time (3.5% for Ollama-SmolLM2 because of one 5.5 s search). Generation is the bottleneck, so a faster model server matters more than a faster search.

---

## 5. LIMITATIONS & FUTURE WORK (column 3, bottom)

**What does not work well**
- SmolLM2 gave invalid handbook answers (6 of 68 on CPU, 7 of 68 on GPU). Qwen2.5 and Groq gave none.
- The local model does not fit on our host (PythonAnywhere disk), so production relies on Groq.
- The handbook can't answer pricing or support questions (14.7% of benchmark handbook requests; 35 of 40, 88%, went unanswered), and once made up a price ("$100 per seat") until we added the number check.
- Benchmark dates and user labels are synthetic and each question was asked once per setup, so the usage and topic charts describe our test set, not real users.
- Our checks catch invented citations and numbers, but not every unsupported sentence.
- Token counts on live pages are estimates (characters ÷ 4).
- "Answered" means the reply passed our checks, not that a person graded it correct. Only the A8 scores are graded by hand.

**Next steps**
- Move hosting to **AWS Lightsail** so we control the server.
- Serve the model with **vLLM** for many users at once (benchmark vs Ollama on our own GPU).
- Move pricing, support and legal info to **static pages** and point those questions there.
- **Split-screen view:** the AI explanation next to the violations table.

---

## FOOTER

- QR code 1: GitHub: https://github.com/S1attaro/15_DataPact
- QR code 2: live app: https://tjaggi.pythonanywhere.com/ (confirm the URL with Tejas before printing)
- Ready-made vector QR codes: `qr_github.svg`, `qr_app.svg`.

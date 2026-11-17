# A10: AI System Evaluation & Analytics Dashboard

DataPact, INFO 490 Team 15. Dashboard: `/analytics/` (sign-in required).
Test login: `mohitg2` / `uiuc12345`.

This file is Part 1 (analytics design). The PDF is built from it.

## What we monitor

DataPact has two AI features:

1. **Explain a violation**: SmolLM2-1.7B on our server, or Groq's `gpt-oss-20b` API.
2. **Handbook Q&A (RAG)**: MiniLM embeddings find 3 handbook passages, then SmolLM2 answers from them.

Every request to either feature writes one row to `AIRequestLog`: time, feature, engine, model, user (as `user-<id>`), request type, input size, prompt and completion tokens, retrieval time, total latency, outcome and cost. The user's question and file values are never stored.

## Step 1: Questions

### System performance
| ID | Question | Why it matters |
|---|---|---|
| P1 | How does latency vary across requests: mean, median and 95th percentile? | The mean hides slow outliers. p95 is what the slowest users feel. |
| P2 | Which engine is faster, local SmolLM2 or the Groq API, and for which feature? | Decides which engine to use by default in production. |
| P3 | Where does handbook time go: retrieval or generation? Do longer inputs answer slower? | Tells us what to optimize (the embedder or the model). |

### User behavior
| ID | Question | Why it matters |
|---|---|---|
| B1 | How often are the AI features used per day, and is use growing? | Shows adoption and helps size the server. |
| B2 | Which feature and which topics do users ask about most? | Shows where to improve docs and prompts. Out-of-scope pricing/support questions show which static pages we need. |
| B3 | How often does the handbook fail to answer (not found, no passages, reply rejected)? | A high failure rate means the knowledge base has gaps. |

### Cost
| ID | Question | Why it matters |
|---|---|---|
| C1 | What does one request cost on each engine and model? | Compares the API bill with running our own model. |
| C2 | Which request types use the most tokens, and drive most of the cost? | Shows where shorter prompts or fewer few-shot examples save the most. |
| C3 | How does daily cost change over time, and what would a month cost? | Budgeting before launch. |

## Step 2: Dashboard plan

### Widgets
- **Summary cards (KPI tiles):** single numbers with no chart needed
- **Histogram:** latency distribution
- **Bar charts:** comparisons across engines, models, topics
- **Line charts:** trends over days
- **Stacked bar:** retrieval vs generation time, prompt vs completion tokens
- **Table:** top cost drivers
- **Filters:** time range (7/30/90/all days), engine, data source

### Question to widget mapping
| Question | Widget | Data used |
|---|---|---|
| P1 | Cards: mean, median, p95 latency + latency histogram | `latency_ms` |
| P2 | Bar: median latency by engine and feature | `engine`, `feature`, `latency_ms` |
| P3 | Stacked bar: retrieval vs generation time (handbook); scatter: input size vs latency | `retrieval_ms`, `latency_ms`, `input_chars` |
| B1 | Card: total requests and users + line: requests per day | `created_at`, `user_label` |
| B2 | Bar: requests by feature and topic | `feature`, `query_type` |
| B3 | Bar: handbook outcome breakdown | `status` (handbook rows) |
| C1 | Cards: cost per 1,000 requests (Groq vs local) + bar: cost per 1,000 by model | `engine`, `model_name`, `cost_usd` |
| C2 | Stacked bar: avg prompt vs completion tokens by request type + table: top cost drivers | `query_type`, `prompt_tokens`, `completion_tokens`, `cost_usd` |
| C3 | Line: cost per day by engine + card: projected 30-day cost | `created_at`, `engine`, `cost_usd` |

### How cost is worked out
- **Groq:** tokens × Groq's price for gpt-oss-20b ($0.075 per 1M input tokens, $0.30 per 1M output tokens).
- **Local / Ollama:** electricity only, watts × time × $0.15/kWh. SmolLM2 runs on the CPU (no ROCm PyTorch on Windows), so it uses about 150 W. Ollama runs on the GPU, so it uses 355 W (RX 7900 XTX).
- Local cost leaves out the GPU and server. Our A7 tables (`multi_model_system/results/`) show that once hosting is included, the API is cheaper at every traffic level we tested. The dashboard caption says this so the chart is not misread.

## Step 3: Statistical thinking
- **Mean vs median vs p95 latency:** latency is right-skewed (a few slow requests, like the first local request that loads the model). The median shows a typical request and p95 shows the bad tail. The mean alone would mislead.
- **Distributions:** a latency histogram shows the skew and any second bump (cold starts, Groq rate-limit retries).
- **Group comparisons:** latency and cost split by engine, model and feature. We compare medians because of the skew.
- **Trends over time:** requests and cost per day, to see growth and weekday/weekend patterns.
- **Rates and shares:** failure rate as a share of handbook requests, and each request type's share of total cost.
- **Simple projection:** projected monthly cost = average daily cost in the selected range × 30.
- **Normalizing:** cost per 1,000 requests, so engines with different request counts can be compared fairly.

## Data source
- **Live:** real use of the two pages writes rows automatically. On these rows, token counts are estimates (characters ÷ 4).
- **Benchmark:** `python manage.py collect_ai_logs --engines local,groq,ollama:<model>` runs the 68 handbook questions in `data/a10_handbook_questions.json` (the 14 A8 test questions, variations, and out-of-scope pricing/support questions) and every seeded violation through each engine. Latency and token counts are real (tokenizer, Groq usage, Ollama counters). Timestamps and user labels are spread over 3 weeks afterwards, so the behavior charts have a realistic shape.
- **Simulated:** `collect_ai_logs --simulate` draws rows from ranges we measured ourselves (A9 real-handbook run: retrieval 6-20 ms, SmolLM2 0.4-5 s). This is the fallback if no model can run.
- The dashboard's "Data source" filter separates all three.

## Findings (benchmark, 308 requests)

Each setup ran the same 68 handbook questions and 9 violation explanations.

Two populations, never mixed without a label:

- **All 308 requests:** used for outcomes, answered counts and cost.
- **The 288 that reached the model:** used for every latency figure. The other 20 are
  retrieval-only (`no_passages`): no passage scored above 0.3, so the model was never
  called and the request ended in about 5 ms. Counting them as answer times would pull
  every latency number down.

Overall latency (288): mean 6,256 ms, median 2,674 ms, p95 32,004 ms. (Over all 308 the
same figures would be 5,850 / 2,618 / 29,660 ms; the dashboard reports the 288.)

| Setup | Handbook median (n=63) | Explain median (n=9) | Handbook answered (of 68) | Invalid replies | $ per 1,000 (all 77) |
|---|---|---|---|---|---|
| Groq gpt-oss-20b (API) | 0.36 s | 0.36 s | 52 | 0 | $0.061 |
| SmolLM2 on CPU (transformers in Django) | 22.6 s* | 14.2 s | 53 | 6 | $0.110 |
| SmolLM2 on GPU (Ollama) | 2.55 s | 2.66 s | 54 | 7 | $0.037 |
| Qwen2.5 14B on GPU (Ollama) | 2.77 s | 4.11 s | 54 | 0 | $0.043 |

\* SmolLM2 on the CPU splits by reply length: 30 handbook requests with short replies
(median 25 tokens) took under 13 s, 32 full answers (median 130 tokens) took over 22 s.
The median falls between the groups, so read it as "13-23 s depending on reply length".

- **P1/P2:** Groq is fastest by far. SmolLM2 through Ollama on our GPU was about 9x faster
  than SmolLM2 through transformers on our CPU for the handbook (22.6 s vs 2.55 s) and about
  5x for explanations (14.2 s vs 2.66 s). The two runs differ in software (runtime and
  model packaging) as well as hardware, so this is not a pure CPU-vs-GPU measurement.
- **P2:** Qwen2.5 14B is 0.22 s slower than SmolLM2 on the GPU for handbook questions, but
  1.45 s slower for explanations (4.11 s vs 2.66 s).
- **P3:** a search takes about 5 ms (median) on every setup. As a share of total handbook
  time that is 0.02% (SmolLM2 CPU), 0.18% (Qwen2.5), 1.3% (Groq) and 3.5% (Ollama SmolLM2,
  whose share comes from one 5.5 s search). Generation is the bottleneck.
- **B3:** each setup was asked the same 10 out-of-scope questions (40 requests in all).
  35 of 40 went unanswered (87.5%, about 88%): 20 never reached a model because no passage
  matched, 13 the model declined ("not in the documents"), 2 were replies our checks
  rejected. The 5 answered anyway were all SmolLM2 (2 on the CPU, 3 on the GPU); Groq and
  Qwen2.5 answered none of their 10. A bigger model, or static pages for pricing and
  support, would fix this.
- **C1:** counting electricity only, slow models cost the most, so SmolLM2 on CPU is the
  most expensive setup. Once hosting is included, a hosted API was cheaper at every traffic
  level in our A7 model (that model priced a Hugging Face-hosted API, not Groq itself).
- **B1/B2 data caveat:** benchmark timestamps and the 9 user labels are synthetic, and
  every question was asked once per setup, so daily trends and topic counts describe our
  test set, not real users.
- "Answered" means the reply passed our checks, not that a person graded it correct.


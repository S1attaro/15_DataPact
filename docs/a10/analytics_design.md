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

| Setup | Handbook median | Explain median | Handbook answered | Invalid replies | $ per 1,000 |
|---|---|---|---|---|---|
| Groq gpt-oss-20b (API) | 0.34 s | 0.36 s | 52/68 | 0 | $0.061 |
| SmolLM2 on CPU (Django) | 12.8 s | 14.2 s | 53/68 | 6 | $0.110 |
| SmolLM2 on GPU (Ollama) | 2.5 s | 2.7 s | 54/68 | 7 | $0.037 |
| Qwen2.5 14B on GPU (Ollama) | 2.7 s | 4.1 s | 54/68 | 0 | $0.043 |

- **P1/P2:** Groq is fastest by far. On our own machine, the GPU makes SmolLM2 about 5x faster than the CPU.
- **P3:** retrieval takes about 5 ms, under 1% of handbook time. Generation is the bottleneck.
- **B3:** 10 of the 68 questions are out of scope. Groq and Qwen2.5 refused all 10. SmolLM2 answered 2 to 3 of them, so its answered count is too high. A bigger model, or static pages for pricing and support, would fix this.
- **C1:** counting electricity only, slow models cost the most, so SmolLM2 on CPU is the most expensive setup. With hosting included, Groq is still cheapest (A7).
- "Answered" means the reply passed our checks, not that a person graded it correct.


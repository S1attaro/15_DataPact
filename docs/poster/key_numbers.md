# Poster key numbers

Generated from data/ai_logs.csv (308 requests, source: benchmark).
Re-run make_poster_charts.py after a new collect_ai_logs run.

## Populations

- All benchmark requests: 308 (cost and outcome figures use these).
- Requests that reached the model: 288 (every latency figure uses these).
- Retrieval-only requests (no passage matched, model never called): 20.

Overall latency, 288 requests that reached the model: mean 6,256 ms, median 2,674 ms, p95 32,004 ms.

## Latency (seconds, requests that reached the model)

| Feature | Engine | Median | p95 | Requests |
|---|---|---|---|---|
| explain | Groq gpt-oss-20b | 0.36 | 0.50 | 9 |
| explain | SmolLM2 (CPU) | 14.23 | 16.34 | 9 |
| explain | Qwen2.5 14B (GPU, Ollama) | 4.11 | 4.31 | 9 |
| explain | SmolLM2 (GPU, Ollama) | 2.66 | 2.74 | 9 |
| handbook | Groq gpt-oss-20b | 0.36 | 0.66 | 63 |
| handbook | SmolLM2 (CPU) | 22.59 | 35.76 | 63 |
| handbook | Qwen2.5 14B (GPU, Ollama) | 2.77 | 3.60 | 63 |
| handbook | SmolLM2 (GPU, Ollama) | 2.55 | 2.75 | 63 |

## Cost per 1,000 requests

| Engine | $ per 1,000 |
|---|---|
| SmolLM2 (CPU) | $0.1104 |
| SmolLM2 (GPU, Ollama) | $0.0365 |
| Qwen2.5 14B (GPU, Ollama) | $0.0434 |
| Groq gpt-oss-20b | $0.0606 |

## Handbook outcomes

| Outcome | Requests | Share |
|---|---|---|
| invalid | 13 | 4.8% |
| no_passages | 20 | 7.4% |
| not_found | 26 | 9.6% |
| ok | 213 | 78.3% |

Out-of-scope (pricing/support/legal) questions: 40 (14.7% of handbook traffic); 35 of 40 not answered (87.5%, rounded 88%): 20 no passage matched (model not called), 13 model said it did not know, 2 reply failed our checks; 5 answered anyway.

## Retrieval share of handbook time (requests that reached the model)

| Engine | Median search | Share of total handbook time |
|---|---|---|
| SmolLM2 (CPU) | 4.7 ms | 0.02% (slowest search 6 ms) |
| SmolLM2 (GPU, Ollama) | 5.2 ms | 3.53% (slowest search 5,526 ms) |
| Qwen2.5 14B (GPU, Ollama) | 5.3 ms | 0.18% (slowest search 9 ms) |
| Groq gpt-oss-20b | 4.6 ms | 1.32% (slowest search 11 ms) |

## A8 RAG improvement (manual grades)

| Setup | Answer score | Wrong refusals |
|---|---|---|
| baseline | 45.8 | 3 |
| top_k_1 | 41.7 | 4 |
| top_k_5 | 58.3 | 3 |
| strict_prompt | 62.5 | 0 |

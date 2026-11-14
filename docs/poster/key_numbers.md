# Poster key numbers

Generated from data/ai_logs.csv (308 requests, source: benchmark).
Re-run make_poster_charts.py after a new collect_ai_logs run.

## Latency (seconds, answered requests)

| Feature | Engine | Median | p95 | Requests |
|---|---|---|---|---|
| explain | Groq gpt-oss-20b | 0.36 | 0.50 | 9 |
| explain | SmolLM2 (CPU) | 14.23 | 16.34 | 9 |
| explain | Qwen2.5 14B (GPU, Ollama) | 4.11 | 4.31 | 9 |
| explain | SmolLM2 (GPU, Ollama) | 2.66 | 2.74 | 9 |
| handbook | Groq gpt-oss-20b | 0.34 | 0.62 | 68 |
| handbook | SmolLM2 (CPU) | 12.84 | 35.62 | 68 |
| handbook | Qwen2.5 14B (GPU, Ollama) | 2.73 | 3.57 | 68 |
| handbook | SmolLM2 (GPU, Ollama) | 2.55 | 2.75 | 68 |

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

Out-of-scope (pricing/support/legal) questions: 40 (14.7% of handbook traffic); 88% not answered.

Retrieval is 0.0% of handbook latency (median); generation is the rest.

## A8 RAG improvement (manual grades)

| Setup | Answer score | Wrong refusals |
|---|---|---|
| baseline | 45.8 | 3 |
| top_k_1 | 41.7 | 4 |
| top_k_5 | 58.3 | 3 |
| strict_prompt | 62.5 | 0 |

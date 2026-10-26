# DataPact — Multi-Model System Design

**A7 Part 1, Part 3: Multi-Model Routing Strategy.** Author: Ashok Chacko (achac), Team 15.

Companion to `multi_model_system.ipynb`. The notebook measures 15 models against 25 DataPact
prompts; this document decides which of them answers a given request, and when.

---

## 1. What is being routed

DataPact validates recurring data files against written contracts. The AI layer is asked for five
different things — the five prompt types benchmarked in Step 1.2:

| # | Prompt type | Triggered by | Output the app consumes |
|---|---|---|---|
| 1 | Classification | an analyst opening one failed check | JSON: `likely_cause`, `reason` |
| 2 | Structured extraction | a steward typing a rule in plain English | JSON: `dataset`, `column`, `rule_type`, `severity` |
| 3 | Summarization | a manager opening the run report | ≤2 sentences of prose |
| 4 | Prediction | the quality-history page | JSON: `trend`, `next_run` |
| 5 | Text generation | an analyst drafting a provider email | a 3–5 sentence email |

These differ in ways that matter for routing. Three return JSON the code must parse, so a
malformed reply is a **failure the system can detect for itself** — that detection is what makes
confidence-based routing possible here without a separate scoring model. Two return prose, where
a wrong answer is still well-formed and only a person notices.

They also differ in who sees the output. A classification stays inside the app. An email leaves
the building and reaches a data provider at another organisation, so the cost of a bad one is not
symmetric with the others.

## 2. The fleet

Five size categories, three models each, as defined in Step 1.1. Figures below are the measured
results from the team's A6 benchmark (`llm-test/ai_prototype_light.ipynb`, Colab T4, 8 balanced
classification inputs per model) — the same 15 models this assignment reuses. The test set is
balanced between the two labels, so **50% accuracy is what a model scores by answering one label
every time**; it means "not reasoning", not "half right".

| Category | Params | Valid structure | Accuracy | Sec/answer | Peak GB |
|---|---|---|---|---|---|
| Ultra-light | 0.13–0.36 B | 4% | 4% | 5.16 | 0.60 |
| Light | 0.49–0.51 B | 46% | 21% | 2.80 | 1.03 |
| Small | 1.10–1.48 B | 71% | 33% | 3.46 | 2.66 |
| Medium | 1.54–1.67 B | 62% | 33% | 2.67 | 3.29 |
| Large | 1.71–1.84 B | 88% | 50% | 2.85 | 3.66 |

Per-model, the picture is sharper than the category averages suggest:

| Model | Category | Valid | Accuracy | Sec | Note |
|---|---|---|---|---|---|
| SmolLM2-1.7B-Instruct | Large | 100% | **75%** | 1.99 | the only model that separated the two causes |
| Qwen1.5-1.8B-Chat | Large | 100% | 50% | 3.48 | perfect format, one label for all 8 |
| Qwen2.5-1.5B-Instruct | Medium | 100% | 50% | 3.24 | same |
| OLMo-2-1B-Instruct | Small | 100% | 50% | 1.90 | same, and fast |
| Qwen2.5-0.5B-Instruct | Light | 100% | 50% | 2.21 | same, on 1 GB |
| Falcon3-1B-Instruct | Medium | 0% | 0% | 2.07 | omits commas between JSON keys |
| H2O-Danube2-1.8B | Large | 62% | 25% | 3.08 | escapes `credit\_hours`, breaking JSON |
| SmolLM2-135M-Instruct | Ultra-light | 0% | 0% | 7.56 | repeats one sentence until cut off |

With the few-shot prompt chosen in A6, SmolLM2-1.7B reached **100% valid and 100% correct at
1.53 s** per answer, using ~602 prompt and ~54 new tokens.

Two conclusions drive every routing rule below.

**Structure is cheap; judgement is not.** Five models across four categories produce perfect JSON
and still score 50%. A 0.5 B model can be trusted to emit the right *shape* and cannot be trusted
to decide what goes in it. So the fleet splits by *what a tier is allowed to decide*, not by size
alone.

**Size is not the predictor.** The largest model tested (H2O-Danube2-1.8B) was the worst in its
category, and Falcon3-1B scored 0% — both on formatting habits learned in training, not on
reasoning. Tier membership is therefore assigned per model from measured scores, never from the
parameter count.

### Tiers used by the routing rules

| Tier | Model | Role |
|---|---|---|
| **T0 — screen** | Qwen2.5-0.5B-Instruct (Light, ~1 GB) | validity and shape checks only; never decides a label |
| **T1 — workhorse** | SmolLM2-1.7B-Instruct (Large, ~3.6 GB) | the default answer for every prompt type |
| **T2 — escalation** | `openai/gpt-oss-20b` via Groq | anything T1 fails, plus everything outbound |

`api.groq.com` is on PythonAnywhere's free-tier allowlist (verified against their published
list), so T2 is reachable from our deployed host. Its free tier is ~1,000 requests/day, which is
the budget the cost-aware rules below are written against.

The Ultra-light category is **deliberately unused**. At 4% valid structure it cannot be relied on
even to screen, and at 5.16 s/answer it is slower than the model that actually works. Benchmarking
it was still worthwhile: it establishes the floor below which the task is impossible, which is
what makes 0.5 B a defensible choice for T0 rather than a guess.

---

## 3. Step 3.1 — Five system scenarios

| # | Scenario | System condition | What matters most |
|---|---|---|---|
| S1 | **Interactive explanation** | one analyst, one violation, a person waiting | latency |
| S2 | **Post-run backfill** | a run finishes and emits 20–60 violations at once | throughput, cost per item |
| S3 | **Contract authoring** | a steward types a rule; output fills a form | exactness — a wrong field writes a wrong contract |
| S4 | **Outbound email drafting** | text that leaves the organisation | quality; errors are seen by a customer |
| S5 | **Degraded mode** | GPU gone, weights missing, or API quota spent | staying up at all |

**S1 — Interactive explanation.** The common case. An analyst clicks *Explain* on a failed check
and waits. One request, classification, user-visible latency. At 1.53 s, T1 is already inside the
window where a spinner feels responsive; a round trip to T2 would be slower and would be billed.

**S2 — Post-run backfill.** A validation run on the Monthly Enrollment Export finishes and
produces 40 violations. The reports page wants an explanation on each. Nobody is watching any
single one, so per-item latency is irrelevant and *total* cost and wall-clock are what matter.
This is the scenario that would quietly exhaust a 1,000/day API budget: one run can consume 4% of
it.

**S3 — Contract authoring.** A steward types *"credit hours should be between 0 and 24, block the
upload if not"* and the app extracts `dataset`, `column`, `rule_type`, `severity` into a form. The
cost of being wrong is asymmetric: a wrong `rule_type` writes a contract that silently mis-checks
every future file. The steward is waiting, but correctness outranks speed.

**S4 — Outbound email drafting.** The output is a message to a data provider at another
organisation. It is prose, so there is no JSON check to catch a bad one, and the only reviewer is
the analyst who asked for it. Volume is low — a handful a day.

**S5 — Degraded mode.** Any of: `transformers` cannot load the weights, the host has no GPU and
not enough RAM, or the Groq free tier is spent. On our own PythonAnywhere deployment this is the
*normal* state, not an exception — 512 MB cannot hold `torch`, never mind a 3.6 GB model. The
system must serve the page regardless.

---

## 4. Step 3.2 — Routing strategy per scenario

| Scenario | Routing strategy | Local models used | Hugging Face / API model | Expected benefit |
|---|---|---|---|---|
| S1 Interactive | T1 first. Validate the JSON. Escalate to T2 only on a failed parse, a bad enum, or >4 s. | SmolLM2-1.7B | gpt-oss-20b (on failure only) | ~1.5 s typical response; API billed only for genuine failures |
| S2 Backfill | T0 screens each violation for a usable prompt, then T1 runs the batch offline. Cap T2 escalations at 5% of the batch; beyond that, queue the rest for the next window. | Qwen2.5-0.5B, SmolLM2-1.7B | gpt-oss-20b, hard-capped | A 40-item run costs at most 2 API calls instead of 40 |
| S3 Authoring | T1 and T2 both answer; if the four extracted fields disagree, show the steward both and make them choose. | SmolLM2-1.7B | gpt-oss-20b (always) | Disagreement surfaces the uncertain cases instead of silently writing a wrong rule |
| S4 Email | T2 directly. T1 drafts only if the API is unavailable, and the draft is labelled as such. | SmolLM2-1.7B (fallback) | gpt-oss-20b (default) | The better writer handles the only text a customer reads; ~5 calls/day is negligible spend |
| S5 Degraded | Try T1, then T2, then neither: render the violation with no AI text and a plain note. | whichever loads | gpt-oss-20b | The page never 500s; the feature degrades, the product does not |

### The decision rule

```
route(request):
    if request.type == "Text generation":            # S4 — outbound
        return T2 or (T1 labelled "draft") or NONE

    if request.type == "Structured extraction":      # S3 — writes a contract
        a, b = T1(request), T2(request)
        return a if fields_match(a, b) else ASK_HUMAN(a, b)

    if request.batch_size > 5:                       # S2 — backfill
        if not T0.looks_answerable(request): return NONE
        answer = T1(request)
        if valid(answer): return answer
        return T2(request) if batch_escalations < 0.05 * batch_size else DEFER

    answer = T1(request)                             # S1 — interactive
    if valid(answer): return answer
    return T2(request)                               # S5 handled by T1/T2 both failing
```

`valid()` is the guardrail already specified in `README_AI.md`: parses as JSON, carries exactly
the expected keys, and every enum field holds an allowed value. It is the same check the Step 1.4
rubric scores as *structure* plus *instruction adherence*, which is what lets the benchmark
numbers predict the escalation rate.

**Routing conditions used, and why these:**

- **Prompt type** — the strongest signal available, because the five types differ in whether the
  output is machine-checkable and whether it leaves the organisation.
- **Self-validation outcome** — a free, exact confidence signal for the three JSON types. No
  separate scoring model is needed.
- **Batch size** — separates "a person is waiting" from "a job is running".
- **Running API count against the daily cap** — turns a budget into a routing input rather than a
  surprise at month end.
- **Model availability** — makes S5 a branch of the same rule instead of a special case.

Prompt length is deliberately *not* a routing condition. DataPact's prompts are built by the app
from fixed fields, so they are near-constant (~602 tokens few-shot); length carries no information
about difficulty here, unlike in a chatbot.

---

## 5. Step 3.3 — Evaluation

### 5.1 How the strategy improves latency

| Path | Measured / expected | When it applies |
|---|---|---|
| T1 answers (S1) | **1.53 s** | the common case |
| T1 fails → T2 (S1) | 1.53 s + API round trip | rare, bounded by T1's failure rate |
| T2 direct (S4) | one API round trip | ~5 requests/day |
| Backfill (S2) | not user-visible | offline |

Routing to T1 first is what keeps the interactive path fast. Two measured details matter:

**The few-shot prompt is both the most accurate and the fastest.** It scored 100%/100% at 1.53 s,
against 1.91 s for zero-shot, because the worked examples teach the model to answer briefly — 54
new tokens instead of 71. Accuracy and latency were not traded off against each other.

**Escalation is bounded by a measured quantity.** T1's valid-structure rate on the benchmark was
100%, so the expected escalation rate is low; where it is not zero in production, every escalation
adds one API round trip to a 1.53 s floor. The worst case is therefore bounded and known, not
open-ended.

Sending everything to T2 instead would replace a 1.53 s local call with a network round trip on
every request, and would make DataPact's latency depend on a third party's queue.

### 5.2 How it reduces cost

Using the measured token counts (~602 prompt + ~54 new ≈ **656 tokens per call**) and a
representative hosted rate of ~$0.15 per million tokens — Connor's Groq research has the confirmed
figure and should replace this placeholder:

| Policy | API calls/day at 20,000 requests | Monthly API spend |
|---|---|---|
| Everything to T2 | 20,000 | ~$59 |
| **Routed (T1 first, ~10% escalation)** | **~2,000** | **~$6** |
| Everything local | 0 | $0 API, ~$290 GPU |

Three separate savings:

1. **The escalation rule makes cost scale with T1's failure rate, not with traffic.** Doubling
   users doubles local compute, which is already paid for, and only doubles the small fraction
   that escalates.
2. **The S2 cap prevents the worst case.** Without it, one bad validation run — 40 violations the
   local model happens to mangle — spends 4% of the daily free tier in a few seconds. With it,
   that run costs at most 2 calls and the rest defer.
3. **The free tier becomes sufficient.** ~2,000 escalations/day is still above Groq's ~1,000/day
   free allowance, but within a factor of two, where the A6 arithmetic showed the alternative
   (an always-on GPU at ~$290/month) is roughly 5× more expensive at this scale. A GPU only wins
   once it is actually busy, which from the same arithmetic is around 60,000 generations/day.

### 5.3 How it maintains output quality

Routing could easily trade quality for cost. Three things stop it:

**The cheap tier is never allowed to decide anything.** T0 screens; it does not classify. This is
the direct consequence of the measurement: five models produce perfect JSON at 50% accuracy, so
"the output parsed" and "the output is right" are independent, and a tier that cannot be trusted
on the second must not be given work that depends on it.

**The expensive tier is used where errors are least recoverable**, not where traffic is highest.
Emails (S4) go to T2 because a customer reads them and no automated check will catch a bad one.
Contract extraction (S3) runs *both* tiers and asks a human when they disagree, because a wrong
`rule_type` corrupts every future validation of that dataset — the one place where paying twice is
cheaper than being wrong.

**Quality is checked on every single request, not sampled.** For the three JSON types, `valid()`
inspects each reply before the app uses it. This is DataPact's own idea applied to itself: the
product exists because unchecked data is trusted until something breaks downstream, and model
output is just another input that arrives claiming to be well-formed.

Where no automated check exists — summaries and emails — the design compensates with a human:
either the better model writes it (S4), or the analyst sees the draft before it goes anywhere. No
prose output is ever acted on automatically.

Finally, the whole system degrades to *no AI* rather than to *bad AI*. If T1 and T2 both fail, the
page shows the violation with the explanation omitted. An analyst who sees no explanation reads
the rows themselves, which is what they did before this feature existed. An analyst who sees a
confidently wrong explanation may not.

---

## 6. Limits of this design

Stated plainly, because the routing rules are only as good as what was measured.

- **The tier assignments rest on A6's classification benchmark** — 8 inputs per model, one prompt
  type. Step 1.5 of this assignment runs 25 prompts across all five types; **those per-type scores
  should be used to confirm or correct the tier table in §2**, particularly whether T0 is viable
  for screening and whether T1 holds up on summarization and prediction as well as it does on
  classification.
- **Eight inputs is a small sample.** SmolLM2-1.7B's 100% means "8 of 8", so the true failure rate
  is above zero and the escalation estimate of ~10% is a planning figure, not a measurement.
- **No model above 1.84 B was tested.** Free Colab crashed on 7–8 B models in A6. "Large" here
  means the largest the team could run, and a genuinely large local model might change the
  T1/T2 boundary.
- **The API price is a placeholder** pending Connor's confirmed Groq figure.
- **None of this is deployed.** The local tier cannot run on our PythonAnywhere free tier at all
  (§3, S5), so in production today every request is S5 or T2.

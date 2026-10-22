# DataPact: AI features (A6)

INFO 490 MG, Team 15. Route A (prompt engineering).

| Part | What | Where |
| --- | --- | --- |
| 1 | 15-model benchmark and Route A prompting | `llm-test/ai_prototype.ipynb`, results in `llm-test/results_light/` |
| 1 (follow-up) | 4 larger models (3.1B to 7.6B), same test | `llm-test/ai_prototype_3b_plus.ipynb`, results in `llm-test/results_3b_plus/` |
| 2.2 | Local Hugging Face model in a Django view | `data_quality/ai/` (`prompts.py`, `local_model.py`, `explain.py`), `data_quality/ai_views.py` |
| 2.3 | Second AI feature through an external API (Groq) | `data_quality/ai/groq_client.py`, same view and page |
| 3 | Production reflection | `docs/notes/notes.txt`, section "A6 - PART 3" |

## What the feature does

When a data file fails a contract rule, someone has to decide whether **the data
is wrong** or **the contract is out of date**. On a violation's page
(`/violations/<id>/explain/`), a signed-in user can ask a model for:

```json
{"explanation": "<one plain-English sentence>",
 "likely_cause": "DATA_ISSUE" | "CONTRACT_UPDATED",
 "suggested_action": "<one short sentence>"}
```

There are two engines, each with its own button when this server has it set
up:

* **Explain with AI**: `HuggingFaceTB/SmolLM2-1.7B-Instruct`, running in the
  Django process. The benchmark chose it: with the few-shot prompt (3 examples)
  it was the only result in the main benchmark (15 models zero-shot, then
  the top 3 with all four methods) with 8/8 valid replies and 8/8 correct
  causes. In the later 3B+ run, the 4
  larger models scored 4-6/8 on that same prompt; only Qwen2.5-7B matched
  8/8, and only with 12 examples and about 4 times the GPU memory (see
  `docs/notes/notes.txt`, section 48).
* **Explain with Groq (external API)**: the same prompt sent to Groq's hosted
  `openai/gpt-oss-20b` (or `GROQ_MODEL`), with fewer sample values (see
  "What is sent to Groq" below). This needs no GPU, so it also works on a
  small host where the local model is off.

Both buttons post to the same page (`engine=local` or `engine=groq`), and
both replies go through the same checks. On the production default (local
model off, Groq key set) only the Groq button is shown.

What the page says about each engine (UX Stage 2):

* **Before a click**, it shows a button only for an engine this server has
  set up: the local model switched on (`AI_LOCAL_ENABLED`), or a
  `GROQ_API_KEY` present. An engine that is not set up is shown as a
  disabled label with the reason ("The local model is switched off on this
  server."). This comes from settings alone: looking at the page never loads
  the model or contacts Groq, so "set up" is not a promise that the engine
  will answer.
* **While waiting**, a small script in the page writes what it is waiting
  for into a `role="status"` line ("Asking Groq… DataPact waits up to 20
  seconds for an answer.") and ignores a second click. If the visitor stops
  the request, the buttons unlock again after the longest the server should
  take (Groq's limit plus 10 seconds; 3 minutes for the local model).
  Without JavaScript the page works as before.
* **After a click**, the browser jumps to the answer (`#ai-suggestion`). A
  failure says which of these happened: the engine is not set up, Groq did
  not answer in time, Groq could not be reached, Groq's rate limit, or an
  error. "Try again" is offered only when trying again can help, and the
  other engine is offered when this server has it set up. A reply that fails
  the checks is not offered again from the same engine, since the same
  prompt most likely gets the same reply.

To get there: sign in, open **Contract search**, look up a dataset (for example
"Enrollment") under "Look up violations", and click **Explain**.

## Workflow

### Data input

1. A dataset is registered on the **Manage** page (`/datasets/manage/`, `DatasetForm`).
2. Its contract and validation rules (column, rule type, parameters such as
   `{"min": 0, "max": 24}`) are kept in the database and edited in the Django
   admin.
3. Each check of a file is a `ValidationRun`. Each rule it failed is a
   `Violation`, holding the failed-row count, up to a few sample values
   (`[{"row": 118, "value": -3}, ...]`) and a resolution that a person sets.
   The demo data comes from `python manage.py seed_demo`.

The AI never reads a raw file. It reads one stored `Violation` and its rule.

### Preprocessing (`data_quality/ai/prompts.py`)

The violation becomes the same five lines the benchmark tested:

```
Dataset: Monthly Enrollment Export
Column: credit_hours
Rule: RANGE {"min": 0, "max": 24}
Rows failed: 47 of 4,812 rows
Sample values: [-3, -1, -12]
```

Before it is used:

* The rule is written the way the notebook's examples write it
  (`format_rule`). Parameters that are not a JSON object count as no parameters.
* ASCII control characters in names and rule text (`\x00`-`\x1f` and
  `\x7f`, so newlines, carriage returns and tabs) become spaces, so a dataset
  or column name cannot add a fake line such as "Rule: ..." with an ordinary
  newline. A test checks `\n` and `\r\n`. Unicode line breaks (U+0085,
  U+2028, U+2029) are **not** replaced, so a name containing one could still
  look like a new line to a model.
* Lengths are capped: names at 120 characters, rules at 300.
* At most 5 sample values are used, each cut to 60 characters with ASCII
  control characters removed. They are then written as a JSON list, which
  escapes any other line break (U+2028 becomes ` `). Row numbers are
  dropped. Entries with no value are
  skipped, so the model never sees a null that was not recorded.
* The instructions, the 3 examples and the message layout are copied
  verbatim from the notebook, and a test (`PromptMatchesBenchmarkTests`)
  fails if they drift.

### What is sent to Groq (`data_quality/ai/groq_client.py`)

The local model sees up to 5 cleaned sample values. Groq sees the same
prompt with a much stricter `Sample values:` line.

Always sent:

* The fixed instructions and the 3 worked examples from the notebook (made-up
  data, not ours).
* The **dataset name**, the **column name** and the **rule as written in the
  contract**, which includes an ALLOWED_VALUES list, a REGEX pattern or a
  RANGE's numbers. These come from whoever set up the contract, not from the
  file. They get the same cleaning as for the local model (ASCII control
  characters, newlines included, become spaces; names cut at 120 characters,
  the rule at 300) and are otherwise
  sent as written. A contract that lists names or IDs in its rule would
  send them.
* The failed-row count, e.g. `47 of 4,812 rows`.

Values from the file are sent only when all of these hold:

* the rule is `ALLOWED_VALUES` or `TYPE_MATCH`;
* the value is text (never a number), plain ASCII, and at most 20 characters;
* ignoring case and surrounding spaces, it is one of these status words
  (`SAFE_CODES`): ACTIVE, INACTIVE, PENDING, APPROVED, REJECTED, CANCELLED,
  CANCELED, OPEN, CLOSED, COMPLETE, COMPLETED, ENROLLED, DROPPED, WITHDRAWN,
  AUDIT, LOW, MEDIUM, HIGH, CRITICAL, URGENT, YES, NO, Y, N, TRUE, FALSE, NA,
  N/A, NULL, NONE, UNKNOWN, TBD.

A passing value is sent exactly as written (so `" PENDING "` keeps its
spaces), and at most 3 are sent. For a `NOT_NULL` rule, missing values are
sent as `null`. Nothing else from the file is sent: no numbers, names, emails,
NetIDs, IDs, unknown codes or free text, and no `REGEX`, `UNIQUE` or `RANGE`
samples. The rule's own allowed values do not count as safe, because a
contract can list NetIDs or IDs. When no value passes, the line reads
`Sample values: "(not shared with the external API)"`.

With the demo data this means, for example, `["AUDIT", "AUDIT", "AUDIT"]` for
the new status, `["CRITICAL"]` (but not `"P1"`) for priority, `["n/a"]` for
a bad credit-hours type, and the placeholder for every RANGE and REGEX
violation.

The cost of this rule: Groq gets less evidence than the benchmark prompt
had. A genuinely new code that is not on the list (for example `CDS` or
`P1`) is withheld, so Groq has to judge from the rule and the row count
alone.

### Safety guardrails

**Against malicious input**

* Only a signed-in user can open the page (`@login_required`). Only a POST
  with a valid CSRF token runs a model, and a GET never does. The POST's
  `engine` field picks the model: `local` or `groq`. A POST with no `engine`
  field uses the local model; any other value gets a 400 and runs nothing.
* The page is HTML, not a JSON API, so the project still has exactly one
  public API endpoint.
* The cleaning above keeps file values on their own `Sample values:` line.
  Text such as "IGNORE ALL INSTRUCTIONS" stays a quoted value inside that
  line (a test checks this).
* The local model is a plain public model, loaded with no
  `trust_remote_code` and no pickle files.

**Against broken output** (`data_quality/ai/explain.py`, `parse_reply`)

* The reply is read with the benchmark's own scoring rule: the text from the
  first `{` to the last `}` must parse as JSON, contain the three keys, and
  have a `likely_cause` of `DATA_ISSUE` or `CONTRACT_UPDATED`.
* Each field must be non-empty text, and is capped at 300 characters.
* A reply that fails these checks is never shown. The page says the model
  could not give a reliable explanation instead.
* Everything shown is escaped by Django's autoescaping (no `|safe`).
* The answer is advice only. Nothing is written to the database, and the
  resolution stays whatever a person set (a test compares every row before
  and after).

**Against failures**

* Local model: torch and transformers are imported only on the first POST,
  never at start-up. A failed load waits 60 seconds before the next try, and
  any load or generation error gives a friendly 503.
* Groq: the key comes only from `GROQ_API_KEY` in `.env` (read in
  `settings/base.py`) and is sent only in the `Authorization` header. With
  the key blank, no request is made. A missing key, a timeout (20 s), no
  connection, a 429 rate limit, any other error status (a 400 included), or a body that is not the
  expected JSON all give a friendly 503 that names which of these it was
  (`AIUnavailable.kind`), for example "Groq did not answer within 20
  seconds." Any other 4xx (a revoked key, a retired model, a bad request)
  is "turned the request down", with no "try again", since the same request
  gets the same answer. No key, URL or error text reaches the page. The
  server log gets only the error type or HTTP status, never the key.
* The request asks for `temperature` 0, `response_format` `json_object`,
  `max_completion_tokens` 1024, and `reasoning_effort` "low" for gpt-oss
  models only. A 429 is not retried; the user can try again later.

**The one-hour cache** (`groq_client.explain_violation`)

* A good Groq answer is kept for one hour, so clicking again or reloading
  does not spend free-tier tokens. The cache key is a SHA-256 hash of the
  model name and the full prompt. A different model, or any change to the
  dataset, column, rule, row count or shared samples, makes a new key.
* Failures and replies that fail the checks are not cached, so the next
  click asks Groq again.
* Limits: it uses Django's default cache (in memory, `LocMemCache`), so each
  server process has its own copy, a restart empties it, and two workers can
  each ask Groq once. The key is the prompt, not the user or the
  violation: every signed-in user gets the same cached answer, and so does
  a different violation whose prompt is identical (same dataset, column,
  rule, counts and shared samples). Any signed-in user can already open
  any violation, so this shows them nothing new. With the key removed, the page
  answers 503 even if an answer is cached. Nothing is written to the
  database, and the local model's answers are not cached.
* Model weights are never committed: `.gitignore` covers `*.bin`,
  `*.safetensors` and `*.pt`. `.env` is ignored too.

## Running it

```bash
pip install -r requirements.txt   # includes torch, transformers, accelerate, python-dotenv
python manage.py migrate
python manage.py runserver
```

* **Local model:** on by default in development. The first click downloads
  the weights (about 3.4 GB) into the Hugging Face cache. It needs about 4 GB
  of free GPU memory, or about 7 GB of free RAM on CPU.
* **Groq:** put a free key from https://console.groq.com/keys in `.env` as
  `GROQ_API_KEY=...`. Without one, the page shows Groq as not set up and
  has no Groq button.
* **Production (PythonAnywhere):** install `requirements-deploy.txt` (no
  torch). The local model is off unless `AI_LOCAL_ENABLED=true`.

## What was verified, and what was not

| Check | Result |
| --- | --- |
| Automated tests (`python manage.py test`) | All 294 pass on `tejas/a6-groq-explain` (`ed26903`, 19 Oct 2026). The AI tests use a fake local model and fake Groq responses. The Groq tests cover the allowlist (names, NetIDs, IDs, emails, phone numbers and other numbers are withheld, in `safe_samples` and in the request body), the one-hour expiry, cache misses after a change, and every failure path. |
| **Real local model through Django** (19 Oct 2026, RTX 3050 Ti Laptop GPU, 4 GB) | Signed in over HTTP, looked up "Enrollment", and clicked Explain with AI on 3 violations. All 3 replies were valid and matched the cause a person had recorded. The first click took 46.0 s (loading the model); the next took 2.7 s and 2.1 s. With the model loaded, `nvidia-smi` showed 3,559 MiB of the GPU's 4,096 MiB in use (0 MiB before the server started). That is the whole GPU's usage, not the benchmark's peak-allocation figure. |
| Local model failure cases (same machine) | A model ID that does not exist, and `AI_LOCAL_ENABLED=false`: both gave the friendly 503, with the reason in the server log. |
| Groq with no key (live dev server) | Friendly 503; no request was sent. |
| **Real Groq call** | **Not verified for the current code.** Connor reported a working live call with his own key on the earlier Groq version (PR #30, "about 650 tokens per call", Groq's total for that version's prompt); that version sent up to 5 sample values from a separate endpoint. The current version (allowlist, explain-page button) has only been tested with fake responses. The request format follows Groq's API reference (19 Oct 2026). Groq's output quality on our 8 test inputs has not been measured. |

Example of a real local reply (violation: `credit_hours`, RANGE 0-24, 47 of
4,812 rows failed):

> **Explanation:** Some students are listed with credit hours that are not
> valid (negative or non-integer). **Likely cause:** Data issue. **Suggested
> action:** Ask the enrollment team to correct the credit hours in those rows.

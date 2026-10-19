# DataPact: AI features (A6)

INFO 490 MG, Team 15. Route A (prompt engineering).

| Part | What | Where |
| --- | --- | --- |
| 1 | 15-model benchmark and Route A prompting | `llm-test/ai_prototype.ipynb`, results in `llm-test/results_light/` |
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

There are two buttons:

* **Explain with AI**: `HuggingFaceTB/SmolLM2-1.7B-Instruct`, running in the
  Django process. The benchmark chose it: with the few-shot prompt (3 examples)
  it was the only model and method with 8/8 valid replies and 8/8 correct causes.
* **Explain with Groq (external API)**: the same prompt sent to Groq's hosted
  `openai/gpt-oss-20b`. This needs no GPU, so it also works on a small host
  where the local model is off.

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
* Control characters and newlines in names and rule text become spaces, so a
  dataset or column name cannot add a fake line such as "Rule: ...".
* Lengths are capped: names at 120 characters, rules at 300.
* At most 5 sample values are used, each cut to 60 characters with control
  characters removed. Row numbers are dropped. Entries with no value are
  skipped, so the model never sees a null that was not recorded.
* The instructions, the 3 examples and the message layout are copied
  verbatim from the notebook, and a test (`PromptMatchesBenchmarkTests`)
  fails if they drift.
* **Groq only:** sample values are replaced with
  `"(not shared with the external API)"`. Only the dataset, column, rule and
  row counts leave the server.

### Safety guardrails

**Against malicious input**

* Only a signed-in user can open the page (`@login_required`). Only a POST
  with a valid CSRF token runs a model, and a GET never does. The `engine`
  field must be `local` or `groq`; anything else gets a 400.
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
* Groq: the key comes only from `GROQ_API_KEY` in `.env`. A missing key, a
  timeout (20 s), no connection, a 429 rate limit, another error status, or a
  body that is not the expected JSON all give the same friendly 503. No key,
  URL or error text reaches the page, and the key is never logged.
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
  `GROQ_API_KEY=...`. Without one, the Groq button says it is not available.
* **Production (PythonAnywhere):** install `requirements-deploy.txt` (no
  torch). The local model is off unless `AI_LOCAL_ENABLED=true`.

## What was verified, and what was not

| Check | Result |
| --- | --- |
| Automated tests (`python manage.py test`) | All pass. The AI tests use a fake local model and fake Groq responses. |
| **Real local model through Django** (19 Oct 2026, RTX 3050 Ti Laptop GPU, 4 GB) | Signed in over HTTP, looked up "Enrollment", and clicked Explain with AI on 3 violations. All 3 replies were valid and matched the cause a person had recorded. The first click took 46.0 s (loading the model); the next took 2.7 s and 2.1 s. GPU memory in use: 3.56 GB. |
| Local model failure cases (same machine) | A model ID that does not exist, and `AI_LOCAL_ENABLED=false`: both gave the friendly 503, with the reason in the server log. |
| Groq with no key (live dev server) | Friendly 503; no request was sent. |
| **Real Groq call** | **Not done yet**: no key was available when this was written. The request format follows Groq's API reference (19 Oct 2026). Groq's output quality on our 8 test inputs has not been measured. |

Example of a real local reply (violation: `credit_hours`, RANGE 0-24, 47 of
4,812 rows failed):

> **Explanation:** Some students are listed with credit hours that are not
> valid (negative or non-integer). **Likely cause:** Data issue. **Suggested
> action:** Ask the enrollment team to correct the credit hours in those rows.

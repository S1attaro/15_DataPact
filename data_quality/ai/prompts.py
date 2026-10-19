"""
The prompt for explaining a violation - A6 Part 2.2, Tejas Jaggi.

INSTRUCTIONS, EXAMPLE_POOL, describe() and build_messages() are copied verbatim
from the benchmark notebook llm-test/ai_prototype.ipynb, where SmolLM2-1.7B with the few-shot
(3-example) prompt scored 8/8 valid and 8/8 correct. Change them only together
with the notebook: PromptMatchesBenchmarkTests fails if the two drift apart.

violation_to_case() is the DataPact part: it turns a stored Violation into the
same five text fields the notebook's test cases use. Sample values come from
uploaded files, so they are treated as untrusted: only the values (no row
numbers), at most MAX_SAMPLES of them, each cut to MAX_SAMPLE_CHARS, with
control characters removed.
"""

import json
import re

DEFAULT_SHOTS = 3
MAX_SAMPLES = 5
MAX_SAMPLE_CHARS = 60
MAX_NAME_CHARS = 120
MAX_RULE_CHARS = 300
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

# --- Copied from llm-test/ai_prototype.ipynb (do not edit here alone) ---

INSTRUCTIONS = (
    "You review failed data-quality checks for DataPact. A failure means either the incoming "
    "data is wrong (DATA_ISSUE) or the data is legitimate and the rule is out of date "
    "(CONTRACT_UPDATED).\n"
    "Reply with ONLY a JSON object, no other text, with exactly these keys:\n"
    '  "explanation": one plain-English sentence,\n'
    '  "likely_cause": "DATA_ISSUE" or "CONTRACT_UPDATED",\n'
    '  "suggested_action": one short sentence.'
)

EXAMPLE_POOL = [
    (dict(dataset="Weekly Sales Extract", column="quantity", rule='RANGE {"min": 1, "max": 1000}',
          failed="9 of 13,120 rows", samples="[0, -3, 0]"),
     dict(explanation="Some sales rows have a quantity of zero or below, which cannot happen for a real sale.",
          likely_cause="DATA_ISSUE", suggested_action="Ask the sales team to correct the quantities in those rows.")),
    (dict(dataset="Monthly Enrollment Export", column="college", rule='ALLOWED_VALUES ["LAS", "ENG", "BUS", "ACES"]',
          failed="220 of 4,812 rows", samples='["CDS", "CDS", "CDS"]'),
     dict(explanation="Many students are listed under CDS, which looks like a newly created college rather than a typo.",
          likely_cause="CONTRACT_UPDATED", suggested_action="Confirm CDS is a real college and add it to the allowed values.")),
    (dict(dataset="Sensor Readings - Lab 3", column="humidity_pct", rule='TYPE_MATCH {"type": "number"}',
          failed="4 of 8,640 rows", samples='["N/A", "err", "N/A"]'),
     dict(explanation="A few humidity readings are text error markers instead of numbers.",
          likely_cause="DATA_ISSUE", suggested_action="Check the sensor logger and re-export the affected readings.")),
    (dict(dataset="Facilities Work Orders", column="priority", rule='ALLOWED_VALUES ["LOW", "MEDIUM", "HIGH"]',
          failed="140 of 2,210 rows", samples='["URGENT", "URGENT", "URGENT"]'),
     dict(explanation="Work orders now use an URGENT priority that the contract does not list yet.",
          likely_cause="CONTRACT_UPDATED", suggested_action="Confirm URGENT is an official priority and add it to the contract.")),
    (dict(dataset="Library Circulation Log", column="checkout_date", rule="NOT_NULL",
          failed="2 of 9,800 rows", samples="[null, null]"),
     dict(explanation="Two checkouts are missing their date, which every checkout must have.",
          likely_cause="DATA_ISSUE", suggested_action="Find the missing dates in the circulation system and fix the export.")),
    (dict(dataset="Course Catalog Snapshot", column="credit_hours", rule='RANGE {"min": 1, "max": 5}',
          failed="18 of 2,100 rows", samples="[6, 6, 6]"),
     dict(explanation="Several courses are worth 6 credits, consistent with a newly approved capstone format.",
          likely_cause="CONTRACT_UPDATED", suggested_action="Confirm the 6-credit courses and raise the maximum to 6.")),
    (dict(dataset="Payroll Deductions Export", column="employee_id", rule="UNIQUE",
          failed="5 of 3,402 rows", samples='["E1001", "E1001", "E2044"]'),
     dict(explanation="Some employee IDs appear more than once, so the same people were exported twice.",
          likely_cause="DATA_ISSUE", suggested_action="Remove the duplicate rows and check why the export repeated them.")),
    (dict(dataset="Weekly Sales Extract", column="region", rule='ALLOWED_VALUES ["NORTH", "SOUTH", "EAST", "WEST"]',
          failed="1,500 of 13,120 rows", samples='["ONLINE", "ONLINE", "ONLINE"]'),
     dict(explanation="A large, consistent block of sales is tagged ONLINE, which looks like a new sales channel.",
          likely_cause="CONTRACT_UPDATED", suggested_action="Confirm ONLINE is a real region and add it to the contract.")),
    (dict(dataset="Monthly Enrollment Export", column="email", rule='REGEX "^[^@]+@illinois\\.edu$"',
          failed="7 of 4,812 rows", samples='["jdoe@illinois", "@illinois.edu"]'),
     dict(explanation="A few email addresses are incomplete and would not work.",
          likely_cause="DATA_ISSUE", suggested_action="Correct the malformed addresses at the source.")),
    (dict(dataset="Sensor Readings - Lab 3", column="sensor_id", rule='ALLOWED_VALUES ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"]',
          failed="720 of 8,640 rows", samples='["S9", "S9", "S9"]'),
     dict(explanation="Readings arrive steadily from a sensor S9, which suggests a new sensor was installed.",
          likely_cause="CONTRACT_UPDATED", suggested_action="Confirm sensor S9 exists and add it to the allowed list.")),
    (dict(dataset="Facilities Work Orders", column="cost_usd", rule='TYPE_MATCH {"type": "number"}',
          failed="3 of 2,210 rows", samples='["$1,200", "TBD"]'),
     dict(explanation="A few costs were typed as text with symbols or placeholders instead of numbers.",
          likely_cause="DATA_ISSUE", suggested_action="Re-enter those costs as plain numbers.")),
    (dict(dataset="Library Circulation Log", column="item_type", rule='ALLOWED_VALUES ["BOOK", "DVD", "JOURNAL"]',
          failed="410 of 9,800 rows", samples='["LAPTOP", "LAPTOP", "LAPTOP"]'),
     dict(explanation="Many loans are for laptops, which matches a new lending service the contract predates.",
          likely_cause="CONTRACT_UPDATED", suggested_action="Confirm laptop lending and add LAPTOP to the allowed values.")),
]



def describe(case):
    return (
        f"Dataset: {case['dataset']}\nColumn: {case['column']}\nRule: {case['rule']}\n"
        f"Rows failed: {case['failed']}\nSample values: {case['samples']}"
    )



def build_messages(case, n_shots):
    messages = []
    for i, (example, answer) in enumerate(EXAMPLE_POOL[:n_shots]):
        text = describe(example)
        if i == 0:
            text = INSTRUCTIONS + "\n\n" + text
        messages.append({"role": "user", "content": text})
        messages.append({"role": "assistant", "content": json.dumps(answer)})
    question = describe(case)
    if n_shots == 0:
        question = INSTRUCTIONS + "\n\n" + question
    messages.append({"role": "user", "content": question})
    return messages
# --- End of copied section ---


def format_rule(rule):
    """Write a rule the way the notebook's cases do, e.g. RANGE {"min": 0, "max": 24}.

    parameters is an admin-editable JSONField, so anything other than an object
    is read as no parameters instead of failing the page.
    """
    params = rule.parameters if isinstance(rule.parameters, dict) else {}
    kind = rule.rule_type
    if kind in ("RANGE", "TYPE_MATCH"):
        text = f"{kind} {json.dumps(params)}"
    elif kind == "ALLOWED_VALUES":
        text = f"{kind} {json.dumps(params.get('values', []))}"
    elif kind == "REGEX":
        text = f'{kind} "{params.get("pattern", "")}"'
    else:
        text = kind
    return clean_text(text, MAX_RULE_CHARS)


def clean_text(text, limit):
    """A name or rule on one line: control characters (newlines too) become spaces."""
    return _CONTROL.sub(" ", str(text))[:limit]


def clean_value(value):
    """One sample value, made safe to place in the prompt."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _CONTROL.sub("", str(value))[:MAX_SAMPLE_CHARS]


def violation_to_case(violation):
    """The five fields the benchmark prompt uses, built from a Violation."""
    rule = violation.rule
    samples = violation.sample_values if isinstance(violation.sample_values, list) else []
    # An entry with no "value" key is skipped, so the model never reads it as a recorded null.
    samples = [s for s in samples if not isinstance(s, dict) or "value" in s]
    values = [clean_value(s["value"] if isinstance(s, dict) else s) for s in samples[:MAX_SAMPLES]]
    return {
        "dataset": clean_text(rule.contract.dataset.name, MAX_NAME_CHARS),
        "column": clean_text(rule.column_name, MAX_NAME_CHARS),
        "rule": format_rule(rule),
        "failed": f"{violation.failed_row_count:,} of {violation.run.row_count:,} rows",
        "samples": json.dumps(values),
    }

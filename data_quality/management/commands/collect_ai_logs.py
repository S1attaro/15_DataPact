"""
Collect AI request logs for the A10 dashboard (Connor Slattery).

Benchmark mode (the real data) runs DataPact's two AI features through each
engine and measures every request: wall-clock latency, retrieval time and
real token counts (the model's own tokenizer, Groq's usage field, Ollama's
counters).

    python manage.py collect_ai_logs --engines local,groq,ollama:qwen2.5:14b

    local            SmolLM2 through data_quality/ai (the same code the pages use)
    groq             the Groq API, same prompt and settings as groq_client.py
    ollama:<model>   any model pulled into a local Ollama (http://localhost:11434)

What is asked:
    handbook   every question in data/a10_handbook_questions.json (68: the
               14 A8 test questions, variations, and out-of-scope ones)
    explain    every violation in the database, --explain-rounds times

Groq's answer cache is skipped here (the runner calls the API itself), so
every Groq row is a real call. --groq-limit caps them (free tier) and calls
are spaced --groq-gap seconds apart.

The measurements are real; the timestamps and user labels are not. Every
request runs in one sitting, so afterwards each row is given a time spread
over the last --days days (more on weekdays and in working hours, growing
slowly) and one of --users made-up users, so the user behavior charts have a
realistic shape. Those rows are marked source=benchmark.

Simulated mode needs no model at all:

    python manage.py collect_ai_logs --simulate

It draws rows from distributions based on our own measurements (A6 benchmark,
A9 real-handbook run: retrieval 6-20 ms, SmolLM2 0.4-5 s on a 4 GB laptop
GPU) and marks them source=simulated. Use it when no model can run.

Either way the rows go to --out (default data/ai_logs.csv). Add --load to
also replace the database's rows (same as running load_ai_logs after).
"""

import csv
import json
import math
import random
import time
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from data_quality.ai import explain, groq_client, handbook, handbook_a8, local_model, prompts, retrieval
from data_quality.ai.local_model import AIUnavailable
from data_quality.analytics.pricing import request_cost
from data_quality.analytics.recorder import estimate_tokens, messages_text, question_topic
from data_quality.management.commands.load_ai_logs import CSV_FIELDS
from data_quality.models import Violation

OLLAMA_URL = "http://localhost:11434/api/chat"
HANDBOOK_STATUS = {"answered": "ok", "not_found": "not_found", "no_passages": "no_passages", "invalid": "invalid"}


class CapturingGenerator:
    """Wraps the local generator to keep the last prompt and reply, for token counts."""

    def __init__(self, generator):
        self.generator = generator
        self.messages = None
        self.reply = ""

    def generate(self, messages):
        self.messages = messages
        self.reply = self.generator.generate(messages)
        return self.reply

    def count(self, text):
        try:
            return len(self.generator.tokenizer(text, add_special_tokens=False)["input_ids"])
        except Exception:
            return estimate_tokens(text)

    def prompt_tokens(self):
        if not self.messages:
            return 0
        try:
            text = self.generator.tokenizer.apply_chat_template(
                self.messages, add_generation_prompt=True, tokenize=False)
        except Exception:
            text = messages_text(self.messages)
        return self.count(text)


class Command(BaseCommand):
    help = "Measure the AI features on each engine (or simulate) and write data/ai_logs.csv."

    def add_arguments(self, parser):
        parser.add_argument("--engines", default="local,groq",
                            help="Comma list: local, groq, ollama:<model>. Default local,groq.")
        parser.add_argument("--features", default="handbook,explain")
        parser.add_argument("--questions", default=str(Path(settings.BASE_DIR) / "data" / "a10_handbook_questions.json"))
        parser.add_argument("--explain-rounds", type=int, default=3)
        parser.add_argument("--groq-limit", type=int, default=100)
        parser.add_argument("--groq-gap", type=float, default=2.5)
        parser.add_argument("--days", type=int, default=21)
        parser.add_argument("--users", type=int, default=9)
        parser.add_argument("--seed", type=int, default=490)
        parser.add_argument("--tz", default="America/Chicago", help="Time zone for the working-hours shape.")
        parser.add_argument("--simulate", action="store_true", help="No models: draw realistic rows instead.")
        parser.add_argument("--rows", type=int, default=650, help="How many rows --simulate draws.")
        parser.add_argument("--out", default=str(Path(settings.BASE_DIR) / "data" / "ai_logs.csv"))
        parser.add_argument("--load", action="store_true", help="Also load the file into the database.")

    def handle(self, *args, **options):
        self.rng = random.Random(options["seed"])
        if options["simulate"]:
            rows = self.simulate(options["rows"])
            source = "simulated"
        else:
            rows = self.benchmark(options)
            source = "benchmark"
        if not rows:
            raise CommandError("No requests were measured. Check the engines and the messages above.")
        self.spread(rows, options["days"], options["users"], ZoneInfo(options["tz"]))
        for row in rows:
            row["source"] = source
            row["cost_usd"] = str(request_cost(row["engine"], row["prompt_tokens"],
                                               row["completion_tokens"], row["latency_ms"]))
        rows.sort(key=lambda row: row["created_at"])
        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({**row, "created_at": row["created_at"].isoformat()})
        self.stdout.write(self.style.SUCCESS(f"Wrote {len(rows)} rows to {out}"))
        if options["load"]:
            call_command("load_ai_logs", str(out), stdout=self.stdout)

    # ------------------------------------------------------------------ benchmark

    def benchmark(self, options):
        engines = [name.strip() for name in options["engines"].split(",") if name.strip()]
        features = {name.strip() for name in options["features"].split(",")}
        self.groq_left = options["groq_limit"]
        self.groq_gap = options["groq_gap"]
        self.last_groq = 0.0
        rows = []

        questions = []
        if "handbook" in features:
            questions = json.loads(Path(options["questions"]).read_text(encoding="utf-8"))["questions"]
            if retrieval.handbook_status():
                self.stderr.write(f"Handbook search is not set up ({retrieval.handbook_status()}); "
                                  "set RAG_EMBEDDING_MODEL_ID in .env. Skipping handbook questions.")
                questions = []
        violations = []
        if "explain" in features:
            violations = list(Violation.objects.select_related(
                "rule", "rule__contract", "rule__contract__dataset", "run"))
            if not violations:
                self.stderr.write("No violations in the database (run seed_demo). Skipping explain.")
            violations = violations * max(1, options["explain_rounds"])

        for engine in engines:
            if engine == "local":
                try:
                    self.stdout.write("Loading the local model (the first time can take a minute)...")
                    local_model.get_generator()
                except AIUnavailable as exc:
                    self.stderr.write(f"Skipping local: {exc}")
                    continue
            self.stdout.write(f"Engine {engine}: {len(questions)} questions, {len(violations)} explain calls")
            for number, question in enumerate(questions, start=1):
                row = self.safe(self.handbook_row, engine, question)
                if row:
                    rows.append(row)
                self.progress(number, len(questions), "handbook")
            for number, violation in enumerate(violations, start=1):
                row = self.safe(self.explain_row, engine, violation)
                if row:
                    rows.append(row)
                self.progress(number, len(violations), "explain")
        return rows

    def progress(self, number, total, what):
        if number == total or number % 10 == 0:
            self.stdout.write(f"  {what}: {number}/{total}")

    def safe(self, method, engine, item):
        try:
            return method(engine, item)
        except GroqSpent:
            return None
        except Exception as exc:  # one bad request should not end a long run
            self.stderr.write(f"  {engine}: {type(exc).__name__}: {exc}")
            return None

    def row(self, feature, engine, model, **fields):
        base = {"feature": feature, "engine": engine.split(":")[0], "model_name": model, "user_label": "",
                "query_type": "", "input_chars": 0, "prompt_tokens": 0, "completion_tokens": 0,
                "retrieval_ms": 0.0, "latency_ms": 0.0, "status": "ok"}
        base.update(fields)
        base["latency_ms"] = round(base["latency_ms"], 2)
        base["retrieval_ms"] = round(base["retrieval_ms"], 2)
        return base

    # handbook ---------------------------------------------------------------

    def handbook_row(self, engine, question):
        topic = question_topic(question)
        if engine == "local":
            capture = CapturingGenerator(local_model.get_generator())
            started = time.perf_counter()
            try:
                answer = handbook.answer_question(question, generator=capture)
            except AIUnavailable:
                return self.row("handbook", engine, settings.AI_LOCAL_MODEL_ID, query_type=topic,
                                input_chars=len(question), status="error",
                                latency_ms=(time.perf_counter() - started) * 1000)
            return self.row("handbook", engine, settings.AI_LOCAL_MODEL_ID, query_type=topic,
                            input_chars=len(question), retrieval_ms=answer.search_ms,
                            latency_ms=(time.perf_counter() - started) * 1000,
                            prompt_tokens=capture.prompt_tokens() if capture.messages else 0,
                            completion_tokens=capture.count(capture.reply) if capture.reply else 0,
                            status=HANDBOOK_STATUS.get(answer.status, "invalid"))

        # Groq or Ollama: same retrieval and same prompt, a different model.
        started = time.perf_counter()
        hits = retrieval.get_provider().search(question, settings.RAG_TOP_K)
        search_ms = (time.perf_counter() - started) * 1000
        passages = tuple(p for p in hits if p.score >= settings.RAG_MIN_SCORE)
        if not passages:
            return self.row("handbook", engine, self.model_name(engine), query_type=topic,
                            input_chars=len(question), retrieval_ms=search_ms, latency_ms=search_ms,
                            status="no_passages")
        messages = handbook_a8.build_messages(question, [{"rank": p.rank, "text": p.text} for p in passages],
                                              system_prompt=handbook.SYSTEM_PROMPT)
        reply, prompt_tokens, completion_tokens = self.call_remote(engine, messages, json_reply=False)
        status, _ = handbook.check_reply(reply, passages)
        return self.row("handbook", engine, self.model_name(engine), query_type=topic,
                        input_chars=len(question), retrieval_ms=search_ms,
                        latency_ms=(time.perf_counter() - started) * 1000 - self.waited_ms,
                        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                        status=HANDBOOK_STATUS.get(status, "invalid"))

    # explain ----------------------------------------------------------------

    def explain_row(self, engine, violation):
        rule_type = violation.rule.rule_type
        if engine == "local":
            messages = prompts.build_messages(prompts.violation_to_case(violation), prompts.DEFAULT_SHOTS)
            capture = CapturingGenerator(local_model.get_generator())
            started = time.perf_counter()
            reply = capture.generate(messages)
            latency = (time.perf_counter() - started) * 1000
            result = explain.parse_reply(reply)
            return self.row("explain", engine, settings.AI_LOCAL_MODEL_ID, query_type=rule_type,
                            input_chars=len(messages_text(messages)), latency_ms=latency,
                            prompt_tokens=capture.prompt_tokens(), completion_tokens=capture.count(reply),
                            status="ok" if result else "invalid")
        messages = groq_client.build_messages(violation)
        started = time.perf_counter()
        reply, prompt_tokens, completion_tokens = self.call_remote(engine, messages, json_reply=True)
        result = explain.parse_reply(reply)
        return self.row("explain", engine, self.model_name(engine), query_type=rule_type,
                        input_chars=len(messages_text(messages)),
                        latency_ms=(time.perf_counter() - started) * 1000 - self.waited_ms,
                        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                        status="ok" if result else "invalid")

    # remote engines ---------------------------------------------------------

    def model_name(self, engine):
        return settings.GROQ_MODEL if engine == "groq" else engine.split(":", 1)[1]

    def call_remote(self, engine, messages, json_reply):
        """(reply text, prompt tokens, completion tokens) from Groq or Ollama."""
        self.waited_ms = 0.0
        if engine == "groq":
            return self.call_groq(messages, json_reply)
        if engine.startswith("ollama:"):
            body = {"model": engine.split(":", 1)[1], "messages": messages, "stream": False,
                    "options": {"temperature": 0, "num_predict": settings.AI_MAX_NEW_TOKENS}}
            if json_reply:
                body["format"] = "json"
            response = requests.post(OLLAMA_URL, json=body, timeout=300)
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"], data.get("prompt_eval_count", 0), data.get("eval_count", 0)
        raise CommandError(f"Unknown engine {engine!r}: use local, groq or ollama:<model>")

    def call_groq(self, messages, json_reply):
        if not settings.GROQ_API_KEY:
            raise CommandError("GROQ_API_KEY is not set in .env")
        if self.groq_left <= 0:
            raise GroqSpent()
        wait = self.groq_gap - (time.monotonic() - self.last_groq)
        if wait > 0:
            time.sleep(wait)
            self.waited_ms = wait * 1000
        body = {"model": settings.GROQ_MODEL, "messages": messages, "temperature": 0,
                "max_completion_tokens": groq_client.MAX_COMPLETION_TOKENS}
        if json_reply:
            body["response_format"] = {"type": "json_object"}
        if settings.GROQ_MODEL.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"
        self.last_groq = time.monotonic()
        self.groq_left -= 1
        response = requests.post(groq_client.API_URL, json=body, timeout=settings.GROQ_TIMEOUT_SECONDS,
                                 headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"})
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage", {})
        return (data["choices"][0]["message"]["content"] or "",
                usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))

    # ------------------------------------------------------------------ simulate

    def simulate(self, count):
        """Rows drawn from our own measured ranges (see the module docstring)."""
        rng = self.rng
        questions = json.loads((Path(settings.BASE_DIR) / "data" / "a10_handbook_questions.json")
                               .read_text(encoding="utf-8"))["questions"]
        rule_types = ["NOT_NULL", "TYPE_MATCH", "RANGE", "ALLOWED_VALUES", "REGEX", "UNIQUE"]

        def lognormal(median, spread):
            return median * math.exp(rng.gauss(0, spread))

        rows = []
        for _ in range(count):
            pick = rng.random()
            if pick < 0.55:  # handbook, local only (the app has no Groq handbook)
                question = rng.choice(questions)
                topic = question_topic(question)
                search = lognormal(9, 0.35)
                roll = rng.random()
                out_of_scope = topic == "out_of_scope"
                if roll < (0.30 if out_of_scope else 0.07):
                    rows.append(self.row("handbook", "local", settings.AI_LOCAL_MODEL_ID, query_type=topic,
                                         input_chars=len(question), retrieval_ms=search,
                                         latency_ms=search + rng.uniform(1, 4), status="no_passages"))
                    continue
                completion = int(min(160, max(12, rng.gauss(95, 40))))
                generate = completion * lognormal(27, 0.18) + rng.uniform(150, 400)
                if out_of_scope:
                    status = rng.choices(["not_found", "invalid", "ok"], [0.55, 0.30, 0.15])[0]
                else:
                    status = rng.choices(["ok", "not_found", "invalid", "error"], [0.84, 0.06, 0.08, 0.02])[0]
                rows.append(self.row("handbook", "local", settings.AI_LOCAL_MODEL_ID, query_type=topic,
                                     input_chars=len(question), retrieval_ms=search,
                                     latency_ms=search + (generate if status != "error" else rng.uniform(20, 80)),
                                     prompt_tokens=0 if status == "error" else int(rng.gauss(560, 70)),
                                     completion_tokens=0 if status == "error" else completion, status=status))
            else:  # explain, local or Groq
                engine = "groq" if rng.random() < 0.45 else "local"
                rule_type = rng.choices(rule_types, [0.20, 0.22, 0.18, 0.22, 0.10, 0.08])[0]
                prompt_chars = int(rng.gauss(2750, 160))
                if engine == "local":
                    completion = int(min(160, max(30, rng.gauss(72, 14))))
                    latency = completion * lognormal(27, 0.15) + rng.uniform(250, 600)
                    status = rng.choices(["ok", "invalid", "error"], [0.88, 0.09, 0.03])[0]
                    prompt_tokens = int(prompt_chars / 3.9)
                    model = settings.AI_LOCAL_MODEL_ID
                else:
                    completion = int(min(1024, max(80, rng.gauss(260, 70))))
                    latency = lognormal(820, 0.35) + completion * 1.1
                    status = rng.choices(["ok", "invalid", "error"], [0.95, 0.02, 0.03])[0]
                    prompt_tokens = int(prompt_chars / 3.7) + 70
                    model = settings.GROQ_MODEL
                if status == "error":
                    latency, prompt_tokens, completion = rng.uniform(150, 20000), 0, 0
                rows.append(self.row("explain", engine, model, query_type=rule_type,
                                     input_chars=prompt_chars, latency_ms=latency,
                                     prompt_tokens=prompt_tokens, completion_tokens=completion, status=status))
        return rows

    # ------------------------------------------------------------------ time and users

    def spread(self, rows, days, users, tz):
        """Give each row a believable time and user (see the module docstring)."""
        rng = self.rng
        now = timezone.now().astimezone(tz).replace(minute=0, second=0, microsecond=0)
        start = now - timedelta(days=days)
        day_weights = []
        for offset in range(days):
            day = start + timedelta(days=offset + 1)
            weekday = 1.0 if day.weekday() < 5 else 0.45
            day_weights.append(weekday * (0.6 + 0.8 * offset / max(1, days - 1)))  # slow growth
        hour_weights = [0.2] * 8 + [1.0, 1.6, 1.8, 1.5, 1.0, 1.4, 1.7, 1.6, 1.2, 0.8, 0.6, 0.5, 0.4, 0.3, 0.2, 0.2]
        people = [f"user-{n}" for n in range(1, users + 1)]
        people_weights = [1 / (rank ** 0.8) for rank in range(1, users + 1)]  # a few heavy users
        for row in rows:
            offset = rng.choices(range(days), day_weights)[0]
            hour = rng.choices(range(24), hour_weights)[0]
            row["created_at"] = (start + timedelta(days=offset + 1)).replace(hour=hour) + timedelta(
                minutes=rng.randrange(60), seconds=rng.randrange(60))
            if row["created_at"] > now:
                row["created_at"] = now - timedelta(minutes=rng.randrange(1, 600))
            row["user_label"] = rng.choices(people, people_weights)[0]


class GroqSpent(Exception):
    """--groq-limit reached; the remaining Groq requests are skipped quietly."""

"""
A10 - AI request logging and the analytics dashboard. Author: Connor Slattery.

No model is loaded: the AI calls are patched, so these tests check that a row
is written for each request (and never breaks the page), what the row holds,
the cost maths, the CSV loader and the dashboard page.
"""

import csv
import io
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from data_quality.ai.explain import Explanation
from data_quality.ai.handbook import HandbookAnswer
from data_quality.ai.local_model import AIUnavailable
from data_quality.analytics import pricing, recorder
from data_quality.analytics.charts import percentile
from data_quality.analytics.cost import cost_context
from data_quality.analytics_views import filtered_logs
from data_quality.management.commands.load_ai_logs import CSV_FIELDS
from data_quality.models import AIRequestLog, Violation


def make_log(**fields):
    values = dict(feature="explain", engine="groq", model_name="openai/gpt-oss-20b", status="ok",
                  latency_ms=1000, prompt_tokens=700, completion_tokens=250)
    values.update(fields)
    return recorder.record(values.pop("feature"), values.pop("engine"), values.pop("model_name"), **values)


class PricingTests(TestCase):
    @override_settings(ANALYTICS_GROQ_INPUT_PER_M=0.075, ANALYTICS_GROQ_OUTPUT_PER_M=0.30)
    def test_groq_is_priced_per_token(self):
        self.assertAlmostEqual(pricing.groq_cost(1_000_000, 1_000_000), 0.375)
        self.assertEqual(pricing.request_cost("groq", 1000, 1000, 5000), Decimal("0.000375"))

    @override_settings(ANALYTICS_GPU_WATTS=360, ANALYTICS_CPU_WATTS=150, ANALYTICS_KWH_PRICE=0.15)
    def test_local_is_priced_by_electricity_not_tokens(self):
        # GPU: 360 W for 10 s = 1 Wh = 0.001 kWh, at $0.15 = $0.00015
        self.assertAlmostEqual(pricing.local_cost(10_000), 0.00015)
        self.assertEqual(pricing.request_cost("ollama", 0, 0, 10_000), Decimal("0.00015"))
        # SmolLM2 runs on the CPU: 150 W for 10 s, at $0.15 = $0.0000625
        self.assertEqual(pricing.request_cost("local", 999, 999, 10_000), Decimal("0.0000625"))


class RecorderTests(TestCase):
    def test_record_saves_a_row_with_its_cost(self):
        row = make_log()
        self.assertEqual(AIRequestLog.objects.count(), 1)
        self.assertGreater(row.cost_usd, 0)
        self.assertEqual(row.source, "live")

    def test_record_never_raises(self):
        with patch.object(AIRequestLog.objects, "create", side_effect=RuntimeError("db down")):
            with self.assertLogs("data_quality.analytics.recorder", "WARNING"):
                self.assertIsNone(make_log())

    def test_users_are_stored_by_id_not_name(self):
        user = User.objects.create_user("alice", password="x-long-password-1")
        row = make_log(user=user)
        self.assertEqual(row.user_label, f"user-{user.pk}")
        self.assertNotIn("alice", row.user_label)

    def test_question_topics(self):
        self.assertEqual(recorder.question_topic("How much does a licence cost per seat?"), "out_of_scope")
        self.assertEqual(recorder.question_topic("Who do I call for support?"), "out_of_scope")
        self.assertEqual(recorder.question_topic("What does a not null rule check?"), "rules")
        self.assertEqual(recorder.question_topic("Which export should I use?"), "exports")
        self.assertEqual(recorder.question_topic("Hello there"), "other")

    def test_estimate_tokens(self):
        self.assertEqual(recorder.estimate_tokens(""), 0)
        self.assertEqual(recorder.estimate_tokens("a" * 400), 100)

    def test_percentile(self):
        self.assertEqual(percentile([], 95), 0.0)
        self.assertEqual(percentile([1, 2, 3, 4, 5], 50), 3)
        self.assertAlmostEqual(percentile(list(range(1, 101)), 95), 95.05)


class ViewLoggingTests(TestCase):
    """The two AI pages write one row per POST, and logging trouble never breaks them."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("analyst", password="a-long-password-9")
        call_command("seed_demo", stdout=io.StringIO())
        cls.violation = Violation.objects.filter(rule__rule_type="ALLOWED_VALUES").first()

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("data_quality:violation-explain", args=[self.violation.pk])

    @override_settings(GROQ_API_KEY="test-key")
    def test_explain_logs_an_answered_request(self):
        answer = Explanation("A new status.", "CONTRACT_UPDATED", "Add AUDIT to the contract.")
        with patch("data_quality.ai_views.groq_client.explain_violation", return_value=answer):
            response = self.client.post(self.url, {"engine": "groq"})
        self.assertEqual(response.status_code, 200)
        row = AIRequestLog.objects.get()
        self.assertEqual((row.feature, row.engine, row.status, row.query_type),
                         ("explain", "groq", "ok", "ALLOWED_VALUES"))
        self.assertGreater(row.prompt_tokens, 100)
        self.assertGreater(row.completion_tokens, 0)
        self.assertEqual(row.user_label, f"user-{self.user.pk}")

    def test_explain_logs_a_failed_request(self):
        with patch("data_quality.ai_views.explain.explain_violation", side_effect=AIUnavailable("off", kind="off")):
            response = self.client.post(self.url, {"engine": "local"})
        self.assertEqual(response.status_code, 503)
        row = AIRequestLog.objects.get()
        self.assertEqual((row.engine, row.status, row.prompt_tokens), ("local", "error", 0))

    def test_explain_logs_a_reply_that_failed_the_checks(self):
        with patch("data_quality.ai_views.explain.explain_violation", return_value=None):
            self.client.post(self.url, {"engine": "local"})
        self.assertEqual(AIRequestLog.objects.get().status, "invalid")

    def test_a_logging_failure_does_not_break_the_page(self):
        answer = Explanation("x", "DATA_ISSUE", "y")
        with patch("data_quality.ai_views.explain.explain_violation", return_value=answer), \
                patch("data_quality.ai_views.recorder.record", side_effect=RuntimeError("boom")), \
                self.assertLogs("data_quality.ai_views", "WARNING"):
            response = self.client.post(self.url, {"engine": "local"})
        self.assertEqual(response.status_code, 200)

    def test_get_does_not_log(self):
        self.client.get(self.url)
        self.assertFalse(AIRequestLog.objects.exists())

    def test_handbook_logs_topic_and_timings_but_not_the_question(self):
        answer = HandbookAnswer("not_found", "", (), search_ms=12.5, generate_s=0.4)
        question = "How much does a licence cost per seat?"
        with patch("data_quality.handbook_views.retrieval.handbook_status", return_value=None), \
                patch("data_quality.handbook_views.handbook.answer_question", return_value=answer):
            self.client.post(reverse("data_quality:handbook-ask"), {"question": question})
        row = AIRequestLog.objects.get()
        self.assertEqual((row.feature, row.status, row.query_type, row.retrieval_ms),
                         ("handbook", "not_found", "out_of_scope", 12.5))
        self.assertEqual(row.input_chars, len(question))
        for field in ("model_name", "user_label", "query_type"):
            self.assertNotIn("licence", getattr(row, field))

    def test_handbook_logs_when_it_cannot_run(self):
        with patch("data_quality.handbook_views.retrieval.handbook_status", return_value="off"):
            self.client.post(reverse("data_quality:handbook-ask"), {"question": "What is a contract?"})
        self.assertEqual(AIRequestLog.objects.get().status, "error")


class LoadAILogsTests(TestCase):
    def write_csv(self, rows):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8")
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        handle.close()
        self.addCleanup(Path(handle.name).unlink)
        return handle.name

    def good_row(self, **fields):
        row = {"created_at": "2026-11-10T14:00:00-06:00", "feature": "handbook", "engine": "local",
               "model_name": "SmolLM2", "user_label": "user-1", "query_type": "rules", "input_chars": "30",
               "prompt_tokens": "500", "completion_tokens": "80", "retrieval_ms": "9.1",
               "latency_ms": "2500", "status": "ok", "cost_usd": "0.00003", "source": "benchmark"}
        row.update(fields)
        return row

    def test_loads_and_replaces(self):
        make_log()
        path = self.write_csv([self.good_row(), self.good_row(engine="groq")])
        call_command("load_ai_logs", path, stdout=io.StringIO())
        self.assertEqual(AIRequestLog.objects.count(), 2)
        self.assertEqual(AIRequestLog.objects.filter(source="benchmark").count(), 2)

    def test_keep_live_keeps_real_use(self):
        make_log()
        path = self.write_csv([self.good_row()])
        call_command("load_ai_logs", path, "--keep-live", stdout=io.StringIO())
        self.assertEqual(AIRequestLog.objects.filter(source="live").count(), 1)
        self.assertEqual(AIRequestLog.objects.count(), 2)

    def test_rejects_bad_values(self):
        with self.assertRaisesMessage(CommandError, "engine must be one of"):
            call_command("load_ai_logs", self.write_csv([self.good_row(engine="gpt5")]), stdout=io.StringIO())
        with self.assertRaisesMessage(CommandError, "Line 2"):
            call_command("load_ai_logs", self.write_csv([self.good_row(latency_ms="fast")]), stdout=io.StringIO())
        self.assertFalse(AIRequestLog.objects.exists())

    def test_the_committed_file_loads(self):
        call_command("load_ai_logs", stdout=io.StringIO())
        self.assertGreater(AIRequestLog.objects.count(), 100)

    def test_simulate_writes_a_loadable_file(self):
        out = Path(tempfile.mkdtemp()) / "sim.csv"
        call_command("collect_ai_logs", "--simulate", "--rows", "40", "--out", str(out), "--load", stdout=io.StringIO())
        self.assertEqual(AIRequestLog.objects.filter(source="simulated").count(), 40)


class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("mohitg2", password="uiuc12345")
        now = timezone.now()
        make_log(created_at=now)
        make_log(engine="local", model_name="SmolLM2", created_at=now - timedelta(days=1))
        make_log(feature="handbook", engine="local", model_name="SmolLM2", query_type="rules",
                 retrieval_ms=9, created_at=now - timedelta(days=40))

    def test_needs_sign_in(self):
        response = self.client.get(reverse("data_quality:analytics"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("data_quality:login"), response["Location"])

    def test_test_account_can_open_it(self):
        self.assertTrue(self.client.login(username="mohitg2", password="uiuc12345"))
        response = self.client.get(reverse("data_quality:analytics") + "?days=all")
        self.assertEqual(response.status_code, 200)
        for text in ("System performance", "User behavior", "Cost", "Top cost drivers",
                     "spec-cost-by-model", "spec-tokens-by-type", "spec-cost-per-day"):
            self.assertContains(response, text)

    def test_empty_dashboard_says_so(self):
        AIRequestLog.objects.all().delete()
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("data_quality:analytics")), "No AI requests logged yet.")

    def test_filters(self):
        qs, filters = filtered_logs({"days": "30"})
        self.assertEqual(qs.count(), 2)
        qs, _ = filtered_logs({"days": "all", "engine": "local"})
        self.assertEqual(qs.count(), 2)
        qs, filters = filtered_logs({"days": "bogus", "engine": "bogus", "source": "bogus"})
        self.assertEqual(filters, {"days": "30", "engine": "", "source": ""})

    def test_cost_context(self):
        data = cost_context(AIRequestLog.objects.all())
        self.assertTrue(data["has_data"])
        self.assertEqual(len(data["charts"]), 3)
        self.assertGreater(data["groq_per_1000"], data["local_per_1000"])
        self.assertAlmostEqual(sum(row["share"] for row in data["drivers"]), 100, delta=0.5)

    def test_nav_link(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("data_quality:home")), 'href="/analytics/"')

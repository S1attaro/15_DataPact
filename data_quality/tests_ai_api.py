"""
Tests for the A6 Part 2.3 external-API explanation (Groq) - Tejas Jaggi.

No test talks to Groq: requests.post is replaced with a fake, so the suite
needs no key and no network. The fakes cover a good reply and every way the
call can fail (no key, timeout, no connection, 429, 5xx, a body that is not
JSON, and JSON in the wrong shape); each failure must reach the visitor as a
safe 503 that names no key, URL or error text.
"""

import json
import re
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from data_quality.ai import explain, groq_client, prompts
from data_quality.ai.local_model import AIUnavailable
from data_quality.tests_ai import VALID_REPLY, FakeGenerator, make_violation

TEST_KEY = "gsk_test-key-never-real-0000"


def groq_response(content=VALID_REPLY, status=200, body=None):
    """A stand-in for requests.Response with Groq's chat-completion shape."""
    response = Mock(status_code=status)
    if body is None:
        body = {"choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                             "finish_reason": "stop"}]}
    if isinstance(body, Exception):
        response.json.side_effect = body
    else:
        response.json.return_value = body
    return response


@override_settings(GROQ_API_KEY=TEST_KEY)
class GroqClientTests(TestCase):
    def setUp(self):
        self.violation = make_violation(samples=[{"row": 118, "value": "SECRET-SAMPLE-123"}])
        patcher = patch.object(groq_client.requests, "post", return_value=groq_response())
        self.post = patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_good_reply_is_read_with_the_benchmarks_rules(self):
        result = groq_client.explain_violation(self.violation)
        self.assertEqual(result.likely_cause, "DATA_ISSUE")
        self.assertTrue(result.explanation.startswith("Some credit_hours"))

    def test_the_request(self):
        groq_client.explain_violation(self.violation)
        (url,), kwargs = self.post.call_args
        self.assertEqual(url, "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(kwargs["headers"], {"Authorization": f"Bearer {TEST_KEY}"})
        self.assertEqual(kwargs["timeout"], settings.GROQ_TIMEOUT_SECONDS)
        body = kwargs["json"]
        self.assertEqual(body["model"], "openai/gpt-oss-20b")
        self.assertEqual(body["temperature"], 0)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertEqual(len(body["messages"]), 2 * prompts.DEFAULT_SHOTS + 1)

    def test_sample_values_are_never_sent(self):
        groq_client.explain_violation(self.violation)
        sent = json.dumps(self.post.call_args.kwargs["json"])
        self.assertNotIn("SECRET-SAMPLE-123", sent)
        question = self.post.call_args.kwargs["json"]["messages"][-1]["content"]
        self.assertIn("Sample values: " + groq_client.WITHHELD, question)
        self.assertIn("credit_hours", question)

    @override_settings(GROQ_MODEL="llama-3.1-8b-instant")
    def test_reasoning_effort_is_only_sent_to_models_that_accept_it(self):
        groq_client.explain_violation(self.violation)
        self.assertNotIn("reasoning_effort", self.post.call_args.kwargs["json"])

    @override_settings(GROQ_API_KEY="")
    def test_no_key_means_no_request(self):
        with self.assertRaises(AIUnavailable):
            groq_client.explain_violation(self.violation)
        self.post.assert_not_called()

    def test_every_failure_becomes_ai_unavailable_without_the_key(self):
        failures = {
            "timeout": requests.Timeout("read timed out"),
            "no connection": requests.ConnectionError("connection refused"),
            "rate limited": groq_response(status=429),
            "server error": groq_response(status=503),
            "bad request": groq_response(status=400),
            "not JSON": groq_response(body=ValueError("Expecting value")),
            "no choices": groq_response(body={"error": {"message": "x"}}),
            "empty choices": groq_response(body={"choices": []}),
            "content not text": groq_response(body={"choices": [{"message": {"content": None}}]}),
            "body is a list": groq_response(body=[1, 2]),
        }
        for name, outcome in failures.items():
            with self.subTest(name):
                if isinstance(outcome, Exception):
                    self.post.side_effect, self.post.return_value = outcome, None
                else:
                    self.post.side_effect, self.post.return_value = None, outcome
                with self.assertRaises(AIUnavailable) as caught:
                    groq_client.explain_violation(self.violation)
                self.assertNotIn(TEST_KEY, str(caught.exception))

    def test_a_reply_that_fails_the_checks_is_none_like_the_local_model(self):
        self.post.return_value = groq_response(content="I think the data is wrong.")
        self.assertIsNone(groq_client.explain_violation(self.violation))


@override_settings(GROQ_API_KEY=TEST_KEY)
class GroqExplainViewTests(TestCase):
    def setUp(self):
        self.violation = make_violation(samples=[{"row": 118, "value": "SECRET-SAMPLE-123"}])
        self.url = reverse("data_quality:violation-explain", args=[self.violation.pk])
        self.user = User.objects.create_user("analyst", password="Spindrift-Harbour-41")
        patcher = patch.object(groq_client.requests, "post", return_value=groq_response())
        self.post = patcher.start()
        self.addCleanup(patcher.stop)
        self.fake = FakeGenerator()
        patcher = patch.object(explain, "get_generator", return_value=self.fake)
        self.get_generator = patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_page_offers_both_engines(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertContains(response, 'name="engine" value="local"')
        self.assertContains(response, 'name="engine" value="groq"')
        self.post.assert_not_called()

    def test_groq_answers_without_loading_the_local_model(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"engine": "groq"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Some credit_hours values are negative")
        self.assertContains(response, "Groq API")
        self.assertContains(response, "does not change the recorded resolution")
        self.post.assert_called_once()
        self.get_generator.assert_not_called()

    def test_no_engine_still_means_the_local_model(self):
        self.client.force_login(self.user)
        self.client.post(self.url)
        self.post.assert_not_called()
        self.assertEqual(len(self.fake.calls), 1)

    def test_an_unknown_engine_is_a_bad_request(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"engine": "openai"})
        self.assertEqual(response.status_code, 400)
        self.post.assert_not_called()
        self.get_generator.assert_not_called()

    def test_signed_out_and_no_csrf_never_call_groq(self):
        self.assertEqual(self.client.post(self.url, {"engine": "groq"}).status_code, 302)
        self.client.handler.enforce_csrf_checks = True
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url, {"engine": "groq"}).status_code, 403)
        self.post.assert_not_called()

    def test_a_failure_is_a_friendly_503_that_leaks_nothing(self):
        self.post.side_effect = requests.Timeout("read timed out")
        self.client.force_login(self.user)
        with self.assertLogs("data_quality.ai_views", "WARNING") as logs:
            response = self.client.post(self.url, {"engine": "groq"})
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "The Groq API is not available", status_code=503)
        for text in (TEST_KEY, "read timed out", "api.groq.com"):
            self.assertNotContains(response, text, status_code=503)
        self.assertNotIn(TEST_KEY, "\n".join(logs.output))

    @override_settings(GROQ_API_KEY="")
    def test_no_key_is_a_friendly_503(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"engine": "groq"})
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "The Groq API is not available", status_code=503)
        self.post.assert_not_called()

    def test_groq_output_is_escaped(self):
        self.post.return_value = groq_response(content=json.dumps(
            {"explanation": "<script>alert(1)</script>", "likely_cause": "DATA_ISSUE", "suggested_action": "y"}))
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"engine": "groq"})
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")


class GroqSettingsTests(TestCase):
    def test_the_key_comes_only_from_the_environment(self):
        self.assertIsInstance(settings.GROQ_API_KEY, str)
        self.assertEqual(settings.GROQ_MODEL, "openai/gpt-oss-20b")
        source = (Path(settings.BASE_DIR) / "data_quality" / "ai" / "groq_client.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"gsk_[A-Za-z0-9]")

    def test_env_example_lists_the_settings_with_no_value(self):
        text = (Path(settings.BASE_DIR) / ".env.example").read_text(encoding="utf-8")
        self.assertRegex(text, re.compile(r"^GROQ_API_KEY=$", re.MULTILINE))
        self.assertRegex(text, re.compile(r"^#?\s*GROQ_MODEL=", re.MULTILINE))

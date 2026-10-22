"""
UX Stage 2 - the "Explain this violation" page tells people what is going on.
Author: Tejas Jaggi.

Before a click, the page says which AI engines this server has set up, from
settings alone: AI_LOCAL_ENABLED for the local model and a GROQ_API_KEY for
Groq. Neither is a promise that the engine will answer, so the page offers
only what it can know. After a click it says what actually happened (a
timeout, no connection, Groq's rate limit, an error, an engine that is off),
offers "try again" only where trying again can help, and points to the other
engine when there is one. The waiting message itself is shown by a small
script in the page; these tests check what the server sends, and the browser
behaviour was checked by hand (see the PR notes).

As in tests_ai.py and tests_ai_api.py, no model is loaded and nothing is sent
to Groq: the local model is a fake generator and requests.post is a fake.
"""

import re
from unittest.mock import patch

import requests
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from data_quality.ai import explain, groq_client, local_model
from data_quality.tests import StylesheetMixin
from data_quality.tests_ai import FakeGenerator, make_violation
from data_quality.tests_ai_api import TEST_KEY, groq_response


def tag_attributes(html, tag):
    """Every <tag ...> opening tag as a dict of its attributes, in page order."""
    return [dict(re.findall(r'([\w-]+)="([^"]*)"', match)) for match in re.findall(rf"<{tag}\b[^>]*>", html)]


def engine_buttons(html):
    return [b for b in tag_attributes(html, "button") if b.get("name") == "engine"]


def unavailable_labels(html):
    """(label, reason) of every _unavailable_action.html block on the page."""
    return re.findall(
        r'<span class="unavailable">\s*'
        r'<span class="btn btn--disabled">([^<]+)</span>\s*'
        r'<span class="unavailable__reason">([^<]+)</span>\s*</span>',
        html,
    )


def result_panel(html):
    """The part of the page from the AI suggestion panel on; it is the last panel."""
    return html[html.index('id="ai-suggestion"'):]


class ExplainPageTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.violation = make_violation()
        self.url = reverse("data_quality:violation-explain", args=[self.violation.pk])
        self.client.force_login(User.objects.create_user("analyst", password="Spindrift-Harbour-41"))
        self.fake = FakeGenerator()
        patcher = patch.object(explain, "get_generator", return_value=self.fake)
        self.get_generator = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(groq_client.requests, "post", return_value=groq_response())
        self.post = patcher.start()
        self.addCleanup(patcher.stop)

    def page(self, response):
        return response.content.decode()


# --- Why an engine could not answer ----------------------------------------------------------

@override_settings(GROQ_API_KEY=TEST_KEY)
class FailureKindTests(TestCase):
    """AIUnavailable carries a kind, so the page can say what happened without the error text."""

    def setUp(self):
        cache.clear()
        self.violation = make_violation()

    def kind_of_groq_failure(self, outcome):
        with patch.object(groq_client.requests, "post") as post:
            if isinstance(outcome, Exception):
                post.side_effect = outcome
            else:
                post.return_value = outcome
            with self.assertRaises(local_model.AIUnavailable) as caught:
                groq_client.explain_violation(self.violation)
        return caught.exception.kind

    def test_each_groq_failure_has_its_kind(self):
        kinds = [
            ("timeout", requests.Timeout("read timed out")),
            # ConnectTimeout is both a Timeout and a ConnectionError; it is a timeout.
            ("timeout", requests.ConnectTimeout("connect timed out")),
            ("unreachable", requests.ConnectionError("connection refused")),
            ("busy", groq_response(status=429)),
            ("error", groq_response(status=500)),
            ("error", groq_response(status=503)),
        ]
        for kind, outcome in kinds:
            with self.subTest(kind=kind, outcome=repr(outcome)):
                self.assertEqual(self.kind_of_groq_failure(outcome), kind)

    def test_groq_turning_the_request_down_is_rejected(self):
        # A revoked key (401/403), a retired model or a bad request (400/404):
        # asking again sends the same request and gets the same answer.
        for status in (400, 401, 403, 404):
            with self.subTest(status=status):
                self.assertEqual(self.kind_of_groq_failure(groq_response(status=status)), "rejected")

    def test_a_reply_in_the_wrong_shape_is_an_error(self):
        for body in (ValueError("Expecting value"), {"choices": []}, [1, 2]):
            with self.subTest(body=repr(body)):
                self.assertEqual(self.kind_of_groq_failure(groq_response(body=body)), "error")

    @override_settings(GROQ_API_KEY="")
    def test_no_key_is_off(self):
        with self.assertRaises(local_model.AIUnavailable) as caught:
            groq_client.explain_violation(self.violation)
        self.assertEqual(caught.exception.kind, "off")

    @override_settings(AI_LOCAL_ENABLED=False)
    def test_the_local_switch_is_off(self):
        with self.assertRaises(local_model.AIUnavailable) as caught:
            local_model.get_generator()
        self.assertEqual(caught.exception.kind, "off")

    @override_settings(AI_LOCAL_ENABLED=True)
    def test_a_local_load_failure_is_an_error(self):
        local_model.reset_for_tests()
        self.addCleanup(local_model.reset_for_tests)
        with patch.object(local_model, "HuggingFaceGenerator", side_effect=OSError("no weights")):
            with self.assertRaises(local_model.AIUnavailable) as caught:
                local_model.get_generator()
        self.assertEqual(caught.exception.kind, "error")

    def test_the_kind_defaults_to_error(self):
        self.assertEqual(local_model.AIUnavailable("anything").kind, "error")


# --- Before a click: what this server has set up --------------------------------------------

class EngineStatusTests(ExplainPageTestCase):
    @override_settings(AI_LOCAL_ENABLED=True, GROQ_API_KEY=TEST_KEY)
    def test_both_engines_get_a_button_and_a_plain_note(self):
        html = self.page(self.client.get(self.url))
        buttons = engine_buttons(html)
        self.assertEqual([b["value"] for b in buttons], ["local", "groq"])
        self.assertIn("btn--primary", buttons[0]["class"])
        self.assertNotIn("btn--primary", buttons[1]["class"])
        # btn--ghost is the dark top bar's button: light grey text, unreadable on a white panel.
        self.assertNotIn("btn--ghost", buttons[1]["class"])
        self.assertIn("SmolLM2-1.7B-Instruct, a local model on this server.", html)
        self.assertIn("openai/gpt-oss-20b, through the Groq API", html)
        self.assertEqual(unavailable_labels(html), [])

    @override_settings(AI_LOCAL_ENABLED=True, GROQ_API_KEY=TEST_KEY)
    def test_looking_at_the_page_never_runs_or_contacts_an_engine(self):
        self.client.get(self.url)
        self.get_generator.assert_not_called()
        self.post.assert_not_called()

    @override_settings(AI_LOCAL_ENABLED=False, GROQ_API_KEY=TEST_KEY)
    def test_with_the_local_model_off_groq_becomes_the_main_button(self):
        # The production default: the local model is off unless AI_LOCAL_ENABLED is set.
        html = self.page(self.client.get(self.url))
        buttons = engine_buttons(html)
        self.assertEqual([b["value"] for b in buttons], ["groq"])
        self.assertIn("btn--primary", buttons[0]["class"])
        self.assertEqual(unavailable_labels(html),
                         [("Explain with AI", "The local model is switched off on this server.")])
        # The button comes before the label, so the action that works is the first thing seen.
        self.assertLess(html.index('value="groq"'), html.index('class="unavailable"'))

    @override_settings(AI_LOCAL_ENABLED=True, GROQ_API_KEY="")
    def test_without_a_key_groq_says_it_is_not_set_up(self):
        html = self.page(self.client.get(self.url))
        self.assertEqual([b["value"] for b in engine_buttons(html)], ["local"])
        self.assertEqual(unavailable_labels(html),
                         [("Explain with Groq (external API)", "Groq is not set up on this server.")])
        self.assertNotIn("Groq receives", html)  # nothing is sent, so the data note is not needed

    @override_settings(AI_LOCAL_ENABLED=False, GROQ_API_KEY="")
    def test_with_no_engine_there_is_nothing_to_press(self):
        html = self.page(self.client.get(self.url))
        self.assertEqual(engine_buttons(html), [])
        self.assertEqual(len(unavailable_labels(html)), 2)
        self.assertIn("Neither AI engine is set up on this server", html)
        self.assertNotIn('id="explain-form"', html)

    @override_settings(AI_LOCAL_ENABLED=True, GROQ_API_KEY=TEST_KEY)
    def test_the_wording_never_claims_an_engine_is_working(self):
        html = self.page(self.client.get(self.url))
        # "running" too: the page reads settings, so it cannot know the model is loaded.
        for claim in ("online", "healthy", "ready", "connected", "working", "running"):
            with self.subTest(claim=claim):
                self.assertNotRegex(html, rf"(?i)\b{claim}\b")


# --- While waiting: what the page's script shows ------------------------------------------

class WaitingTests(ExplainPageTestCase):
    @override_settings(AI_LOCAL_ENABLED=True, GROQ_API_KEY=TEST_KEY, GROQ_TIMEOUT_SECONDS=7)
    def test_each_button_carries_what_to_say_while_its_engine_works(self):
        local, groq = engine_buttons(self.page(self.client.get(self.url)))
        self.assertEqual(local["data-wait"], "Asking the local model… The first answer after the "
                                             "server starts can take a minute or more while the model loads.")
        self.assertEqual(groq["data-wait"], "Asking Groq… DataPact waits up to 7 seconds for an answer.")

    @override_settings(AI_LOCAL_ENABLED=True, GROQ_API_KEY=TEST_KEY, GROQ_TIMEOUT_SECONDS=7)
    def test_each_button_says_when_the_page_stops_waiting(self):
        # If the visitor stops the request (Esc, the browser's Stop button), no
        # event tells the page, so the script unlocks it after this many seconds:
        # Groq's own time limit plus a margin, and three minutes for a model load.
        local, groq = engine_buttons(self.page(self.client.get(self.url)))
        self.assertEqual(groq["data-wait-seconds"], "17")
        self.assertEqual(local["data-wait-seconds"], "180")

    @override_settings(AI_LOCAL_ENABLED=True, GROQ_API_KEY=TEST_KEY)
    def test_the_page_has_an_empty_status_line_for_the_waiting_message(self):
        html = self.page(self.client.get(self.url))
        self.assertRegex(html, r'<p class="explain__status" id="explain-status" role="status"></p>')
        self.assertNotIn('aria-busy="true"', html)

    @override_settings(AI_LOCAL_ENABLED=True, GROQ_API_KEY=TEST_KEY)
    def test_the_form_sends_the_visitor_to_the_answer(self):
        html = self.page(self.client.get(self.url))
        (form,) = [f for f in tag_attributes(html, "form") if f.get("id") == "explain-form"]
        self.assertEqual(form["action"], self.url + "#ai-suggestion")
        self.assertEqual(form["method"], "post")

    @override_settings(AI_LOCAL_ENABLED=True, GROQ_API_KEY=TEST_KEY)
    def test_the_answer_panel_is_the_anchor_and_can_take_focus(self):
        html = self.page(self.client.post(self.url, {"engine": "groq"}))
        (panel,) = [s for s in tag_attributes(html, "section") if s.get("id") == "ai-suggestion"]
        self.assertEqual(panel["tabindex"], "-1")
        self.assertEqual(panel["aria-labelledby"], "ai-suggestion-title")
        self.assertIn('id="ai-suggestion-title"', html)


# --- After a click: what happened and what to do next ---------------------------------------

@override_settings(AI_LOCAL_ENABLED=True, GROQ_API_KEY=TEST_KEY, GROQ_TIMEOUT_SECONDS=20)
class OutcomeTests(ExplainPageTestCase):
    def ask(self, engine):
        response = self.client.post(self.url, {"engine": engine})
        return response, result_panel(self.page(response))

    def follow_up(self, panel):
        """(value, label) of each button in the answer panel; they submit the main form."""
        buttons = engine_buttons(panel)
        for button in buttons:
            self.assertEqual(button.get("form"), "explain-form")
        labels = re.findall(r'<button\b[^>]*name="engine"[^>]*>([^<]+)</button>', panel)
        return [(b["value"], label.strip()) for b, label in zip(buttons, labels)]

    def test_a_good_answer_has_no_follow_up_buttons(self):
        response, panel = self.ask("groq")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Some credit_hours values are negative", panel)
        self.assertEqual(self.follow_up(panel), [])

    def test_groq_timing_out_says_so_and_offers_another_try(self):
        self.post.side_effect = requests.Timeout("read timed out")
        response, panel = self.ask("groq")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Groq did not answer within 20 seconds.", panel)
        self.assertEqual(self.follow_up(panel),
                         [("groq", "Try Groq again"), ("local", "Ask the local model instead")])

    def test_no_connection_to_groq(self):
        self.post.side_effect = requests.ConnectionError("connection refused")
        response, panel = self.ask("groq")
        self.assertEqual(response.status_code, 503)
        self.assertIn("DataPact could not reach Groq.", panel)
        self.assertIn(("groq", "Try Groq again"), self.follow_up(panel))

    def test_groq_rate_limit_asks_the_visitor_to_wait(self):
        self.post.return_value = groq_response(status=429)
        response, panel = self.ask("groq")
        self.assertEqual(response.status_code, 503)
        self.assertIn("The Groq request limit has been reached for now. Wait a minute, then try again.", panel)
        self.assertIn(("groq", "Try Groq again"), self.follow_up(panel))

    def test_a_groq_error_or_unreadable_reply(self):
        for name, reply in {"server error": groq_response(status=500),
                            "not JSON": groq_response(body=ValueError("Expecting value"))}.items():
            with self.subTest(name):
                self.post.return_value = reply
                response, panel = self.ask("groq")
                self.assertEqual(response.status_code, 503)
                self.assertIn("Groq sent back an error or a reply DataPact could not read.", panel)
                self.assertIn(("groq", "Try Groq again"), self.follow_up(panel))

    def test_a_local_model_failure_can_be_tried_again(self):
        self.get_generator.side_effect = local_model.AIUnavailable("CUDA out of memory")
        response, panel = self.ask("local")
        self.assertEqual(response.status_code, 503)
        self.assertIn("The local model could not run on this server.", panel)
        self.assertEqual(self.follow_up(panel),
                         [("local", "Try the local model again"), ("groq", "Ask Groq instead")])

    def test_groq_turning_the_request_down_is_not_offered_again(self):
        self.post.return_value = groq_response(status=401)
        response, panel = self.ask("groq")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Groq turned the request down, so asking again will not help.", panel)
        self.assertEqual(self.follow_up(panel), [("local", "Ask the local model instead")])

    @override_settings(AI_LOCAL_ENABLED=False, GROQ_API_KEY="")
    def test_a_post_when_no_engine_is_set_up(self):
        # Only a page opened before both engines were switched off can send this.
        response, panel = self.ask("groq")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Groq is not set up on this server, so it cannot answer here.", panel)
        self.assertEqual(engine_buttons(self.page(response)), [])
        self.post.assert_not_called()

    @override_settings(GROQ_API_KEY="")
    def test_groq_without_a_key_is_not_offered_again(self):
        # A page opened before the key was removed can still post engine=groq.
        response, panel = self.ask("groq")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Groq is not set up on this server, so it cannot answer here.", panel)
        self.assertEqual(self.follow_up(panel), [("local", "Ask the local model instead")])
        self.post.assert_not_called()

    @override_settings(AI_LOCAL_ENABLED=False)
    def test_a_switched_off_local_model_is_not_offered_again(self):
        self.get_generator.side_effect = local_model.AIUnavailable("switched off", kind="off")
        response, panel = self.ask("local")
        self.assertEqual(response.status_code, 503)
        self.assertIn("The local model is switched off on this server, so it cannot answer here.", panel)
        self.assertEqual(self.follow_up(panel), [("groq", "Ask Groq instead")])

    def test_an_unusable_reply_is_not_offered_again_from_the_same_engine(self):
        # Both engines answer the same prompt the same way (greedy decoding,
        # temperature 0), so asking again would most likely repeat the reply.
        self.fake.reply = "not JSON at all"
        response, panel = self.ask("local")
        self.assertEqual(response.status_code, 200)
        self.assertIn("could not produce a reliable explanation", panel)
        self.assertEqual(self.follow_up(panel), [("groq", "Ask Groq instead")])

    @override_settings(GROQ_API_KEY="")
    def test_with_only_one_engine_a_permanent_failure_leaves_no_buttons(self):
        self.fake.reply = "not JSON at all"
        _, panel = self.ask("local")
        self.assertEqual(self.follow_up(panel), [])

    def test_no_failure_shows_the_key_the_url_or_the_error_text(self):
        failures = [requests.Timeout("read timed out SECRET-DETAIL"),
                    requests.ConnectionError("no route SECRET-DETAIL"),
                    groq_response(status=429), groq_response(status=500)]
        for failure in failures:
            with self.subTest(failure=repr(failure)):
                if isinstance(failure, Exception):
                    self.post.side_effect, self.post.return_value = failure, None
                else:
                    self.post.side_effect, self.post.return_value = None, failure
                with self.assertLogs("data_quality.ai_views", "WARNING"):
                    html = self.page(self.client.post(self.url, {"engine": "groq"}))
                for secret in (TEST_KEY, "SECRET-DETAIL", "api.groq.com", "Traceback"):
                    self.assertNotIn(secret, html)


class ExplainPageStyleTests(StylesheetMixin, TestCase):
    """The page's own classes exist in datapact.css (two of them never had a rule)."""

    def test_the_fact_lists_and_notes_are_styled(self):
        for selector in (".facts dt", ".facts dd", ".card__note", ".engine__note", ".explain__status"):
            with self.subTest(selector=selector):
                self.assertTrue(self.rule(selector).strip())

    def test_the_waiting_indicator_stops_moving_for_reduced_motion(self):
        reduced = self.css[self.css.index("@media (prefers-reduced-motion: reduce)"):]
        self.assertRegex(reduced, r"\.explain__status::before\s*\{[^}]*animation:\s*none")

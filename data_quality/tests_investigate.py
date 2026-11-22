"""
Product redesign, Stage 3D - the violation investigation journey.

Dataset detail -> violation lookup (on the Contracts page) -> the violation's
page, now "Investigate this violation". What these tests pin:

* One name for the page: Investigate (title, breadcrumb, table links, the
  "Next step" column). "Explain" survives only on the AI engine buttons,
  because what a model returns is an explanation.
* "What happens next", the human decision, on the page in every state:
  before a request, with no engine, after an answer, and after each kind of
  failure. No admin link.
* The rule by its readable name (the model's RuleType label) with the exact
  expression the model sees under it, unchanged.
* Row counts with thousands separators on all three pages; the stored numbers
  and the lookup's order are untouched.
* The two violation tables keep their desktop table and become labelled
  blocks on a phone (CSS), with nothing hidden.
* One entrance animation, only on a new usable AI answer, removed entirely
  under reduced motion; the form fields' focus transition is gone.

The browser side (no sideways scrolling at 390px, what is visible, focus) is
checked with Playwright and recorded in docs/redesign/stage_3d/. As in
tests_ai_page.py, no model is loaded and nothing is sent to Groq.
"""
import re
from html import unescape

import requests
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape

from data_quality.ai import local_model, prompts
from data_quality.models import ValidationRule, Violation
from data_quality.tests import StylesheetMixin
from data_quality.tests_ai import make_violation
from data_quality.tests_ai_api import TEST_KEY, groq_response
from data_quality.tests_ai_page import ExplainPageTestCase

ENGINE_BUTTON_LABELS = ("Explain with AI", "Explain with Groq (external API)")


def main_of(html):
    return html[html.index("<main"):html.index("</main>")]


def text_of(fragment):
    """Text a reader meets, including visually hidden text (screen readers read it)."""
    fragment = re.sub(r"<script\b.*?</script>", " ", fragment, flags=re.S)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def decision_of(html):
    start = html.index('<section class="panel decision"')
    return html[start:html.index("</section>", start)]


def record_of(html):
    """The record container's own HTML: from <div class="record"> to its matching </div>."""
    start = html.index('<div class="record">')
    depth = 0
    for tag in re.finditer(r"<(/?)div\b[^>]*>", html[start:]):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return html[start:start + tag.end()]
    raise AssertionError("the record container is never closed")


def table_rows(html, table_class):
    table = html[html.index(table_class):]
    body = re.split(r"<tbody\b[^>]*>", table, maxsplit=1)[1].split("</tbody>", 1)[0]
    return re.findall(r"<tr\b.*?</tr>", body, flags=re.S)


# --- Naming --------------------------------------------------------------------------------------

@override_settings(AI_LOCAL_ENABLED=True, GROQ_API_KEY=TEST_KEY)
class InvestigateNamingTests(ExplainPageTestCase):
    def test_the_page_title_heading_and_breadcrumb_say_investigate(self):
        html = self.page(self.client.get(self.url))
        self.assertIn("<title>Investigate violation - DataPact</title>", html)
        self.assertRegex(html, r"<h1[^>]*>\s*Investigate this violation\s*</h1>")
        crumbs = html[html.index('<nav class="breadcrumbs"'):]
        crumbs = crumbs[:crumbs.index("</nav>")]
        self.assertIn('<li aria-current="page">Investigate violation</li>', crumbs)
        self.assertIn(f'href="{self.violation.rule.contract.dataset.get_absolute_url()}"', crumbs)

    def test_explain_is_left_only_on_the_engine_buttons(self):
        main = text_of(main_of(self.page(self.client.get(self.url))))
        for label in ENGINE_BUTTON_LABELS:
            self.assertIn(label, main)
            main = main.replace(label, "")
        self.assertNotRegex(main, r"\bExplain\b")
        self.assertNotIn("Explain this violation", main)

    def test_the_engine_buttons_keep_their_names(self):
        """Investigate is what the person does; Explain is what the model does. Unchanged on purpose."""
        html = self.page(self.client.get(self.url))
        for label in ENGINE_BUTTON_LABELS:
            self.assertRegex(html, rf'<button\b[^>]*name="engine"[^>]*>{re.escape(label)}</button>')

    def test_the_route_and_url_name_are_unchanged(self):
        self.assertEqual(self.url, f"/violations/{self.violation.pk}/explain/")


class JourneyNamingTests(TestCase):
    def setUp(self):
        self.violation = make_violation()
        self.client.force_login(User.objects.create_user("analyst", password="Spindrift-Harbour-41"))

    def lookup_html(self):
        return self.client.post(reverse("data_quality:contract-search"), {"dataset": "", "resolution": ""}).content.decode()

    def detail_html(self):
        return self.client.get(self.violation.rule.contract.dataset.get_absolute_url()).content.decode()

    def test_both_tables_say_next_step_and_investigate(self):
        for name, html, table in (("detail", self.detail_html(), "vtable--detail"),
                                  ("lookup", self.lookup_html(), "vtable--lookup")):
            with self.subTest(page=name):
                self.assertIn('<th scope="col" role="columnheader">Next step</th>', html)
                self.assertNotIn("AI explanation", html)
                row = table_rows(html, table)[0]
                cell = re.search(r'<td role="cell" data-label="Next step" class="vtable__next">(.*?)</td>', row, flags=re.S).group(1)
                link = re.search(r'<a href="([^"]+)">(.*?)</a>', cell, flags=re.S)
                self.assertEqual(link.group(1), reverse("data_quality:violation-explain", args=[self.violation.pk]))
                self.assertEqual(text_of(link.group(2)),
                                 "Investigate credit_hours Range in enrollment.csv, "
                                 f"{self.violation.run.started_at:%Y-%m-%d}")

    def test_no_explain_label_is_left_on_the_dataset_or_lookup_pages(self):
        for name, html in (("detail", self.detail_html()), ("lookup", self.lookup_html())):
            with self.subTest(page=name):
                self.assertNotRegex(text_of(main_of(html)), r"\bExplain\b")


# --- What happens next, in every state ----------------------------------------------------------

DECISION_SENTENCES = (
    "What happens next",
    "it can suggest an explanation, a likely cause and an action",
    "A suggestion never changes the recorded resolution.",
    "A person decides.",
    "The decision is recorded in the DataPact admin,",
    "by someone with access to it.",
    "Recorded resolution",
)


@override_settings(AI_LOCAL_ENABLED=True, GROQ_API_KEY=TEST_KEY, GROQ_TIMEOUT_SECONDS=20)
class WhatHappensNextTests(ExplainPageTestCase):
    def assert_decision(self, response, expected_status=200):
        self.assertEqual(response.status_code, expected_status)
        html = self.page(response)
        decision = decision_of(html)
        text = text_of(decision)
        for sentence in DECISION_SENTENCES:
            self.assertIn(sentence, text)
        self.assertIn('<span class="badge badge--open">Open</span>', decision)
        self.assertIn("No decision has been recorded yet.", text)
        self.assertNotIn("/admin", main_of(html))  # words only: no link to the admin
        self.assertRegex(decision, r'<h2 class="panel__title" id="decision-title">What happens next</h2>')
        self.assertIn('aria-labelledby="decision-title"', decision)
        return html

    def ask(self, engine="groq"):
        return self.client.post(self.url, {"engine": engine})

    def test_before_any_request(self):
        html = self.assert_decision(self.client.get(self.url))
        self.assertNotIn('id="ai-suggestion"', html)

    @override_settings(AI_LOCAL_ENABLED=False, GROQ_API_KEY="")
    def test_with_no_engine_set_up(self):
        html = self.assert_decision(self.client.get(self.url))
        self.assertIn("Neither AI engine is set up on this server", html)

    def test_after_a_usable_answer(self):
        html = self.assert_decision(self.ask())
        self.assertIn("Some credit_hours values are negative", html)
        # The answer comes before the decision: facts, suggestion, decision.
        self.assertLess(html.index('id="ai-suggestion"'), html.index('class="panel decision"'))

    def test_after_a_timeout(self):
        self.post.side_effect = requests.Timeout("read timed out")
        self.assertIn("Groq did not answer within 20 seconds.", self.assert_decision(self.ask(), 503))

    def test_after_groq_cannot_be_reached(self):
        self.post.side_effect = requests.ConnectionError("connection refused")
        self.assertIn("DataPact could not reach Groq.", self.assert_decision(self.ask(), 503))

    def test_after_groq_turns_the_request_down(self):
        self.post.return_value = groq_response(status=401)
        self.assertIn("Groq turned the request down", self.assert_decision(self.ask(), 503))

    def test_after_an_error_or_unreadable_reply(self):
        self.post.return_value = groq_response(status=500)
        self.assertIn("Groq sent back an error", self.assert_decision(self.ask(), 503))

    def test_after_the_local_model_fails(self):
        self.get_generator.side_effect = local_model.AIUnavailable("CUDA out of memory")
        self.assertIn("The local model could not run on this server.", self.assert_decision(self.ask("local"), 503))

    @override_settings(AI_LOCAL_ENABLED=False)
    def test_after_asking_an_engine_that_is_off(self):
        self.get_generator.side_effect = local_model.AIUnavailable("switched off", kind="off")
        self.assertIn("The local model is switched off on this server", self.assert_decision(self.ask("local"), 503))

    def test_when_no_reliable_explanation_comes_back(self):
        self.fake.reply = "not JSON at all"
        html = self.assert_decision(self.ask("local"))
        self.assertIn("The model could not produce a reliable explanation", html)

    def test_a_decided_violation_says_a_person_recorded_it(self):
        Violation.objects.filter(pk=self.violation.pk).update(resolution=Violation.Resolution.DATA_ISSUE)
        decision = decision_of(self.page(self.client.get(self.url)))
        self.assertIn('<span class="badge badge--data_issue">Data issue</span>', decision)
        self.assertIn("A person has recorded this decision.", text_of(decision))

    def test_the_resolution_is_no_longer_repeated_in_the_facts(self):
        html = self.page(self.client.get(self.url))
        self.assertEqual(html.count("<dt>Recorded resolution</dt>"), 1)
        self.assertGreater(html.index("<dt>Recorded resolution</dt>"), html.index('class="panel decision"'))


# --- Stage 3D.1: the three layers form one record (DESIGN.md's record layers) -----------------

@override_settings(AI_LOCAL_ENABLED=True, GROQ_API_KEY=TEST_KEY, GROQ_TIMEOUT_SECONDS=20)
class RecordLayerTests(StylesheetMixin, ExplainPageTestCase):
    FACTS = '<h2 class="panel__title">The failed check</h2>'
    DECISION = '<section class="panel decision"'

    def suggestion_tag(self, record):
        tag = re.search(r'<section class="([^"]*)" id="ai-suggestion"', record)
        return tag.group(1).split() if tag else None

    def test_a_usable_answer_is_the_tinted_middle_layer_of_one_record(self):
        html = self.page(self.client.post(self.url, {"engine": "groq"}))
        record = record_of(html)
        self.assertEqual(html.count('<div class="record">'), 1)
        positions = [record.index(self.FACTS), record.index('id="ai-suggestion"'), record.index(self.DECISION)]
        self.assertEqual(positions, sorted(positions))  # facts, suggestion, decision, all inside the record
        self.assertIn("record__suggestion", self.suggestion_tag(record))
        self.assertIn("Some credit_hours values are negative", record)
        # Headings unchanged: each layer keeps its h2.
        self.assertEqual(re.findall(r'<h2 class="panel__title"[^>]*>([^<]+)</h2>', record),
                         ["The failed check", "AI suggestion", "What happens next"])

    def test_a_failure_keeps_its_layer_untinted(self):
        self.post.side_effect = requests.Timeout("read timed out")
        record = record_of(self.page(self.client.post(self.url, {"engine": "groq"})))
        self.assertIn("Groq did not answer within 20 seconds.", record)
        self.assertNotIn("record__suggestion", self.suggestion_tag(record))
        self.assertIn(self.DECISION, record)

    def test_an_unusable_reply_keeps_its_layer_untinted(self):
        self.fake.reply = "not JSON at all"
        record = record_of(self.page(self.client.post(self.url, {"engine": "local"})))
        self.assertNotIn("record__suggestion", self.suggestion_tag(record))

    def test_before_a_request_there_is_no_suggestion_layer(self):
        html = self.page(self.client.get(self.url))
        record = record_of(html)
        self.assertNotIn('id="ai-suggestion"', html)
        self.assertNotIn("record__suggestion", html)
        self.assertLess(record.index(self.FACTS), record.index(self.DECISION))

    @override_settings(AI_LOCAL_ENABLED=False, GROQ_API_KEY="")
    def test_with_no_engine_the_record_is_facts_and_decision(self):
        html = self.page(self.client.get(self.url))
        record = record_of(html)
        self.assertNotIn('id="ai-suggestion"', html)
        self.assertNotIn('id="explain-status"', html)  # nothing to wait for
        self.assertEqual(re.findall(r'<h2 class="panel__title"[^>]*>([^<]+)</h2>', record),
                         ["The failed check", "What happens next"])

    def test_the_waiting_line_sits_in_the_facts_layer_under_the_buttons(self):
        record = record_of(self.page(self.client.get(self.url)))
        form_end = record.index("</form>")
        status = record.index('<p class="explain__status" id="explain-status" role="status"></p>')
        self.assertLess(form_end, status)
        self.assertLess(status, record.index(self.DECISION))

    def test_the_record_uses_the_design_systems_edge_and_tint_only(self):
        block = self.css[self.css.index("/* Stage 3D.1, the record"):self.css.index("/* The one entrance on the page")]
        self.assertRegex(block, r"\.record \{[^}]*border: 1px solid var\(--line\);[^}]*border-radius: var\(--radius-sheet\);")
        self.assertIn(".record > .record__suggestion { background: var(--key-wash); }", block)
        self.assertIn(".record > .record__suggestion .panel__title { color: var(--accent-strong); }", block)
        self.assertIn(".record > .panel + .panel { border-top: 1px solid var(--line); }", block)
        # Stage 3D.2: no head rule inside the record, so the only lines are the edge and the separators.
        self.assertIn(".record > .panel > .panel__head { padding: 1.1rem 1.1rem 0; border-bottom: 0; }", block)
        self.assertIn(".record > .panel { margin: 0; border: 0; border-radius: 0; overflow: visible; }", block)
        css_only = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
        self.assertNotIn("key-rule", css_only)  # the suggestion's head rule went with the others
        for banned in ("box-shadow", "gradient", "border-radius: 50%"):
            self.assertNotIn(banned, css_only)


# --- The rule: readable name first, exact expression under it -----------------------------------

@override_settings(AI_LOCAL_ENABLED=False, GROQ_API_KEY="")
class RulePresentationTests(TestCase):
    CASES = (
        ("RANGE", {"min": 0, "max": 100000}, "Range"),
        ("ALLOWED_VALUES", {"values": ["ACTIVE", "WITHDRAWN"]}, "Allowed values"),
        ("REGEX", {"pattern": "^[A-Z]{3}-\\d+$"}, "Format (regex)"),
        ("NOT_NULL", {}, "Not null"),
        ("TYPE_MATCH", {"type": "integer"}, "Type match"),
        ("UNIQUE", {}, "Unique"),
    )

    def setUp(self):
        self.client.force_login(User.objects.create_user("analyst", password="Spindrift-Harbour-41"))

    def test_each_rule_type_shows_its_label_over_its_exact_expression(self):
        for rule_type, parameters, label in self.CASES:
            with self.subTest(rule_type=rule_type):
                violation = make_violation(rule_type=rule_type, parameters=parameters)
                html = self.client.get(reverse("data_quality:violation-explain", args=[violation.pk])).content.decode()
                rule = re.search(r"<dt>Rule</dt><dd>(.*?)</dd>", html, flags=re.S).group(1)
                self.assertEqual(label, dict(ValidationRule.RuleType.choices)[rule_type])
                self.assertIn(f'<span class="rule__name">{label}</span>', rule)
                self.assertIn(f'<code class="rule__expr">{escape(prompts.format_rule(violation.rule))}</code>', rule)
                self.assertLess(rule.index("rule__name"), rule.index("rule__expr"))

    def test_the_range_keeps_its_exact_bounds(self):
        violation = make_violation(parameters={"min": 0, "max": 100000})
        html = self.client.get(reverse("data_quality:violation-explain", args=[violation.pk])).content.decode()
        self.assertIn(escape('RANGE {"min": 0, "max": 100000}'), html)

    def test_showing_the_rule_changes_nothing_stored(self):
        violation = make_violation(parameters={"min": 0, "max": 24})
        self.client.get(reverse("data_quality:violation-explain", args=[violation.pk]))
        rule = ValidationRule.objects.get(pk=violation.rule.pk)
        self.assertEqual((rule.rule_type, rule.parameters), ("RANGE", {"min": 0, "max": 24}))
        self.assertEqual(prompts.format_rule(rule), 'RANGE {"min": 0, "max": 24}')


# --- Row counts with thousands separators -------------------------------------------------------

@override_settings(AI_LOCAL_ENABLED=False, GROQ_API_KEY="")
class NumberFormattingTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user("analyst", password="Spindrift-Harbour-41"))
        self.small = self.violation(23, 980)          # below 1,000
        self.mid = self.violation(1234, 13120)       # above 1,000 and 10,000
        self.big = self.violation(12345, 104000)     # above 10,000 and 100,000

    def violation(self, failed, rows):
        v = make_violation()
        Violation.objects.filter(pk=v.pk).update(failed_row_count=failed)
        type(v.run).objects.filter(pk=v.run.pk).update(row_count=rows)
        return Violation.objects.select_related("run", "rule__contract__dataset").get(pk=v.pk)

    def test_the_investigate_page(self):
        for v, expected in ((self.small, "23 of 980"), (self.mid, "1,234 of 13,120"), (self.big, "12,345 of 104,000")):
            with self.subTest(expected=expected):
                html = self.client.get(reverse("data_quality:violation-explain", args=[v.pk])).content.decode()
                self.assertIn(f'<dt>Rows failed</dt><dd class="facts__num">{expected}</dd>', html)

    def test_the_dataset_table(self):
        for v, expected in ((self.small, "23"), (self.mid, "1,234"), (self.big, "12,345")):
            with self.subTest(expected=expected):
                html = self.client.get(v.rule.contract.dataset.get_absolute_url()).content.decode()
                self.assertIn(f'<td role="cell" data-label="Failed rows" class="num">{expected}</td>', html)

    def test_the_lookup_table_keeps_its_numeric_order(self):
        html = self.client.post(reverse("data_quality:contract-search"), {"dataset": "", "resolution": ""}).content.decode()
        cells = re.findall(r'data-label="Failed rows" class="num">([^<]+)</td>', html)
        self.assertEqual(cells, ["12,345", "1,234", "23"])  # most failed rows first, by number, not by text

    def test_the_stored_numbers_do_not_change(self):
        self.client.get(reverse("data_quality:violation-explain", args=[self.big.pk]))
        self.client.post(reverse("data_quality:contract-search"), {"dataset": "", "resolution": ""})
        stored = Violation.objects.select_related("run").get(pk=self.big.pk)
        self.assertEqual((stored.failed_row_count, stored.run.row_count), (12345, 104000))


# --- The tables on a phone ----------------------------------------------------------------------

class ResponsiveTableTests(StylesheetMixin, TestCase):
    """The markup the phone layout needs, and the CSS that lays it out. Measured in a browser too."""

    def setUp(self):
        self.violation = make_violation()
        self.client.force_login(User.objects.create_user("analyst", password="Spindrift-Harbour-41"))

    def phone_block(self):
        css = self.css[self.css.index("/* ---- 22. investigation journey"):]
        start = css.index("@media (max-width: 40em)")
        return css[start:]

    def test_every_cell_is_labelled_with_its_column_name(self):
        pages = (
            ("detail", self.client.get(self.violation.rule.contract.dataset.get_absolute_url()).content.decode(), "vtable--detail"),
            ("lookup", self.client.post(reverse("data_quality:contract-search"),
                                        {"dataset": "", "resolution": ""}).content.decode(), "vtable--lookup"),
        )
        for name, html, table in pages:
            with self.subTest(page=name):
                head = html[html.index(table):]
                headers = re.findall(r'<th scope="col" role="columnheader"[^>]*>([^<]+)</th>',
                                     head[:head.index("</thead>")])
                row = table_rows(html, table)[0]
                labels = re.findall(r'<td role="cell" data-label="([^"]+)"', row)
                self.assertEqual(labels, headers)  # every field, in column order, under its own name
                self.assertIn("Resolution", labels)
                self.assertIn('role="table"', head[:200])
                self.assertIn('<tr role="row">', row)

    def test_the_phone_layout_hides_nothing_and_keeps_investigate_tappable(self):
        block = self.phone_block()
        self.assertIn(".vtable thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }", block)
        # Nothing is hidden on a phone: no cell, row, column or label.
        self.assertNotRegex(block, r"display:\s*none")
        self.assertIn("content: attr(data-label);", block)
        self.assertIn(".panel:has(.vtable) { overflow: visible;", block)
        self.assertRegex(block, r"\.vtable__next a \{[^}]*min-height: 2\.75rem;")

    def test_the_desktop_table_is_untouched(self):
        before_phone = self.css[self.css.index("/* ---- 22. investigation journey"):]
        before_phone = before_phone[:before_phone.index("@media (max-width: 40em)")]
        self.assertNotIn(".vtable", before_phone)  # every .vtable rule lives inside the phone query


# --- The one animation -------------------------------------------------------------------------

@override_settings(AI_LOCAL_ENABLED=True, GROQ_API_KEY=TEST_KEY, GROQ_TIMEOUT_SECONDS=20)
class AnswerEntranceTests(StylesheetMixin, ExplainPageTestCase):
    def section_classes(self, html):
        tag = re.search(r'<section class="([^"]*)" id="ai-suggestion"[^>]*>', html)
        return tag.group(1).split() if tag else None

    def test_only_a_new_usable_answer_gets_the_entrance(self):
        html = self.page(self.client.post(self.url, {"engine": "groq"}))
        self.assertIn("ai-answer--new", self.section_classes(html))

    def test_no_entrance_on_a_first_visit_or_any_failure(self):
        self.assertNotIn("ai-answer--new", self.page(self.client.get(self.url)))
        failures = {
            "timeout": lambda: setattr(self.post, "side_effect", requests.Timeout("t")),
            "unreachable": lambda: setattr(self.post, "side_effect", requests.ConnectionError("c")),
            "rejected": lambda: setattr(self.post, "return_value", groq_response(status=401)),
        }
        for kind, arrange in failures.items():
            with self.subTest(kind=kind):
                self.post.side_effect = None
                arrange()
                classes = self.section_classes(self.page(self.client.post(self.url, {"engine": "groq"})))
                self.assertNotIn("ai-answer--new", classes)
        self.post.side_effect = None
        self.fake.reply = "not JSON at all"
        self.assertNotIn("ai-answer--new", self.section_classes(self.page(self.client.post(self.url, {"engine": "local"}))))

    def test_the_entrance_is_small_quick_and_gpu_only(self):
        keyframes = re.search(r"@keyframes ai-answer-in \{(.*?)\n\}", self.css, flags=re.S).group(1)
        properties = set(re.findall(r"([a-z-]+):", keyframes))
        self.assertEqual(properties, {"opacity", "transform"})
        self.assertIn("translateY(6px)", keyframes)
        rule = re.search(r"\.ai-answer--new \{ animation: ([^;]+); \}", self.css).group(1)
        duration = int(re.search(r"(\d+)ms", rule).group(1))
        self.assertTrue(180 <= duration <= 200, duration)
        self.assertIn("var(--ease-out)", rule)

    def test_reduced_motion_removes_it_entirely(self):
        blocks = re.findall(r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\}", self.css, flags=re.S)
        self.assertTrue(any(".ai-answer--new { animation: none; }" in b for b in blocks))

    def test_it_is_the_only_animation_this_stage_adds(self):
        # Section 22 only: later stages' sections (23 onward) are checked by their own tests.
        start = self.css.index("/* ---- 22. investigation journey")
        section = self.css[start:self.css.index("/* ---- 23. insight pages")]
        self.assertEqual(re.findall(r"animation:\s*([^;]+);", section), ["ai-answer-in 190ms var(--ease-out) backwards", "none"])
        self.assertNotIn("transition:", section)

    def test_focus_still_moves_to_the_answer(self):
        html = self.page(self.client.post(self.url, {"engine": "groq"}))
        self.assertRegex(html, r'<section class="[^"]*" id="ai-suggestion" tabindex="-1"')
        self.assertIn('var answer = document.getElementById("ai-suggestion");', html)
        self.assertIn("answer.focus({ preventScroll: true });", html)

    def test_form_fields_focus_without_a_transition(self):
        rule = re.search(r"select,\s*textarea \{(.*?)\}", self.css, flags=re.S).group(1)
        self.assertNotIn("transition:", rule)  # the property; the comment there says why it went
        self.assertRegex(self.css, r"input:focus, select:focus, textarea:focus \{")


# --- The lookup keeps how it works --------------------------------------------------------------

class LookupFramingTests(TestCase):
    def setUp(self):
        make_violation()
        self.client.force_login(User.objects.create_user("analyst", password="Spindrift-Harbour-41"))

    def test_the_contracts_page_says_it_also_holds_the_lookup(self):
        html = self.client.get(reverse("data_quality:contract-search")).content.decode()
        subtitle = html[html.index('<p class="page__subtitle">'):]
        subtitle = subtitle[:subtitle.index("</p>")]
        self.assertIn('<a href="#violation-lookup">look up recorded violations</a>', subtitle)
        self.assertIn('<p class="lookup__intro">', html)

    def test_the_overview_link_still_chooses_open_without_running_the_lookup(self):
        response = self.client.get(reverse("data_quality:contract-search") + "?resolution=OPEN")
        self.assertEqual(response.context["violation_resolution"], "OPEN")
        self.assertIsNone(response.context["violation_results"])
        self.assertContains(response, "Open is selected. Press Look up violations to see them.")
        self.assertContains(response, '<form method="post" action="/contracts/search/#violation-results">')

    def test_pressing_look_up_still_runs_it(self):
        response = self.client.post(reverse("data_quality:contract-search"), {"dataset": "", "resolution": "OPEN"})
        self.assertEqual(len(response.context["violation_results"]), 1)

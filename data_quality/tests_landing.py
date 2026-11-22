"""
Product redesign, November 2026 - the public landing page and the
answer-sheet design system.
Author: Tejas Jaggi (with Claude Code).

What these tests pin down:

  - the landing page owns its first viewport (one h1, the landing surface
    attribute) and still sits inside base.html's shell;
  - the "re-key" specimen is real form controls that work without script:
    two radios in one group, contract v3 chosen by default, and the four
    recorded AUDIT failures from the demo workspace;
  - the honesty commitments in PRODUCT.md: unbuilt features are listed as
    planned, the AI answer is labelled illustrative, the pilot packages
    are labelled proposals, and no price in dollars appears;
  - signed out, the bar's section links point at sections that exist on
    the page; signed in, they are not shown;
  - the typefaces are self-hosted: nothing on the page or in the
    stylesheet asks a font host for anything;
  - the new colour tokens meet WCAG AA where they carry text or focus.

The rendered page was also checked in a browser at 1440 and 390 px
(docs/redesign/after/).
"""

import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from data_quality.tests import StylesheetMixin, contrast_ratio

HOME = "/"
SECTIONS = ("how-it-works", "ai", "use-cases", "pilot")


class LandingStructureTests(TestCase):
    def setUp(self):
        self.html = self.client.get(HOME).content.decode()

    def test_the_landing_page_owns_its_first_viewport(self):
        self.assertRegex(self.html, r'<main class="page" id="main" data-surface="landing">')
        self.assertEqual(self.html.count("<h1"), 1)
        self.assertIn("Give every dataset an answer key.", self.html)
        # The default page header (and its generic "DataPact" h1) is replaced.
        self.assertNotIn('class="page__header"', self.html)

    def test_every_section_has_a_heading(self):
        for section in re.findall(r"<section\b[^>]*>", self.html):
            with self.subTest(section=section):
                self.assertIn("aria-labelledby=", section)

    def test_the_re_key_control_works_without_script(self):
        radios = re.findall(r'<input class="rekey__input" type="radio" name="answer-key"[^>]*>', self.html)
        self.assertEqual(len(radios), 2)
        self.assertIn('id="key-v3" value="v3" checked', radios[0])
        self.assertNotIn("checked", radios[1])
        for key in ("key-v3", "key-v4"):
            with self.subTest(key=key):
                self.assertIn(f'<label class="rekey__option" for="{key}">', self.html)
        self.assertNotIn("answer-key", self.html.split("</figure>", 1)[1])

    def test_the_specimen_shows_the_four_recorded_failures_and_says_the_rest_are_representative(self):
        audit_rows = re.findall(r'<tr class="is-audit"><th scope="row">(\d+)</th>', self.html)
        self.assertEqual(audit_rows, ["118", "442", "2910", "3377"])
        self.assertIn("the other rows are representative", self.html)


class LandingHonestyTests(TestCase):
    def setUp(self):
        self.html = self.client.get(HOME).content.decode()

    def test_unbuilt_features_are_listed_as_planned(self):
        planned = self.html.split('id="mat-planned"', 1)[1].split("</section>", 1)[0]
        for feature in ("Uploading a delivered file", "automatically", "Editing contract rules"):
            with self.subTest(feature=feature):
                self.assertIn(feature, planned)

    def test_local_only_models_are_not_listed_as_live(self):
        live = self.html.split('id="mat-live"', 1)[1].split("</section>", 1)[0]
        self.assertNotIn("SmolLM2", live)
        self.assertNotIn("Handbook", live)

    def test_the_ai_answer_is_labelled_illustrative(self):
        self.assertIn("Illustrative answer", self.html)
        self.assertIn("never changes a record", self.html)

    def test_packages_are_proposals_with_no_invented_price(self):
        self.assertIn("proposals, not offers", self.html)
        self.assertNotRegex(self.html, r"\$\s?\d")

    def test_use_cases_are_not_presented_as_deployments(self):
        self.assertIn("none of them is a live university deployment", self.html)


class LandingNavigationTests(TestCase):
    def test_signed_out_section_links_point_at_sections_on_the_page(self):
        html = self.client.get(HOME).content.decode()
        nav = html[html.index('<nav class="mainnav"'):html.index("</nav>")]
        for section in SECTIONS:
            with self.subTest(section=section):
                self.assertIn(f'href="{reverse("data_quality:home")}#{section}"', nav)
                self.assertIn(f'id="{section}"', html)

    def test_signed_in_the_bar_has_no_section_links(self):
        self.client.force_login(User.objects.create_user("lander", password="pw"))
        html = self.client.get(HOME).content.decode()
        self.assertNotIn("mainnav__anchor", html)
        # The signed-in page still offers the workspace as its first action.
        self.assertIn(f'href="{reverse("data_quality:dataset-list")}">Open the dataset registry', html)


class SelfHostedFontTests(StylesheetMixin, TestCase):
    def test_no_font_host_is_contacted(self):
        html = self.client.get(HOME).content.decode()
        for host in ("fonts.googleapis", "fonts.gstatic", "use.typekit"):
            with self.subTest(host=host):
                self.assertNotIn(host, html)
                self.assertNotIn(host, self.css)

    def test_both_faces_are_declared_from_the_static_fonts_folder(self):
        faces = re.findall(r"@font-face\s*\{[^}]*\}", self.css)
        self.assertEqual(len(faces), 2)
        for name in ("archivo-var.woff2", "source-serif-4-var.woff2"):
            with self.subTest(font=name):
                self.assertTrue(any(f'url("../fonts/{name}")' in face for face in faces))

    def test_the_fonts_are_preloaded(self):
        html = self.client.get(HOME).content.decode()
        self.assertEqual(len(re.findall(r'<link rel="preload" href="[^"]+\.woff2" as="font" type="font/woff2" crossorigin>', html)), 2)


class AnswerSheetTokenTests(StylesheetMixin, TestCase):
    def test_links_and_text_read_on_the_key_wash(self):
        # The hero band is printed in --key-wash and carries links and body text.
        for token in ("accent", "accent-strong", "ink", "ink-soft"):
            with self.subTest(token=token):
                self.assertGreaterEqual(contrast_ratio(self.tokens[token], self.tokens["key-wash"]), 4.5)

    def test_text_and_focus_read_on_graphite(self):
        for token in ("on-bar", "on-bar-soft"):
            with self.subTest(token=token):
                self.assertGreaterEqual(contrast_ratio(self.tokens[token], self.tokens["bar"]), 4.5)
        self.assertGreaterEqual(contrast_ratio(self.tokens["key-on-bar"], self.tokens["bar"]), 3)

    def test_the_departure_mark_is_visible_on_a_sheet(self):
        self.assertGreaterEqual(contrast_ratio(self.tokens["signal"], self.tokens["surface"]), 3)

    def test_the_sheet_holds_still_for_reduced_motion(self):
        blocks = re.findall(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n\}", self.css, flags=re.S)
        self.assertTrue(any(re.search(r"\.sheet \*[^{]*\{[^}]*animation:\s*none", b) for b in blocks))

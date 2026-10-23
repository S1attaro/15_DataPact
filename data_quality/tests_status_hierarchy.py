"""
UX Stage 6, increment 2 - status colours, hierarchy, wording, busy buttons.
Author: Tejas Jaggi.

The increment 1 critique found the badge colours mixing two meanings: an
Active contract wore the "passed" green and a Draft wore the "error" amber,
so a contract's place in its lifecycle looked like the health of its data.
Run outcomes and violation resolutions had no badge at all. It also found:

  - Home's panel title ("How DataPact works") no bigger than the step names
    inside it, and the headline numbers (open violations, failed runs) no
    bigger than body text;
  - sentence-case labels next to Title Case ones ("Source Team");
  - the plain-button hover fill showing on the explain page's buttons while
    they are busy (aria-disabled="true"), so they looked clickable.

The colour families these tests pin down:

  lifecycle (Contract.Status)      Active: blue, ringed. Draft: white, dashed.
                                   Retired: plain grey.
  data health (ValidationRun)      Passed green, Failed red, Error amber.
  resolution (Violation)           Open red (needs a decision); Data issue and
                                   Contract updated plain grey (decided).

Every badge still shows its state in words; colour is never the only cue.
"""

import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from data_quality.models import Dataset
from data_quality.tests import SignedInClientMixin, StylesheetMixin, contrast_ratio
from data_quality.tests_discovery import SEARCH, DiscoveryData, results_rows

BADGE_GREY = "#eef0f3"  # the plain .badge background


def rem(value):
    match = re.fullmatch(r"\s*([\d.]+)rem\s*", value)
    assert match, f"not a rem value: {value!r}"
    return float(match.group(1))


class StatusColourTests(StylesheetMixin, TestCase):
    def badge(self, name):
        return self.rule(f".badge--{name}")

    def test_contract_lifecycle_does_not_borrow_the_data_health_colours(self):
        for name in ("active", "draft"):
            with self.subTest(status=name):
                rule = self.badge(name)
                for family in ("--pass-", "--fail-", "--warn-"):
                    self.assertNotIn(family, rule)
        # And no shared selector lists a lifecycle state beside a health one.
        for match in re.finditer(r"(?m)^([^{}\n]*\.badge--[^{}\n]*)\{", self.css):
            selector = match.group(1)
            lifecycle = re.search(r"\.badge--(active|draft|retired)\b", selector)
            health = re.search(r"\.badge--(passed|failed|error|open)\b", selector)
            self.assertFalse(lifecycle and health, selector)

    def test_run_outcomes_use_the_data_health_colours(self):
        for name, family in (("passed", "pass"), ("failed", "fail"), ("error", "warn")):
            with self.subTest(outcome=name):
                rule = self.badge(name)
                self.assertIn(f"var(--{family}-bg)", rule)
                self.assertIn(f"var(--{family}-ink)", rule)

    def test_an_open_violation_is_red_and_a_decided_one_is_plain(self):
        self.assertIn("var(--fail-bg)", self.badge("open"))
        for name in ("data_issue", "contract_updated"):
            self.assertNotRegex(self.css, rf"\.badge--{name}\b")

    def test_a_badge_stays_on_one_line(self):
        # "Contract updated" wrapped into a two-line pill in the lookup table.
        self.assertRegex(self.rule(".badge"), r"white-space:\s*nowrap")

    def test_a_named_badge_is_not_forced_into_capitals(self):
        self.assertRegex(self.badge("named"), r"text-transform:\s*none")

    def test_draft_and_active_are_told_apart_by_more_than_colour(self):
        # A dashed edge for a draft, a solid ring for the version in force.
        self.assertRegex(self.badge("draft"), r"outline:\s*1px dashed")
        self.assertRegex(self.badge("active"), r"box-shadow:\s*inset 0 0 0 1px")

    def test_every_badge_label_is_readable(self):
        pairs = {
            "active": (self.tokens["live-ink"], self.tokens["live-bg"]),
            "draft": (self.tokens["ink-soft"], self.tokens["surface"]),
            "retired": (self.tokens["ink-soft"], BADGE_GREY),
            "passed": (self.tokens["pass-ink"], self.tokens["pass-bg"]),
            "failed": (self.tokens["fail-ink"], self.tokens["fail-bg"]),
            "error": (self.tokens["warn-ink"], self.tokens["warn-bg"]),
        }
        for name, (ink, ground) in pairs.items():
            with self.subTest(badge=name):
                self.assertGreaterEqual(contrast_ratio(ink, ground), 4.5)


class StatusMarkupTests(DiscoveryData):
    def test_run_outcomes_are_badged_on_reports_and_quality_history(self):
        for name in ("data_quality:reports", "data_quality:quality-history"):
            html = self.client.get(reverse(name)).content.decode()
            for value, label in (("passed", "Passed"), ("failed", "Failed"), ("error", "Error")):
                with self.subTest(page=name, outcome=value):
                    self.assertRegex(
                        html, rf'<th scope="row">\s*<span class="badge badge--{value}">{label}</span>\s*</th>')

    def test_violation_resolutions_are_badged_on_the_dataset_page(self):
        html = self.client.get(reverse("data_quality:dataset-detail", args=[self.enrollment.pk])).content.decode()
        self.assertIn('<span class="badge badge--data_issue">Data issue</span>', html)

    def test_violation_resolutions_are_badged_in_the_lookup_results(self):
        rows = results_rows(self.lookup().content.decode())
        badges = [re.search(r'<span class="badge badge--(\w+)">([^<]+)</span>', row).groups() for row in rows]
        self.assertIn(("open", "Open"), badges)
        self.assertIn(("data_issue", "Data issue"), badges)

    def test_a_dataset_with_no_active_contract_is_not_called_a_draft(self):
        Dataset.objects.create(name="Unversioned Feed", owner=self.user, source_team="Ops")
        html = self.client.get(reverse("data_quality:dataset-cbv-base")).content.decode()
        self.assertIn('<span class="muted">None active</span>', html)
        self.assertNotIn("badge--draft", html)

    def test_the_active_version_keeps_its_lower_case_v(self):
        html = self.client.get(reverse("data_quality:dataset-cbv-base")).content.decode()
        self.assertIn('<span class="badge badge--active badge--named">v1</span>', html)


class HierarchyTests(StylesheetMixin, TestCase):
    def size(self, selector):
        value = re.search(r"(?:^|;)\s*font-size:\s*([^;]+)", self.rule(selector))
        self.assertIsNotNone(value, f"{selector} sets no font-size")
        return rem(value.group(1))

    def test_a_panel_title_is_larger_than_the_headings_inside_it(self):
        self.assertGreater(self.size(".panel__title"), self.size(".workflow__name"))

    def test_headline_numbers_stand_above_their_labels(self):
        stat = self.rule(".factlist--stats dt + dd")
        self.assertGreaterEqual(rem(re.search(r"font-size:\s*([^;]+)", stat).group(1)), 1.25)
        self.assertRegex(stat, r"font-variant-numeric:\s*tabular-nums")


class HierarchyMarkupTests(SignedInClientMixin, TestCase):
    def test_home_and_reports_mark_their_counts_as_stats(self):
        for name in ("data_quality:home", "data_quality:reports"):
            with self.subTest(page=name):
                self.assertContains(self.client.get(reverse(name)), '<dl class="factlist factlist--stats">')


class SentenceCaseTests(SignedInClientMixin, TestCase):
    """Labels, headers and buttons are sentence case; page names stay names."""

    def setUp(self):
        owner = User.objects.create_user("owner2", password="pw")
        self.dataset = Dataset.objects.create(name="Weekly Sales Extract", owner=owner, source_team="Finance")

    def test_no_title_case_labels_are_left(self):
        pages = (
            reverse("data_quality:dataset-list"),
            reverse("data_quality:dataset-cbv-base"),
            reverse("data_quality:dataset-manage"),
            reverse("data_quality:dataset-detail", args=[self.dataset.pk]),
        )
        old = ("Source Team", "Register Dataset", "Contract Versions", "Active Contract",
               "Column / Rule", "Upload New File", "View / Edit Rules", "New Contract Version")
        for url in pages:
            html = self.client.get(url).content.decode()
            for text in old:
                with self.subTest(url=url, text=text):
                    self.assertNotIn(text, html)

    def test_the_sentence_case_labels_are_there(self):
        manage = self.client.get(reverse("data_quality:dataset-manage")).content.decode()
        self.assertIn(">Source team</th>", manage)
        self.assertRegex(manage, r'<label for="[^"]+">Source team</label>')
        self.assertIn(">Register dataset</button>", manage)
        overview = self.client.get(reverse("data_quality:dataset-cbv-base")).content.decode()
        self.assertIn('<th scope="col" class="num">Contract versions</th>', overview)
        self.assertIn('<th scope="col">Active contract</th>', overview)


class BusyButtonTests(StylesheetMixin, TestCase):
    """The explain page marks its buttons aria-disabled while a model answers."""

    def test_a_busy_button_looks_unavailable(self):
        self.assertRegex(self.rule('button.btn[aria-disabled="true"]'), r"opacity:\s*0\.\d+")

    def test_a_busy_button_keeps_its_resting_colours_on_hover(self):
        plain = self.rule(':where(button).btn[aria-disabled="true"]:hover')
        self.assertRegex(plain, r"background:\s*var\(--surface\)")
        self.assertRegex(plain, r"border-color:\s*var\(--line-strong\)")
        primary = self.rule('.btn--primary[aria-disabled="true"]:hover')
        self.assertRegex(primary, r"background:\s*var\(--accent\)")
        # After the plain rule, so a busy primary button stays blue.
        self.assertLess(self.css.index(':where(button).btn[aria-disabled="true"]:hover'),
                        self.css.index('.btn--primary[aria-disabled="true"]:hover'))

    def test_a_busy_button_does_not_press_in(self):
        self.assertIn(':where(a, button:not([aria-disabled="true"])).btn:active', self.css)


class MotionTests(StylesheetMixin, TestCase):
    def test_buttons_move_only_transform_and_opacity(self):
        transition = re.search(r"transition:\s*([^;]+);", self.rule(".btn")).group(1)
        properties = {part.split()[0] for part in transition.split(",")}
        self.assertEqual(properties, {"transform", "opacity"})
        self.assertNotIn("all", transition)

    def test_reduced_motion_drops_the_press_movement(self):
        blocks = re.findall(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n\}", self.css, flags=re.S)
        self.assertTrue(any(re.search(r"\.btn:active\s*\{\s*transform:\s*none", b) for b in blocks))

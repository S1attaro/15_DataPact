"""
UX Stage 6, increment 3 - touch hover, the explain page's resolution, the
Quality History chart, and a scroll cue for wide tables.
Author: Tejas Jaggi.

  - A tapped button kept its hover fill on a phone, because touch screens
    fake :hover after a tap. Fills and row highlights now need a real
    pointer, (hover: hover) and (pointer: fine); the press (:active), the
    busy fade and the focus ring do not depend on it.
  - The explain page wrote the recorded resolution as plain text; it now
    uses the same badge as the dataset page and the lookup, and a missing
    or unknown value says so instead of drawing an empty or coloured pill.
  - The Quality History chart's notes were #8b959f (2.9:1), its 9-10pt text
    shrank to about 5px on a phone, and the page's panel heading repeated the chart's
    own title word for word. The chart keeps its title, axis labels and
    legend (A3 Section 4); the panel heading now says what the panel is.
  - A wide table scrolls inside its panel on a phone with nothing to say
    there is more; a shadow now shows at the edge that has more to see,
    and only when there is.
"""

import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from data_quality import charts
from data_quality.models import Contract, Dataset, ValidationRun, Violation
from data_quality.tests import SignedInClientMixin, StylesheetMixin, contrast_ratio
from data_quality.tests_discovery import DiscoveryData

HOVER_QUERY = "@media (hover: hover) and (pointer: fine)"


def media_blocks(css, query):
    """The bodies of every `query { ... }` block, braces matched."""
    bodies = []
    start = css.find(query)
    while start != -1:
        open_at = css.index("{", start)
        depth, i = 0, open_at
        while True:
            if css[i] == "{":
                depth += 1
            elif css[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        bodies.append(css[open_at + 1:i])
        start = css.find(query, i)
    return bodies


def outside(css, query):
    """The stylesheet with every `query { ... }` block cut out."""
    for body in media_blocks(css, query):
        css = css.replace(body, "")
    return css


def hex_colour(value):
    from matplotlib.colors import to_hex
    return to_hex(value)


class TouchHoverTests(StylesheetMixin, TestCase):
    GATED = (
        ":where(a, button).btn:hover",
        ".btn--primary:hover",
        ":where(button).btn[aria-disabled=\"true\"]:hover",
        ".btn--primary[aria-disabled=\"true\"]:hover",
        ".btn--ghost:hover",
        ".datatable tbody tr:hover",
    )

    def test_hover_fills_need_a_real_pointer(self):
        gated = "".join(media_blocks(self.css, HOVER_QUERY))
        rest = outside(self.css, HOVER_QUERY)
        for selector in self.GATED:
            with self.subTest(selector=selector):
                self.assertRegex(gated, r"(?m)^\s*" + re.escape(selector) + r"\s*\{")
                self.assertNotRegex(rest, r"(?m)^\s*" + re.escape(selector) + r"\s*\{")

    def test_press_busy_and_focus_do_not_depend_on_hover(self):
        rest = outside(self.css, HOVER_QUERY)
        for selector in (
            ':where(a, button:not([aria-disabled="true"])).btn:active',
            'button.btn[aria-disabled="true"]',
            ":focus-visible",
            ".topbar .menutoggle[aria-expanded=\"true\"]",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, rest)

    def test_a_busy_button_still_keeps_its_colours_after_the_plain_hover(self):
        gated = "".join(media_blocks(self.css, HOVER_QUERY))
        self.assertLess(gated.index(":where(a, button).btn:hover"),
                        gated.index(':where(button).btn[aria-disabled="true"]:hover'))
        self.assertLess(gated.index(".btn--primary:hover"),
                        gated.index('.btn--primary[aria-disabled="true"]:hover'))


class ExplainResolutionTests(DiscoveryData):
    def facts(self, violation):
        html = self.client.get(reverse("data_quality:violation-explain", args=[violation.pk])).content.decode()
        return html.split("<dt>Recorded resolution</dt>", 1)[1].split("</dd>", 1)[0]

    def test_each_resolution_is_shown_as_its_badge(self):
        cases = (
            (Violation.Resolution.OPEN, "open", "Open"),
            (Violation.Resolution.DATA_ISSUE, "data_issue", "Data issue"),
            (Violation.Resolution.CONTRACT_UPDATED, "contract_updated", "Contract updated"),
        )
        for value, css_name, label in cases:
            with self.subTest(resolution=value):
                Violation.objects.filter(pk=self.open_total.pk).update(resolution=value)
                self.assertIn(f'<span class="badge badge--{css_name}">{label}</span>',
                              self.facts(self.open_total))

    def test_an_unknown_value_shows_its_own_text_in_the_plain_badge(self):
        Violation.objects.filter(pk=self.open_total.pk).update(resolution="WONT_FIX")
        self.assertIn('<span class="badge badge--wont_fix">WONT_FIX</span>', self.facts(self.open_total))

    def test_a_missing_value_says_so(self):
        Violation.objects.filter(pk=self.open_total.pk).update(resolution="")
        facts = self.facts(self.open_total)
        self.assertIn('<span class="muted">Not recorded</span>', facts)
        self.assertNotIn("badge", facts)


class UnknownStatusStylesTests(StylesheetMixin, TestCase):
    def test_no_colour_rule_reaches_an_unknown_status(self):
        # An unknown resolution keeps the plain grey: nothing like
        # [class*="badge--"] colours whatever class happens to be written.
        self.assertNotRegex(self.css, r"\[class\*=\"badge--")


class ChartFigureTests(TestCase):
    """The figure behind /quality/run-outcomes.png."""

    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("owner3", password="pw")
        dataset = Dataset.objects.create(name="Monthly Enrollment Export", owner=owner, source_team="Registrar")
        contract = Contract.objects.create(dataset=dataset, version_number=1, status=Contract.Status.ACTIVE)
        for status in (ValidationRun.Status.FAILED, ValidationRun.Status.FAILED, ValidationRun.Status.PASSED):
            ValidationRun.objects.create(contract=contract, file_name="f.csv", row_count=10, status=status)

    def figure(self):
        return charts.build_run_outcomes_figure()

    def test_it_keeps_a_title_axis_labels_and_a_legend(self):
        ax = self.figure().axes[0]
        self.assertEqual(ax.get_title(), charts.RUN_OUTCOMES_TITLE)
        self.assertEqual(ax.get_xlabel(), "Outcome")
        self.assertEqual(ax.get_ylabel(), "Validation runs")
        self.assertEqual([t.get_text() for t in ax.get_legend().get_texts()], ["Passed", "Failed", "Error"])

    def test_bars_keep_their_order_counts_and_colours(self):
        ax = self.figure().axes[0]
        self.assertEqual([round(p.get_height()) for p in ax.patches], [1, 2, 0])
        self.assertEqual([hex_colour(p.get_facecolor()) for p in ax.patches],
                         ["#1d6b36", "#a12a2a", "#855c11"])

    def test_every_word_on_it_is_readable(self):
        fig = self.figure()
        ax = fig.axes[0]
        texts = [ax.title, ax.xaxis.label, ax.yaxis.label, *ax.get_xticklabels(), *ax.get_yticklabels(),
                 *ax.get_legend().get_texts(), *fig.texts]
        for text in texts:
            if not text.get_text():
                continue
            with self.subTest(text=text.get_text()):
                self.assertGreaterEqual(contrast_ratio(hex_colour(text.get_color()), "#ffffff"), 4.5)
                # The 792px image is shown about 310px wide on a 390px phone;
                # the old 9pt notes came out near 5 CSS px there.
                self.assertGreaterEqual(text.get_fontsize(), 11)

    def test_the_baseline_is_visible(self):
        spine = self.figure().axes[0].spines["bottom"]
        self.assertGreaterEqual(contrast_ratio(hex_colour(spine.get_edgecolor()), "#ffffff"), 3)

    def test_an_empty_chart_still_says_why_in_readable_text(self):
        ValidationRun.objects.all().delete()
        ax = self.figure().axes[0]
        notes = [t for t in ax.texts if "No validation runs" in t.get_text()]
        self.assertEqual(len(notes), 1)
        self.assertGreaterEqual(contrast_ratio(hex_colour(notes[0].get_color()), "#ffffff"), 4.5)


class QualityHistoryHeadingTests(SignedInClientMixin, TestCase):
    def test_the_panel_heading_does_not_repeat_the_charts_own_title(self):
        html = self.client.get(reverse("data_quality:quality-history")).content.decode()
        titles = re.findall(r'<h2 class="panel__title">([^<]+)</h2>', html)
        self.assertIn("As a chart", titles)
        self.assertNotIn(charts.RUN_OUTCOMES_TITLE.lower(), [t.lower() for t in titles])
        self.assertIn("The same numbers, as text", titles)


class ScrollCueTests(StylesheetMixin, TestCase):
    def test_a_panel_with_a_table_shades_the_edge_that_has_more(self):
        cue = self.rule(".panel:has(.datatable)")
        # Two covers that scroll with the content and two shadows that stay
        # with the box: a shadow only shows where a cover has moved off it.
        self.assertEqual(len(re.findall(r"\blocal\b", cue)), 2)
        self.assertEqual(len(re.findall(r"\bscroll\b", cue)), 2)
        self.assertIn("var(--surface)", cue)

    def test_the_cue_is_paint_only(self):
        cue = self.rule(".panel:has(.datatable)")
        for prop in ("overflow", "width", "padding", "margin", "pointer-events", "position"):
            with self.subTest(prop=prop):
                self.assertNotRegex(cue, rf"(?m)^\s*{prop}\s*:")

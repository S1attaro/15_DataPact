"""
UX Stage 6, increment 1 - shared component foundations.
Author: Tejas Jaggi.

An Impeccable critique of every page (two independent reviews, one of them
the mechanical detector run in the browser) found that the shared pieces
were drifting rather than any one page being wrong:

  - `.datatable th` styled every header cell, so the dataset and outcome
    names that head each row on Reports and Quality History came out as
    small grey capitals on a grey band that stopped partway across the row;
  - panel titles, column headers and fact labels were all 0.68-0.75rem
    capitals, so a panel's title was no bigger than its table's headers,
    and form labels were capitals too;
  - links had no base rule (browser blue and visited purple wherever no
    local rule reached), only <button> primary buttons had a hover, and the
    plain button's edge was 1.2:1 against white;
  - "Retired" contract versions used the failure red, the colour the app
    keeps for broken data;
  - the top bar's "Not yet" tag was 10.9px, under the 11px floor.

These tests pin the fixes to the stylesheet and to the few templates whose
tables were missing a shared class. The pages were also checked in a
browser (see the PR notes).
"""

import re
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from data_quality.tests import SignedInClientMixin, StylesheetMixin, contrast_ratio
from data_quality.tests_discovery import DiscoveryData


def rem(value):
    match = re.fullmatch(r"\s*([\d.]+)rem\s*", value)
    assert match, f"not a rem value: {value!r}"
    return float(match.group(1))


class TypeScaleTests(StylesheetMixin, TestCase):
    def declared(self, selector, prop):
        value = re.search(rf"(?:^|;)\s*{prop}:\s*([^;]+)", self.rule(selector))
        self.assertIsNotNone(value, f"{selector} sets no {prop}")
        return value.group(1).strip()

    def token(self, name):
        value = re.search(rf"--{name}:\s*([^;]+);", self.css)
        self.assertIsNotNone(value, f"no --{name} token")
        return value.group(1).strip()

    def test_small_capital_labels_share_one_size_and_colour(self):
        # Column headers and fact labels are the same role: one token each.
        for selector in (".datatable thead th", ".factlist dt", ".facts dt"):
            with self.subTest(selector=selector):
                self.assertEqual(self.declared(selector, "font-size"), "var(--text-label)")
                self.assertEqual(self.declared(selector, "color"), "var(--ink-soft)")

    def test_a_panel_title_is_a_step_above_its_column_headers(self):
        title = self.rule(".panel__title")
        self.assertNotRegex(title, r"text-transform:\s*uppercase")
        self.assertEqual(self.declared(".panel__title", "color"), "var(--ink)")
        self.assertGreaterEqual(rem(self.declared(".panel__title", "font-size")),
                                rem(self.token("text-label")) * 1.3)

    def test_form_labels_are_written_in_sentence_case(self):
        label = self.rule("label")
        self.assertNotRegex(label, r"text-transform:\s*uppercase")
        self.assertGreaterEqual(rem(self.declared("label", "font-size")), 0.85)

    def test_the_not_yet_tag_is_at_least_11px(self):
        self.assertGreaterEqual(rem(self.declared(".mainnav__tag", "font-size")) * 16, 11)

    def test_long_subtitles_keep_a_readable_measure(self):
        width = re.fullmatch(r"(\d+)ch", self.declared(".page__subtitle", "max-width"))
        self.assertIsNotNone(width)
        self.assertLessEqual(int(width.group(1)), 75)


class TableHeaderTests(StylesheetMixin, TestCase):
    def test_only_the_header_row_gets_column_header_styling(self):
        self.assertRegex(self.rule(".datatable thead th"), r"text-transform:\s*uppercase")
        # The old rule matched every th, row headers included.
        self.assertNotRegex(self.css, r"(?m)^\.datatable th\s*\{")

    def test_row_headers_read_like_the_data_they_label(self):
        row = self.rule(".datatable tbody th")
        self.assertRegex(row, r"text-transform:\s*none")
        self.assertRegex(row, r"color:\s*var\(--ink\)")
        self.assertRegex(row, r"text-align:\s*left")
        self.assertNotRegex(row, r"background:\s*#")

    def test_the_last_row_has_no_bottom_line_whether_it_starts_with_td_or_th(self):
        # The panel's own edge closes the table; a row-header th kept its
        # border and drew a short line under the last row on Reports.
        self.assertRegex(
            self.css,
            r"\.datatable tbody tr:last-child td,\s*\.datatable tbody tr:last-child th\s*\{\s*border-bottom:\s*none",
        )


class LinkAndButtonTests(StylesheetMixin, TestCase):
    def test_every_link_has_the_site_colour_and_a_hover(self):
        self.assertRegex(self.rule("a"), r"color:\s*var\(--accent\)")
        self.assertRegex(self.rule("a"), r"text-underline-offset:")
        # :where() keeps the hover at a bare link's weight, so the brand,
        # the nav and link-buttons keep their own colours on hover.
        self.assertRegex(self.rule("a:where(:hover)"), r"color:\s*var\(--accent-strong\)")
        self.assertGreaterEqual(contrast_ratio(self.tokens["accent-strong"], self.tokens["surface"]), 4.5)

    def test_primary_buttons_hover_whether_they_are_links_or_buttons(self):
        self.assertRegex(self.rule(".btn--primary:hover"), r"background:\s*var\(--accent-strong\)")
        self.assertNotRegex(self.css, r"(?m)^button\.btn--primary:hover")

    def test_plain_buttons_have_a_visible_edge_and_a_hover(self):
        self.assertRegex(self.rule(".btn"), r"border:\s*1px solid var\(--line-strong\)")
        # :where() keeps it below .btn--ghost:hover and .btn--primary:hover.
        self.assertRegex(self.rule(":where(a, button).btn:hover"), r"background:")
        # The dark bar's ghost buttons (Log out, Menu) keep their clear
        # background on hover; the plain hover's light fill under their
        # white text left the label unreadable (found in the browser).
        self.assertRegex(self.rule(".btn--ghost:hover"), r"background:\s*transparent")
        # Never a bare .btn:hover: it would reach the unavailable-action
        # labels, which are spans styled as buttons and must not react.
        self.assertNotRegex(self.css, r"(?m)^\.btn:hover")


class BadgeTests(StylesheetMixin, TestCase):
    def test_a_retired_contract_is_not_shown_in_the_failure_red(self):
        for match in re.finditer(r"(?m)^([^{}\n]*\.badge--retired[^{}\n]*)\{([^}]*)\}", self.css):
            with self.subTest(rule=match.group(1)):
                self.assertNotIn("--fail", match.group(2))
        failure = re.search(r"(?m)^([^{}\n]*)\{[^}]*var\(--fail-bg\)[^}]*\}", self.css[self.css.index(".badge {"):])
        self.assertNotIn("retired", failure.group(1))


class TableMarkupTests(SignedInClientMixin, TestCase):
    def test_empty_report_tables_use_the_empty_row(self):
        # run_outcome_counts() always lists every outcome (zeros included),
        # so the outcome tables only reach {% empty %} if it returns nothing.
        with patch("data_quality.charts.run_outcome_counts", return_value=[]):
            for name, rows in (("data_quality:reports", 2), ("data_quality:quality-history", 1)):
                with self.subTest(page=name):
                    html = self.client.get(reverse(name)).content.decode()
                    self.assertEqual(html.count('<tr class="is-emptyrow">'), rows)


class NumericColumnTests(DiscoveryData):
    def test_number_columns_align_their_headers_with_their_numbers(self):
        cases = (
            (reverse("data_quality:dataset-cbv-base"), '<th scope="col" class="num">Contract Versions</th>'),
            (reverse("data_quality:dataset-detail", args=[self.enrollment.pk]), '<th scope="col" class="num">Rules</th>'),
            (reverse("data_quality:quality-history"), '<th scope="col" class="num">Validation runs</th>'),
        )
        for url, header in cases:
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), header, html=True)

    def test_quality_history_counts_are_numeric_cells(self):
        html = self.client.get(reverse("data_quality:quality-history")).content.decode()
        body = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
        self.assertTrue(re.findall(r'<td class="num">\d+</td>', body))
        self.assertNotRegex(body, r"<td>\d+</td>")

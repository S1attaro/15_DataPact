"""
UX Stage 3 - finding violations and telling them apart.
Author: Tejas Jaggi.

Violations are found through the "Look up violations" form on the Contracts
page. That lookup stays a POST (A3 Section 2 shows a GET search and a POST
search on one page), so a link cannot run it. What links can do, and what
these tests check:

- the Home page's open-violation count and its workflow link take a
  signed-in user straight to the lookup, with "Open" already chosen when they
  came from the count;
- the results say how many violations matched and what was searched for, and
  the page lands on them instead of the top of a long page;
- each row says which dataset and which validation run it belongs to, so two
  failures of the same rule in different files no longer look identical, and
  links to the dataset;
- each Explain link has a name of its own for screen readers;
- the explain page says which run the violation came from.

Nothing here changes what the lookup finds, how it is ordered, or any
recorded resolution.
"""

import datetime
import re

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from data_quality.models import Contract, Dataset, ValidationRule, ValidationRun, Violation
from data_quality.tests import StylesheetMixin

SEARCH = reverse("data_quality:contract-search")


def when(year, month, day):
    return datetime.datetime(year, month, day, 12, 0, tzinfo=datetime.timezone.utc)


def results_rows(html):
    """The <tr> elements of the violation results table, as raw HTML."""
    panel = html.split('id="violation-results"', 1)[1]
    body = panel.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    return re.findall(r"<tr\b.*?</tr>", body, flags=re.S)


def visible_text(fragment):
    """Text a sighted reader sees: tags and visually hidden spans removed."""
    fragment = re.sub(r'<span class="visually-hidden">.*?</span>', "", fragment, flags=re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", fragment).split())


def link_names(fragment):
    """The accessible name of every link: all of its text, hidden or not."""
    return [" ".join(re.sub(r"<[^>]+>", " ", inner).split())
            for inner in re.findall(r"<a\b[^>]*>(.*?)</a>", fragment, flags=re.S)]


class DiscoveryData(TestCase):
    """
    The seed data's awkward case: one rule that failed in two monthly runs,
    plus an open violation in another dataset.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("reviewer", password="pw")
        owner = User.objects.create_user("owner1", password="pw")
        cls.enrollment = Dataset.objects.create(
            name="Monthly Enrollment Export", owner=owner, source_team="Registrar")
        cls.sales = Dataset.objects.create(
            name="Weekly Sales Extract", owner=owner, source_team="Finance")
        enr_v1 = Contract.objects.create(
            dataset=cls.enrollment, version_number=1, status=Contract.Status.ACTIVE)
        sales_v1 = Contract.objects.create(
            dataset=cls.sales, version_number=1, status=Contract.Status.ACTIVE)
        credit = ValidationRule.objects.create(
            contract=enr_v1, column_name="credit_hours", rule_type=ValidationRule.RuleType.TYPE_MATCH,
            parameters={"type": "integer"})
        total = ValidationRule.objects.create(
            contract=sales_v1, column_name="order_total", rule_type=ValidationRule.RuleType.RANGE,
            parameters={"min": 0, "max": 100000})
        april = ValidationRun.objects.create(
            contract=enr_v1, file_name="enrollment_2026_04.csv", row_count=4611,
            status=ValidationRun.Status.FAILED, started_at=when(2026, 4, 30))
        may = ValidationRun.objects.create(
            contract=enr_v1, file_name="enrollment_2026_05.csv", row_count=4640,
            status=ValidationRun.Status.FAILED, started_at=when(2026, 5, 31))
        week36 = ValidationRun.objects.create(
            contract=sales_v1, file_name="sales_2026_w36.csv", row_count=13120,
            status=ValidationRun.Status.FAILED, started_at=when(2026, 9, 4))
        cls.april_credit = Violation.objects.create(
            run=april, rule=credit, failed_row_count=12, message="not whole numbers",
            resolution=Violation.Resolution.DATA_ISSUE)
        cls.may_credit = Violation.objects.create(
            run=may, rule=credit, failed_row_count=5, message="not whole numbers",
            resolution=Violation.Resolution.DATA_ISSUE)
        cls.open_total = Violation.objects.create(
            run=week36, rule=total, failed_row_count=23, message="negative totals",
            resolution=Violation.Resolution.OPEN)

    def setUp(self):
        self.client.force_login(self.user)

    def lookup(self, dataset="", resolution=""):
        return self.client.post(SEARCH, {"dataset": dataset, "resolution": resolution})


class HomeLeadsToTheLookupTests(DiscoveryData):
    OPEN_LINK = f'href="{SEARCH}?resolution=OPEN#violation-lookup"'

    def test_the_open_violation_count_links_to_the_lookup_with_open_chosen(self):
        response = self.client.get(reverse("data_quality:home"))
        self.assertEqual(response.context["open_violation_count"], 1)
        self.assertContains(response, self.OPEN_LINK, count=1)
        self.assertContains(response, "Look up open violations")

    def test_there_is_no_open_violations_link_when_none_are_open(self):
        Violation.objects.update(resolution=Violation.Resolution.DATA_ISSUE)
        response = self.client.get(reverse("data_quality:home"))
        self.assertNotContains(response, "Look up open violations")

    def test_an_anonymous_visitor_sees_the_count_but_no_link(self):
        """The lookup is behind a login, and Home never advertises one of those."""
        self.client.logout()
        response = self.client.get(reverse("data_quality:home"))
        self.assertContains(response, "Open violations")
        self.assertNotContains(response, self.OPEN_LINK)
        self.assertNotContains(response, "Look up open violations")

    def test_the_workflow_link_goes_straight_to_the_lookup_form(self):
        response = self.client.get(reverse("data_quality:home"))
        self.assertContains(response, f'href="{SEARCH}#violation-lookup">Look up violations</a>')


class LookupFormTests(DiscoveryData):
    def test_the_lookup_panel_is_the_target_of_the_home_links(self):
        response = self.client.get(SEARCH)
        self.assertContains(response, 'id="violation-lookup"', count=1)

    def test_a_link_can_choose_the_resolution_but_does_not_run_the_lookup(self):
        response = self.client.get(SEARCH, {"resolution": "OPEN"})
        self.assertEqual(response.context["violation_resolution"], "OPEN")
        self.assertContains(response, '<option value="OPEN" selected>Open</option>', html=True)
        self.assertIsNone(response.context["violation_results"])
        self.assertNotContains(response, 'id="violation-results"')

    def test_a_chosen_resolution_says_the_lookup_has_not_run_yet(self):
        """Arriving from "Look up open violations" shows a form, not results: say so."""
        response = self.client.get(SEARCH, {"resolution": "OPEN"})
        self.assertContains(response, "Open is selected. Press Look up violations to see them.")

    def test_no_hint_without_a_chosen_resolution(self):
        response = self.client.get(SEARCH)
        self.assertNotContains(response, "is selected. Press Look up violations")

    def test_an_unknown_resolution_in_the_link_is_ignored(self):
        response = self.client.get(SEARCH, {"resolution": "<script>"})
        self.assertEqual(response.context["violation_resolution"], "")
        # Only the page's own content: the site's menu script (UX Stage 5)
        # sits before <main> on every signed-in page.
        html = response.content.decode()
        self.assertNotIn("<script>", html[html.index("<main"):])

    def test_the_contract_search_still_ignores_the_resolution(self):
        """`status` filters contracts; `resolution` must not leak into it."""
        response = self.client.get(SEARCH, {"resolution": "OPEN"})
        self.assertEqual(response.context["status"], "")

    def test_the_lookup_posts_to_its_own_results(self):
        response = self.client.get(SEARCH)
        self.assertContains(response, f'action="{SEARCH}#violation-results"')

    def test_the_lookup_still_needs_a_login(self):
        self.client.logout()
        response = self.client.post(SEARCH, {"dataset": "", "resolution": ""})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("data_quality:login"), response["Location"])


class ResultsTests(DiscoveryData):
    def test_the_results_panel_can_take_focus_when_the_page_lands_on_it(self):
        response = self.lookup()
        self.assertContains(response, 'id="violation-results" tabindex="-1"')

    def test_the_results_say_how_many_matched_and_how_they_are_ordered(self):
        response = self.lookup()
        self.assertContains(response, "3 violations, most failed rows first.")

    def test_the_summary_repeats_what_was_searched_for(self):
        response = self.lookup(dataset="Enrollment", resolution="DATA_ISSUE")
        self.assertContains(
            response,
            "2 violations in datasets whose name contains “Enrollment” with resolution "
            "Data issue, most failed rows first.")

    def test_one_result_is_singular(self):
        response = self.lookup(resolution="OPEN")
        self.assertContains(response, "1 violation with resolution Open, most failed rows first.")

    def test_the_search_text_in_the_summary_is_escaped(self):
        """The summary repeats what was typed, so it must render as text, not markup."""
        feed = Dataset.objects.create(name="Ops <i>Feed</i>", owner=self.user, source_team="Ops")
        contract = Contract.objects.create(dataset=feed, version_number=1, status=Contract.Status.ACTIVE)
        rule = ValidationRule.objects.create(
            contract=contract, column_name="id", rule_type=ValidationRule.RuleType.NOT_NULL)
        run = ValidationRun.objects.create(
            contract=contract, file_name="ops.csv", row_count=1, status=ValidationRun.Status.FAILED)
        Violation.objects.create(run=run, rule=rule, failed_row_count=1, message="m")
        html = self.lookup(dataset="<i>").content.decode()
        summary = re.search(r'<p class="results__summary">(.*?)</p>', html, flags=re.S).group(1)
        self.assertIn("“&lt;i&gt;”", summary)
        self.assertNotIn("<i>", summary)

    def test_the_lookup_finds_and_orders_the_same_violations_as_before(self):
        response = self.lookup()
        self.assertEqual(list(response.context["violation_results"]),
                         [self.open_total, self.april_credit, self.may_credit])

    def test_each_row_links_to_its_dataset(self):
        rows = results_rows(self.lookup().content.decode())
        self.assertIn(f'<a href="{self.sales.get_absolute_url()}">Weekly Sales Extract</a>', rows[0])
        self.assertIn(f'<a href="{self.enrollment.get_absolute_url()}">Monthly Enrollment Export</a>', rows[1])

    def test_each_row_names_its_validation_run(self):
        rows = [visible_text(row) for row in results_rows(self.lookup().content.decode())]
        self.assertIn("sales_2026_w36.csv 2026-09-04", rows[0])
        self.assertIn("enrollment_2026_04.csv 2026-04-30", rows[1])
        self.assertIn("enrollment_2026_05.csv 2026-05-31", rows[2])

    def test_the_same_rule_failing_in_two_runs_no_longer_reads_the_same(self):
        rows = [visible_text(row) for row in results_rows(self.lookup(dataset="Enrollment").content.decode())]
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0], rows[1])

    def test_the_table_has_a_run_column(self):
        response = self.lookup()
        self.assertContains(response, '<th scope="col">Validation run</th>', html=True)
        self.assertContains(response, '<th scope="col">AI explanation</th>', html=True)

    def test_each_explain_link_has_a_name_of_its_own(self):
        html = self.lookup().content.decode()
        names = [name for row in results_rows(html) for name in link_names(row) if name.startswith("Explain")]
        # The date too: the same file name can be checked again in a later run.
        self.assertEqual(names, [
            "Explain order_total Range in sales_2026_w36.csv, 2026-09-04",
            "Explain credit_hours Type match in enrollment_2026_04.csv, 2026-04-30",
            "Explain credit_hours Type match in enrollment_2026_05.csv, 2026-05-31",
        ])

    def test_the_explain_link_still_looks_the_same(self):
        rows = results_rows(self.lookup().content.decode())
        self.assertIn(f'href="{reverse("data_quality:violation-explain", args=[self.april_credit.pk])}"', rows[1])
        self.assertTrue(visible_text(rows[1]).endswith("Explain"))

    def test_showing_the_run_costs_no_extra_query_per_row(self):
        with CaptureQueriesContext(connection) as three:
            self.lookup()
        extra_run = ValidationRun.objects.create(
            contract=self.sales.contracts.get(), file_name="sales_2026_w37.csv", row_count=1,
            status=ValidationRun.Status.FAILED, started_at=timezone.now())
        Violation.objects.create(run=extra_run, rule=self.open_total.rule, failed_row_count=1, message="m")
        with CaptureQueriesContext(connection) as four:
            self.lookup()
        self.assertEqual(len(four), len(three))

    def test_no_match_keeps_the_existing_message(self):
        response = self.lookup(dataset="Nonexistent")
        self.assertContains(response, "No violations matched that lookup.")
        self.assertNotContains(response, "most failed rows first")

    def test_an_empty_database_says_nothing_has_been_recorded(self):
        """'Try a different dataset name' would send someone looking for nothing."""
        Violation.objects.all().delete()
        response = self.lookup(dataset="Enrollment")
        self.assertContains(response, "No violations have been recorded yet.")
        self.assertNotContains(response, "No violations matched that lookup.")

    def test_the_lookup_writes_nothing(self):
        before = list(Violation.objects.order_by("pk").values_list("pk", "resolution"))
        self.lookup()
        self.assertEqual(list(Violation.objects.order_by("pk").values_list("pk", "resolution")), before)


class ExplainPageRunTests(DiscoveryData):
    def test_the_explain_page_says_which_run_the_violation_came_from(self):
        response = self.client.get(reverse("data_quality:violation-explain", args=[self.may_credit.pk]))
        html = response.content.decode()
        self.assertIn("<dt>Validation run</dt>", html)
        self.assertIn("enrollment_2026_05.csv, checked 2026-05-31", visible_text(html))


class HiddenTextStyleTests(StylesheetMixin, TestCase):
    def test_visually_hidden_text_is_clipped_not_removed(self):
        """display:none would hide it from screen readers too, which defeats the point."""
        rule = self.rule(".visually-hidden")
        self.assertRegex(rule, r"position:\s*absolute")
        self.assertRegex(rule, r"clip-path:\s*inset\(50%\)")
        self.assertNotRegex(rule, r"display:\s*none|visibility:\s*hidden")

    def test_hidden_text_in_a_wide_table_cannot_widen_the_page(self):
        """
        An absolutely positioned span is placed against its nearest positioned
        ancestor. With none, it sat at its spot in the far-right column, outside
        the panel's scroll area, and made the whole page scroll sideways at
        390px (found in the browser). A positioned table keeps it inside.
        """
        self.assertRegex(self.rule(".datatable"), r"position:\s*relative")

    def test_the_home_link_spacing_is_not_overridden(self):
        """`.factlist dd` (0,1,1) beats a bare `.factlist__link` (0,1,0), so the rule must be scoped."""
        self.assertRegex(self.rule(".factlist .factlist__link"), r"margin:\s*0\.35rem 0 0")

    def test_the_run_line_is_readable(self):
        """The run is secondary text, but it must stay at --ink-soft (4.5:1), not --ink-faint."""
        self.assertEqual(self.declared_colour(".datatable .cell__sub", "color"), self.tokens["ink-soft"])

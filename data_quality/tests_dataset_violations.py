"""
UX Stage 4 - a dataset's own page lists its recorded violations.
Author: Tejas Jaggi.

Before this, the dataset page showed the dataset and its contract versions
and never mentioned a violation: the only way to them was the lookup on the
Contracts page. Now the page has a "Violations" panel: every violation
recorded against any of the dataset's contract versions, newest run first,
each naming its run (file, date, contract version) and rule, with a link to
the existing explain page. These tests check what the panel shows, what it
leaves out (other datasets, sample values), its empty states, its query
count, and that the page is still for signed-in users only.

Nothing here changes a violation, a run or a recorded resolution.
"""

import re
from html import unescape

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from data_quality.models import Contract, Dataset, ValidationRule, ValidationRun, Violation
from data_quality.tests_discovery import DiscoveryData, link_names, visible_text, when


def detail_url(dataset):
    return reverse("data_quality:dataset-detail", args=[dataset.pk])


def violation_rows(html):
    """The <tr> elements of the dataset page's violations table, as raw HTML."""
    panel = html.split('id="violations"', 1)[1]
    body = panel.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    return re.findall(r"<tr\b.*?</tr>", body, flags=re.S)


class DatasetViolationsTests(DiscoveryData):
    """Enrollment: credit_hours failed in April (12 rows) and May (5); Sales: one open violation."""

    def page(self, dataset=None):
        return self.client.get(detail_url(dataset or self.enrollment))

    def test_the_page_has_a_violations_panel(self):
        response = self.page()
        self.assertContains(response, 'id="violations"', count=1)
        self.assertContains(response, '<h2 class="panel__title" id="violations-title">Violations</h2>', html=True)

    def test_it_lists_this_datasets_violations_newest_run_first(self):
        response = self.page()
        self.assertEqual(list(response.context["violations"]), [self.may_credit, self.april_credit])

    def test_it_leaves_out_other_datasets(self):
        html = self.page().content.decode()
        self.assertNotIn("sales_2026_w36.csv", html)
        self.assertNotIn("order_total", html)

    def test_within_one_run_the_most_failed_rows_come_first(self):
        april = self.april_credit.run
        status = ValidationRule.objects.create(
            contract=april.contract, column_name="status", rule_type=ValidationRule.RuleType.ALLOWED_VALUES,
            parameters={"values": ["ACTIVE", "INACTIVE"]})
        bigger = Violation.objects.create(run=april, rule=status, failed_row_count=40, message="m")
        response = self.page()
        self.assertEqual(list(response.context["violations"]), [self.may_credit, bigger, self.april_credit])

    def test_violations_under_an_older_contract_version_are_listed_too(self):
        v2 = Contract.objects.create(dataset=self.enrollment, version_number=2, status=Contract.Status.ACTIVE)
        term = ValidationRule.objects.create(
            contract=v2, column_name="term_code", rule_type=ValidationRule.RuleType.REGEX,
            parameters={"pattern": "^[0-9]{4}[A-Z]$"})
        july = ValidationRun.objects.create(
            contract=v2, file_name="enrollment_2026_07.csv", row_count=1,
            status=ValidationRun.Status.FAILED, started_at=when(2026, 7, 31))
        Violation.objects.create(run=july, rule=term, failed_row_count=8, message="m")
        rows = [unescape(visible_text(row)) for row in violation_rows(self.page().content.decode())]
        self.assertEqual(len(rows), 3)
        self.assertIn("enrollment_2026_07.csv 2026-07-31 · contract v2", rows[0])
        self.assertIn("enrollment_2026_05.csv 2026-05-31 · contract v1", rows[1])

    def test_two_runs_at_the_same_moment_keep_their_rows_together(self):
        """Ordering by time alone would interleave them by failed rows."""
        contract = self.april_credit.run.contract
        status = ValidationRule.objects.create(
            contract=contract, column_name="status", rule_type=ValidationRule.RuleType.ALLOWED_VALUES)
        first, second = (ValidationRun.objects.create(
            contract=contract, file_name=name, row_count=1, status=ValidationRun.Status.FAILED,
            started_at=when(2026, 8, 31)) for name in ("a.csv", "b.csv"))
        Violation.objects.create(run=first, rule=self.april_credit.rule, failed_row_count=50, message="m")
        Violation.objects.create(run=first, rule=status, failed_row_count=1, message="m")
        Violation.objects.create(run=second, rule=self.april_credit.rule, failed_row_count=20, message="m")
        runs = [v.run.file_name for v in self.page().context["violations"]][:3]
        self.assertEqual(runs, ["b.csv", "a.csv", "a.csv"])

    def test_a_file_name_is_shown_as_text_not_markup(self):
        run = self.may_credit.run
        run.file_name = "<b>may</b>.csv"
        run.save()
        html = self.page().content.decode()
        self.assertIn("&lt;b&gt;may&lt;/b&gt;.csv", html)
        self.assertNotIn("<b>may</b>", html)

    def test_each_row_names_its_run_contract_version_and_rule(self):
        rows = [unescape(visible_text(row)) for row in violation_rows(self.page().content.decode())]
        self.assertIn("enrollment_2026_05.csv 2026-05-31 · contract v1", rows[0])
        self.assertIn("credit_hours - Type match", rows[0])
        self.assertIn("enrollment_2026_04.csv 2026-04-30 · contract v1", rows[1])

    def test_each_row_shows_failed_rows_and_the_recorded_resolution_in_words(self):
        rows = [visible_text(row) for row in violation_rows(self.page().content.decode())]
        self.assertIn("5 Data issue", rows[0])
        self.assertIn("12 Data issue", rows[1])

    def test_the_repeated_failure_reads_differently_in_each_run(self):
        rows = [visible_text(row) for row in violation_rows(self.page().content.decode())]
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0], rows[1])

    def test_each_row_links_to_the_explain_page_with_a_name_of_its_own(self):
        rows = violation_rows(self.page().content.decode())
        self.assertIn(f'href="{reverse("data_quality:violation-explain", args=[self.may_credit.pk])}"', rows[0])
        self.assertIn(f'href="{reverse("data_quality:violation-explain", args=[self.april_credit.pk])}"', rows[1])
        names = [name for row in rows for name in link_names(row)]
        self.assertEqual(names, [
            "Explain credit_hours Type match in enrollment_2026_05.csv, 2026-05-31",
            "Explain credit_hours Type match in enrollment_2026_04.csv, 2026-04-30",
        ])
        self.assertTrue(visible_text(rows[0]).endswith("Explain"))

    def test_the_table_headers(self):
        response = self.page()
        for header in ("Validation run", "Column / rule", "Failed rows", "Resolution", "AI explanation"):
            with self.subTest(header=header):
                self.assertContains(response, f'<th scope="col">{header}</th>' if header != "Failed rows"
                                    else '<th scope="col" class="num">Failed rows</th>', html=True)

    def test_the_summary_counts_violations_and_says_how_they_are_ordered(self):
        self.assertContains(self.page(), "2 violations recorded, newest run first.")

    def test_the_summary_says_how_many_are_still_open(self):
        response = self.page(self.sales)
        self.assertContains(response, "1 violation recorded, newest run first. 1 is still open.")

    def test_the_summary_says_nothing_about_open_ones_when_none_are(self):
        self.assertNotContains(self.page(), "still open")

    def test_two_open_violations_are_plural(self):
        Violation.objects.filter(rule__contract__dataset=self.enrollment).update(
            resolution=Violation.Resolution.OPEN)
        self.assertContains(self.page(), "2 violations recorded, newest run first. 2 are still open.")

    def test_sample_values_and_messages_stay_off_the_page(self):
        """The lookup and explain page do not show the file's raw values; neither does this list."""
        self.april_credit.sample_values = [{"row": 209, "value": "SECRET-SAMPLE-12.5"}]
        self.april_credit.message = "UNIQUE-MESSAGE-TEXT"
        self.april_credit.save()
        html = self.page().content.decode()
        self.assertNotIn("SECRET-SAMPLE-12.5", html)
        self.assertNotIn("UNIQUE-MESSAGE-TEXT", html)

    def test_the_list_costs_the_same_queries_however_long_it_is(self):
        with CaptureQueriesContext(connection) as two:
            self.page()
        june = ValidationRun.objects.create(
            contract=self.april_credit.run.contract, file_name="enrollment_2026_06.csv", row_count=1,
            status=ValidationRun.Status.FAILED, started_at=when(2026, 6, 30))
        Violation.objects.create(run=june, rule=self.april_credit.rule, failed_row_count=1, message="m")
        with CaptureQueriesContext(connection) as three:
            self.page()
        self.assertEqual(len(three), len(two))

    def test_viewing_the_page_writes_nothing(self):
        before = list(Violation.objects.order_by("pk").values_list("pk", "resolution"))
        self.page()
        self.assertEqual(list(Violation.objects.order_by("pk").values_list("pk", "resolution")), before)

    def test_the_page_is_still_for_signed_in_users_only(self):
        self.client.logout()
        response = self.page()
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("data_quality:login"), response["Location"])


class DatasetPageHeaderTests(DiscoveryData):
    def test_the_page_no_longer_names_the_view_that_rendered_it(self):
        """
        The "Rendered by: Generic CBV - DetailView" chip was an A2 grading aid;
        the rubric asks for view names in docs/notes/notes.txt, not on the page.
        """
        response = self.client.get(detail_url(self.enrollment))
        self.assertNotContains(response, "Rendered by")
        self.assertNotContains(response, 'class="viewchip"')
        # The page itself is unchanged: still the DetailView's template.
        self.assertTemplateUsed(response, "data_quality/dataset_detail.html")
        self.assertContains(response, "<h2 class=\"panel__title\">Dataset</h2>", html=True)


class DatasetViolationsEmptyTests(DiscoveryData):
    def test_a_dataset_with_no_runs_says_none_have_been_recorded(self):
        new = Dataset.objects.create(name="New Feed", owner=self.user, source_team="Ops")
        response = self.client.get(detail_url(new))
        self.assertContains(response, "No validation runs have been recorded for this dataset yet.")
        self.assertContains(response, "Violations appear here when a run finds a file that breaks one of its contract rules.")
        panel = response.content.decode().split('id="violations"', 1)[1].split("</section>", 1)[0]
        self.assertNotIn("<thead>", panel)

    def test_a_dataset_whose_runs_found_nothing_says_so(self):
        clean = Dataset.objects.create(name="Clean Feed", owner=self.user, source_team="Ops")
        contract = Contract.objects.create(dataset=clean, version_number=1, status=Contract.Status.ACTIVE)
        for month in (1, 2):
            ValidationRun.objects.create(
                contract=contract, file_name=f"clean_{month}.csv", row_count=1,
                status=ValidationRun.Status.PASSED, started_at=when(2026, month, 28))
        response = self.client.get(detail_url(clean))
        self.assertContains(response, "No violations recorded for this dataset.")
        self.assertContains(response, "2 validation runs recorded, none with a violation.")

    def test_one_clean_run_is_singular(self):
        clean = Dataset.objects.create(name="Clean Feed", owner=self.user, source_team="Ops")
        contract = Contract.objects.create(dataset=clean, version_number=1, status=Contract.Status.ACTIVE)
        ValidationRun.objects.create(
            contract=contract, file_name="clean.csv", row_count=1, status=ValidationRun.Status.PASSED)
        self.assertContains(self.client.get(detail_url(clean)), "1 validation run recorded, none with a violation.")

    def test_a_run_that_ended_in_an_error_is_not_passed_off_as_clean(self):
        """
        The seed's Library feed has one ERROR run and no violations. "None with a
        violation" alone would read as if the file passed, so the error is named.
        """
        feed = Dataset.objects.create(name="Library Feed", owner=self.user, source_team="Library")
        contract = Contract.objects.create(dataset=feed, version_number=1, status=Contract.Status.ACTIVE)
        ValidationRun.objects.create(
            contract=contract, file_name="circ.csv", row_count=1, status=ValidationRun.Status.ERROR)
        ValidationRun.objects.create(
            contract=contract, file_name="circ2.csv", row_count=1, status=ValidationRun.Status.PASSED)
        response = self.client.get(detail_url(feed))
        self.assertContains(
            response,
            "2 validation runs recorded, none with a violation. "
            "1 ended in an error and may not have been fully checked.")

    def test_no_error_note_when_every_run_finished(self):
        clean = Dataset.objects.create(name="Clean Feed", owner=self.user, source_team="Ops")
        contract = Contract.objects.create(dataset=clean, version_number=1, status=Contract.Status.ACTIVE)
        ValidationRun.objects.create(
            contract=contract, file_name="clean.csv", row_count=1, status=ValidationRun.Status.PASSED)
        self.assertNotContains(self.client.get(detail_url(clean)), "ended in an error")

    def test_the_empty_panel_adds_no_disabled_action(self):
        """The page's three unavailable actions stay the only disabled controls (UX Stage 1)."""
        new = Dataset.objects.create(name="New Feed", owner=self.user, source_team="Ops")
        html = self.client.get(detail_url(new)).content.decode()
        self.assertEqual(html.count("btn--disabled"), 3)

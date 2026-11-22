"""
Product redesign, Stage 3A - the dataset registry (/datasets/).
Author: Tejas Jaggi (with Claude Code).

What these tests pin down:

  - no page tells the user which Django view rendered it ("Rendered by:",
    an A2 grading aid), here or on the three other pages that carried it;
  - each registry row's extra facts come from the real records, in one
    query: the active contract version, the latest run and its outcome, and
    the open violations (the same definition the dataset page uses);
  - search (q) and the open-violations filter (show=open) narrow the rows
    and nothing else: the summary always describes the whole registry;
  - an empty registry and a search with no match say different things,
    and an empty registry shows no search tools;
  - a template rendered without the annotations shows no quality columns,
    rather than columns that would claim "No runs" for data never loaded;
  - the registry's small-screen layout follows the text size (em) and has
    no sideways-scrolling table.

The page was also checked in a browser at 1440, 1024, 768 and 390 px
(docs/redesign/registry/after/).
"""

import re
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.template.loader import render_to_string
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from data_quality.models import Contract, Dataset, ValidationRule, ValidationRun, Violation
from data_quality.tests import SignedInClientMixin, StylesheetMixin

REGISTRY = reverse("data_quality:dataset-list")


def rows(html):
    """The registry's data rows (each starts with the dataset's row header)."""
    body = html.split("<tbody", 1)[1].split("</tbody>", 1)[0]
    return re.findall(r'<tr role="row"[^>]*>(.*?)</tr>', body, flags=re.S)


class RegistryData(SignedInClientMixin, TestCase):
    """
    Two datasets with history and one without:

      Monthly Enrollment Export (Registrar, owner registrar_lead)
        v1 retired, v2 active; runs: passed (older), failed (newest);
        violations: one OPEN, one DATA_ISSUE
      Weekly Sales Extract (Finance, owner finance_lead)
        v1 active; one passed run, no violations
      Course Catalog Snapshot (Provost Office, owner provost_lead)
        a draft contract only; no runs
    """

    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        registrar = User.objects.create_user("registrar_lead", password="pw")
        finance = User.objects.create_user("finance_lead", password="pw")
        provost = User.objects.create_user("provost_lead", password="pw")

        cls.enrollment = Dataset.objects.create(
            name="Monthly Enrollment Export", owner=registrar, source_team="Registrar",
            description="One row per student per term.",
        )
        Contract.objects.create(dataset=cls.enrollment, version_number=1, status=Contract.Status.RETIRED)
        v2 = Contract.objects.create(dataset=cls.enrollment, version_number=2, status=Contract.Status.ACTIVE)
        rule = ValidationRule.objects.create(contract=v2, column_name="status", rule_type="ALLOWED_VALUES")
        # A run records at most one violation per rule, so the decided one
        # needs a rule of its own.
        other_rule = ValidationRule.objects.create(contract=v2, column_name="credit_hours", rule_type="RANGE")
        ValidationRun.objects.create(contract=v2, file_name="enrollment_08.csv", row_count=10,
                                     status=ValidationRun.Status.PASSED, started_at=now - timedelta(days=30))
        failed = ValidationRun.objects.create(contract=v2, file_name="enrollment_09.csv", row_count=10,
                                              status=ValidationRun.Status.FAILED, started_at=now)
        Violation.objects.create(run=failed, rule=rule, failed_row_count=4, message="m",
                                 resolution=Violation.Resolution.OPEN)
        Violation.objects.create(run=failed, rule=other_rule, failed_row_count=2, message="m",
                                 resolution=Violation.Resolution.DATA_ISSUE)

        cls.sales = Dataset.objects.create(name="Weekly Sales Extract", owner=finance, source_team="Finance")
        sales_v1 = Contract.objects.create(dataset=cls.sales, version_number=1, status=Contract.Status.ACTIVE)
        ValidationRun.objects.create(contract=sales_v1, file_name="sales.csv", row_count=5,
                                     status=ValidationRun.Status.PASSED, started_at=now - timedelta(days=2))

        cls.catalog = Dataset.objects.create(name="Course Catalog Snapshot", owner=provost,
                                             source_team="Provost Office")
        Contract.objects.create(dataset=cls.catalog, version_number=1, status=Contract.Status.DRAFT)


class NoImplementationDetailTests(RegistryData):
    PAGES = (
        "data_quality:dataset-list",
        "data_quality:dataset-render",
        "data_quality:dataset-cbv-base",
        "data_quality:contract-search",
        "data_quality:dataset-manage",
    )

    def test_no_page_names_the_view_that_rendered_it(self):
        for name in self.PAGES:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "Rendered by")
                self.assertNotContains(response, 'class="viewchip"')
                for leak in ("Generic CBV", "ListView", "django.views.View", "Function-based view"):
                    self.assertNotContains(response, leak)


class RegistryRowTests(RegistryData):
    def row_for(self, dataset):
        html = self.client.get(REGISTRY).content.decode()
        return next(r for r in rows(html) if dataset.name in r)

    def test_the_title_describes_every_dataset_not_only_mine(self):
        html = self.client.get(REGISTRY).content.decode()
        self.assertIn('<h1 class="page__title">Dataset registry</h1>', html)
        self.assertNotIn("My Datasets", html)

    def test_the_dataset_name_is_the_rows_link_and_its_header(self):
        row = self.row_for(self.enrollment)
        self.assertRegex(
            row,
            rf'<th scope="row" role="rowheader" class="registry-dataset">\s*'
            rf'<a class="registry-name" href="{self.enrollment.get_absolute_url()}">Monthly Enrollment Export</a>',
        )
        self.assertIn("One row per student per term.", row)

    def test_a_row_shows_its_active_version_latest_run_and_open_violations(self):
        row = self.row_for(self.enrollment)
        self.assertIn('<span class="badge badge--active badge--named">v2</span>', row)
        self.assertIn('<span class="badge badge--failed">Failed</span>', row)
        self.assertIn("2 runs", row)
        # One OPEN violation; the DATA_ISSUE one is decided and not counted.
        self.assertRegex(row, r"</span>1 open</span>")

    def test_a_dataset_without_history_says_so_in_words(self):
        row = self.row_for(self.catalog)
        self.assertIn('<span class="muted">None active</span>', row)
        self.assertIn('<span class="muted">No runs recorded</span>', row)
        self.assertIn('<span class="muted">None</span>', row)
        self.assertNotIn("badge--draft", row)

    def test_a_clean_dataset_shows_its_passed_run_and_no_open_violations(self):
        row = self.row_for(self.sales)
        self.assertIn('<span class="badge badge--passed">Passed</span>', row)
        self.assertNotIn("open-count", row)

    def test_every_cell_carries_its_label_for_the_stacked_layout(self):
        row = self.row_for(self.enrollment)
        for label in ("Office and owner", "Contract", "Latest run", "Open violations", "Registered"):
            with self.subTest(label=label):
                self.assertIn(f'data-label="{label}"', row)

    def test_the_rows_cost_one_query_on_both_routes(self):
        for name in ("data_quality:dataset-list", "data_quality:dataset-render"):
            with self.subTest(page=name):
                with CaptureQueriesContext(connection) as captured:
                    response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                list_queries = [q for q in captured.captured_queries
                                if q["sql"].lstrip().upper().startswith("SELECT")
                                and '"data_quality_dataset"."name"' in q["sql"]]
                # The ListView reads the rows, then the whole registry once
                # more for its summary; the FBV reads the rows only.
                self.assertLessEqual(len(list_queries), 2 if name.endswith("list") else 1)


class RegistryQueryCountTests(RegistryData):
    """
    Stage 3B review: the per-table count above cannot see a per-row query on
    another table (a contract or run lookup made while a row renders). This
    counts EVERY query the rendered page makes and requires the number to stay
    the same when the registry doubles, each new dataset carrying a contract,
    a run and an open violation, so any per-row lookup would add queries.
    """

    def all_queries(self, name):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse(name))
        self.assertEqual(response.status_code, 200)
        return len(captured.captured_queries)

    def add_datasets(self, count):
        owner = User.objects.create_user("bulk_owner", password="pw")
        for i in range(count):
            dataset = Dataset.objects.create(name=f"Bulk Dataset {i}", owner=owner, source_team="Bulk")
            contract = Contract.objects.create(dataset=dataset, version_number=1, status=Contract.Status.ACTIVE)
            rule = ValidationRule.objects.create(contract=contract, column_name="c", rule_type="NOT_NULL")
            run = ValidationRun.objects.create(contract=contract, file_name="f.csv", row_count=1,
                                               status=ValidationRun.Status.FAILED)
            Violation.objects.create(run=run, rule=rule, failed_row_count=1, message="m")

    def test_rendering_more_rows_costs_no_more_queries(self):
        for name in ("data_quality:dataset-list", "data_quality:dataset-render"):
            with self.subTest(page=name):
                html_rows = len(rows(self.client.get(reverse(name)).content.decode()))
                self.assertEqual(html_rows, Dataset.objects.count())
        self.add_datasets(3)
        for name in ("data_quality:dataset-list", "data_quality:dataset-render"):
            with self.subTest(page=name):
                after_rows = len(rows(self.client.get(reverse(name)).content.decode()))
                self.assertEqual(after_rows, Dataset.objects.count())
                self.assertEqual(self.all_queries(name), self.baseline[name])

    def setUp(self):
        self.baseline = {name: self.all_queries(name)
                         for name in ("data_quality:dataset-list", "data_quality:dataset-render")}

    def add_datasets_in_every_state(self):
        """
        Stage 3B.1: six rows, one per state a row can be in, so a query that
        runs only for some rows (say, those without an active contract) is
        still added and counted. States: contract active or absent, runs
        recorded or absent, violations open, decided only, or absent.
        """
        owner = User.objects.create_user("mixed_owner", password="pw")

        def dataset(name):
            return Dataset.objects.create(name=name, owner=owner, source_team="Mixed")

        def run(contract, status):
            return ValidationRun.objects.create(contract=contract, file_name="f.csv", row_count=1, status=status)

        dataset("State A - no contract")
        Contract.objects.create(dataset=dataset("State B - draft only"), version_number=1,
                                status=Contract.Status.DRAFT)
        Contract.objects.create(dataset=dataset("State C - active, no runs"), version_number=1,
                                status=Contract.Status.ACTIVE)
        passed = Contract.objects.create(dataset=dataset("State D - passed run"), version_number=1,
                                         status=Contract.Status.ACTIVE)
        run(passed, ValidationRun.Status.PASSED)
        for name, resolution in (("State E - decided only", Violation.Resolution.DATA_ISSUE),
                                 ("State F - open violation", Violation.Resolution.OPEN)):
            contract = Contract.objects.create(dataset=dataset(name), version_number=1,
                                               status=Contract.Status.ACTIVE)
            rule = ValidationRule.objects.create(contract=contract, column_name="c", rule_type="NOT_NULL")
            Violation.objects.create(run=run(contract, ValidationRun.Status.FAILED), rule=rule,
                                     failed_row_count=1, message="m", resolution=resolution)

    def test_rows_in_every_state_cost_no_more_queries(self):
        self.add_datasets_in_every_state()
        for name in ("data_quality:dataset-list", "data_quality:dataset-render"):
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                self.assertEqual(len(rows(html)), Dataset.objects.count())
                for state in "ABCDEF":
                    self.assertIn(f"State {state} -", html)
                self.assertEqual(self.all_queries(name), self.baseline[name])


class RegistrySummaryTests(RegistryData):
    def test_the_summary_counts_the_real_records(self):
        registry = self.client.get(REGISTRY).context["registry"]
        self.assertEqual(registry["total"], 3)
        self.assertEqual(registry["with_active_contract"], 2)
        self.assertEqual(registry["with_runs"], 2)
        self.assertEqual(registry["needing_decision"], 1)

    def test_the_summary_does_not_change_with_the_search(self):
        registry = self.client.get(REGISTRY, {"q": "sales"}).context["registry"]
        self.assertEqual(registry["total"], 3)
        self.assertEqual(registry["needing_decision"], 1)


class RegistrySearchTests(RegistryData):
    def names(self, **params):
        return [d.name for d in self.client.get(REGISTRY, params).context["datasets"]]

    def test_search_matches_name_office_and_owner_ignoring_case(self):
        self.assertEqual(self.names(q="ENROLL"), ["Monthly Enrollment Export"])
        self.assertEqual(self.names(q="finance"), ["Weekly Sales Extract"])
        self.assertEqual(self.names(q="provost_lead"), ["Course Catalog Snapshot"])

    def test_the_open_filter_keeps_datasets_with_an_open_violation(self):
        self.assertEqual(self.names(show="open"), ["Monthly Enrollment Export"])
        self.assertEqual(self.names(q="sales", show="open"), [])

    def test_an_unknown_filter_value_is_ignored(self):
        self.assertEqual(len(self.names(show="everything")), 3)

    def test_results_stay_in_name_order(self):
        self.assertEqual(
            self.names(),
            ["Course Catalog Snapshot", "Monthly Enrollment Export", "Weekly Sales Extract"],
        )

    def test_the_search_is_a_labelled_get_form(self):
        html = self.client.get(REGISTRY).content.decode()
        self.assertRegex(html, rf'<form class="registry-search" method="get" action="{REGISTRY}" role="search"')
        self.assertIn('<label class="registry-search__label" for="registry-q">Find a dataset</label>', html)
        self.assertIn('id="registry-q" name="q"', html)

    def test_the_current_filter_is_marked_for_screen_readers(self):
        nav = self.client.get(REGISTRY, {"show": "open"}).content.decode()
        nav = nav[nav.index('<nav class="registry-filter"'):]
        nav = nav[:nav.index("</nav>")]
        self.assertEqual(nav.count('aria-current="page"'), 1)
        self.assertRegex(nav, r'show=open" aria-current="page">With open violations')

    def test_a_search_keeps_its_words_in_the_box_and_says_how_many_matched(self):
        response = self.client.get(REGISTRY, {"q": "enroll"})
        self.assertContains(response, 'value="enroll"')
        self.assertContains(response, "Showing 1 of 3 datasets matching")

    def test_a_search_with_no_match_offers_the_full_list_not_registration(self):
        response = self.client.get(REGISTRY, {"q": "no such dataset"})
        self.assertContains(response, "No datasets match this search.")
        self.assertContains(response, f'href="{REGISTRY}">Show all datasets</a>')
        self.assertNotContains(response, "No datasets registered yet")

    def test_the_search_is_escaped(self):
        response = self.client.get(REGISTRY, {"q": '<script>alert(1)</script>'})
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")


class EmptyRegistryTests(SignedInClientMixin, TestCase):
    def test_an_empty_registry_shows_no_search_tools(self):
        html = self.client.get(REGISTRY).content.decode()
        self.assertIn("No datasets registered yet", html)
        self.assertNotIn('class="registry-search"', html)
        self.assertNotIn('class="registry-ledger"', html)


class TemplateWithoutAnnotationsTests(RegistryData):
    def test_no_quality_column_is_shown_for_data_that_was_not_loaded(self):
        html = render_to_string("data_quality/dataset_list.html", {"datasets": Dataset.objects.all()})
        self.assertIn("Monthly Enrollment Export", html)
        for absent in ("Latest run", "No runs recorded", "Open violations"):
            with self.subTest(text=absent):
                self.assertNotIn(absent, html)


class RegistryStyleTests(StylesheetMixin, TestCase):
    def registry_css(self):
        # Section 19 only: it ends where the shell's section 20 begins.
        start = self.css.index("19. dataset registry")
        end = self.css.find("20. application shell", start)
        return self.css[start:end if end != -1 else None]

    def test_the_small_screen_layout_follows_the_text_size(self):
        conditions = re.findall(r"@media\s*\(([^)]*)\)", self.registry_css())
        widths = [c for c in conditions if "width" in c]
        self.assertTrue(widths)
        for cond in widths:
            with self.subTest(media=cond):
                self.assertRegex(cond, r"^max-width:\s*[\d.]+em$")

    def test_stacked_rows_do_not_scroll_sideways(self):
        css = self.registry_css()
        self.assertRegex(css, r"\.registry-panel\s*\{\s*overflow:\s*visible;")
        self.assertRegex(css, r"\.registry-table tbody tr\s*\{[^}]*display:\s*grid")
        self.assertRegex(css, r"\.registry-table td::before\s*\{[^}]*content:\s*attr\(data-label\)")

    def test_registry_hover_needs_a_real_pointer(self):
        css = self.registry_css()
        hovers = re.findall(r"(?m)^\s*([^{}\n]*:hover[^{}\n]*)\{", css)
        gated = css[css.index("@media (hover: hover) and (pointer: fine)"):]
        for selector in hovers:
            with self.subTest(selector=selector):
                self.assertIn(selector.strip(), gated)

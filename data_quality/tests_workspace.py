"""
Product redesign, Stage 3C - the workspace overview (/datasets/overview/)
and the page-header breadcrumb rule.
Author: Tejas Jaggi (with Claude Code).

What these tests pin down:

  - the A2 Base CBV still supplies "rows" exactly as before, and the page
    now also answers: what needs a decision (open violations, newest run
    first, five at most), what was checked most recently (five runs, with
    their violation and open counts), and which datasets are not covered
    (no active contract, no recorded run, latest run ended in an error);
  - "Review open violations" appears only when a violation is open, and
    goes to the existing lookup with Open chosen;
  - the page never offers a Resolve action, never uses relative or "live"
    time words, and says a person records each decision;
  - with no datasets, only the single Register empty state is shown;
  - the page costs the same number of queries however many rows it shows,
    in every state a dataset can be in;
  - top-level pages carry no breadcrumb; nested pages carry a labelled
    breadcrumb landmark whose last item is the current page.
"""

import re
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from data_quality.models import Contract, Dataset, ValidationRule, ValidationRun, Violation
from data_quality.tests import SignedInClientMixin

OVERVIEW = reverse("data_quality:dataset-cbv-base")
LOOKUP_OPEN = f'{reverse("data_quality:contract-search")}?resolution=OPEN#violation-lookup'


def main(html):
    return html[html.index('<main class="page"'):html.index("</main>")]


class WorkspaceData(SignedInClientMixin, TestCase):
    """
    Five datasets, one per state the overview distinguishes:
      Alpha   active contract; newest run FAILED with one OPEN and one decided violation
      Beta    active contract; one PASSED run
      Gamma   draft contract only; no runs
      Delta   active contract; a PASSED run, then a newer run that ended in ERROR
      Epsilon active contract; no runs
    """

    @classmethod
    def setUpTestData(cls):
        cls.now = timezone.now()
        owner = User.objects.create_user("workspace_owner", password="pw")

        def dataset(name, team="Registrar"):
            return Dataset.objects.create(name=name, owner=owner, source_team=team)

        def contract(ds, version=1, status=Contract.Status.ACTIVE):
            return Contract.objects.create(dataset=ds, version_number=version, status=status)

        def run(ct, status, days_ago, name="f.csv", rows=100):
            return ValidationRun.objects.create(contract=ct, file_name=name, row_count=rows, status=status,
                                                started_at=cls.now - timedelta(days=days_ago))

        cls.alpha = dataset("Alpha Export")
        alpha_v = contract(cls.alpha, version=2)
        cls.alpha_run = run(alpha_v, ValidationRun.Status.FAILED, 1, name="alpha_2026_09.csv", rows=4812)
        rule_a = ValidationRule.objects.create(contract=alpha_v, column_name="status", rule_type="ALLOWED_VALUES")
        rule_b = ValidationRule.objects.create(contract=alpha_v, column_name="credit_hours", rule_type="RANGE")
        cls.open_violation = Violation.objects.create(run=cls.alpha_run, rule=rule_a, failed_row_count=1234,
                                                      message="m", resolution=Violation.Resolution.OPEN)
        Violation.objects.create(run=cls.alpha_run, rule=rule_b, failed_row_count=2, message="m",
                                 resolution=Violation.Resolution.DATA_ISSUE)

        cls.beta = dataset("Beta Extract", team="Finance")
        run(contract(cls.beta), ValidationRun.Status.PASSED, 3)

        cls.gamma = dataset("Gamma Snapshot", team="Provost Office")
        contract(cls.gamma, status=Contract.Status.DRAFT)

        cls.delta = dataset("Delta Log", team="Library")
        delta_v = contract(cls.delta)
        run(delta_v, ValidationRun.Status.PASSED, 10)
        run(delta_v, ValidationRun.Status.ERROR, 2)

        cls.epsilon = dataset("Epsilon Readings", team="Research")
        contract(cls.epsilon)


class WorkspaceContextTests(WorkspaceData):
    def test_the_a2_rows_are_unchanged(self):
        rows = self.client.get(OVERVIEW).context["rows"]
        self.assertEqual([r["dataset"].name for r in rows],
                         ["Alpha Export", "Beta Extract", "Delta Log", "Epsilon Readings", "Gamma Snapshot"])
        for row in rows:
            with self.subTest(dataset=row["dataset"].name):
                self.assertEqual(set(row), {"dataset", "contract_count", "active_contract"})
        gamma = next(r for r in rows if r["dataset"] == self.gamma)
        self.assertEqual(gamma["contract_count"], 1)
        self.assertIsNone(gamma["active_contract"])

    def test_only_open_violations_need_a_decision(self):
        context = self.client.get(OVERVIEW).context
        self.assertEqual(context["open_violation_count"], 1)
        self.assertEqual(context["open_violations"], [self.open_violation])

    def test_runs_carry_their_violation_and_open_counts(self):
        runs = self.client.get(OVERVIEW).context["recent_runs"]
        self.assertEqual(runs[0], self.alpha_run)  # the most recently recorded
        self.assertEqual((runs[0].violation_count, runs[0].open_count), (2, 1))
        self.assertEqual([r.started_at for r in runs], sorted((r.started_at for r in runs), reverse=True))
        self.assertEqual(self.client.get(OVERVIEW).context["run_count"], 4)

    def test_coverage_gaps_tell_no_run_apart_from_a_failed_run(self):
        gaps = self.client.get(OVERVIEW).context["gaps"]
        self.assertEqual(gaps["no_active_contract"], [self.gamma])
        self.assertEqual(gaps["no_runs"], [self.epsilon, self.gamma])
        self.assertEqual(gaps["latest_run_error"], [self.delta])
        # Alpha's failed run is a violation to decide, not a coverage gap.
        self.assertNotIn(self.alpha, [d for kind in gaps.values() for d in kind])


class WorkspacePageTests(WorkspaceData):
    def setUp(self):
        self.html = main(self.client.get(OVERVIEW).content.decode())

    def test_the_page_is_the_workspace_overview(self):
        self.assertIn('<h1 class="page__title">Workspace overview</h1>', self.html)
        for title in ("Needs a decision", "Most recently recorded runs", "Coverage gaps", "Contract coverage"):
            with self.subTest(section=title):
                self.assertRegex(self.html, rf'<h2 class="ws-section__title" id="[^"]+">{title}</h2>')

    def test_review_open_violations_goes_to_the_lookup_with_open_chosen(self):
        self.assertIn(f'<a class="btn btn--primary" href="{LOOKUP_OPEN}">Review open violations</a>', self.html)

    def test_each_open_violation_has_a_uniquely_named_investigate_link(self):
        url = reverse("data_quality:violation-explain", args=[self.open_violation.pk])
        self.assertIn(f'href="{url}">Investigate<span class="visually-hidden"> status in Alpha Export</span></a>', self.html)
        self.assertIn("<strong>1,234</strong> of 4,812 rows failed", self.html)
        self.assertIn("alpha_2026_09.csv", self.html)

    def test_a_person_decides_and_the_page_offers_no_resolve_action(self):
        self.assertIn("A person records each decision", self.html)
        self.assertIn("it never records one", self.html)
        self.assertNotRegex(self.html, r"(?i)>\s*resolve")

    def test_dates_are_absolute_and_nothing_claims_to_be_live(self):
        self.assertRegex(self.html, r"recorded \d{4}-\d{2}-\d{2}")
        self.assertNotRegex(self.html, r"(?i)\b(ago|today|yesterday|live|real[- ]time)\b")
        self.assertRegex(self.client.get(OVERVIEW).content.decode(), r"does not check\s+incoming files automatically yet")

    def test_a_dataset_never_checked_is_not_called_a_failure(self):
        self.assertIn("Never checked, so there is no result yet: not a failure.", self.html)

    def test_every_section_links_to_its_existing_destination(self):
        for name in ("data_quality:reports", "data_quality:quality-history"):
            with self.subTest(destination=name):
                self.assertIn(f'href="{reverse(name)}"', self.html)
        self.assertIn(f'href="{LOOKUP_OPEN}">Look up all open violations</a>', self.html)
        for dataset in (self.gamma, self.delta, self.epsilon):
            self.assertIn(f'href="{dataset.get_absolute_url()}"', self.html)


class ReviewOpenViolationsJourneyTests(WorkspaceData):
    """
    Stage 3C.1: following the overview's own primary action. The lookup is a
    POST, so the link only chooses Open and says so; one more press runs it.
    """

    def test_the_button_chooses_open_and_one_press_lists_only_open_violations(self):
        html = self.client.get(OVERVIEW).content.decode()
        href = re.search(r'<a class="btn btn--primary" href="([^"]+)">Review open violations</a>', html).group(1)
        self.assertEqual(href, LOOKUP_OPEN)
        landing = self.client.get(href)  # the test client drops the #fragment, keeps the query
        self.assertEqual(landing.status_code, 200)
        self.assertEqual(landing.context["violation_resolution"], Violation.Resolution.OPEN)
        self.assertIsNone(landing.context["violation_results"])
        self.assertContains(landing, "Open is selected. Press Look up violations to see them.")
        self.assertContains(landing, '<option value="OPEN" selected>Open</option>', html=True)

        results = self.client.post(reverse("data_quality:contract-search"), {"dataset": "", "resolution": "OPEN"})
        found = list(results.context["violation_results"])
        self.assertEqual(found, [self.open_violation])
        self.assertTrue(all(v.resolution == Violation.Resolution.OPEN for v in found))


class WorkspaceStateTests(SignedInClientMixin, TestCase):
    def test_no_datasets_shows_only_the_register_empty_state(self):
        html = main(self.client.get(OVERVIEW).content.decode())
        self.assertEqual(html.count('class="empty-state__message"'), 1)
        self.assertIn("No datasets registered yet", html)
        for absent in ("Needs a decision", "Most recently recorded runs", "Coverage gaps", "Review open violations"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, html)

    def test_with_nothing_open_there_is_no_primary_action(self):
        owner = User.objects.create_user("calm_owner", password="pw")
        dataset = Dataset.objects.create(name="Calm Extract", owner=owner, source_team="Finance")
        ValidationRun.objects.create(contract=Contract.objects.create(dataset=dataset, version_number=1,
                                                                      status=Contract.Status.ACTIVE),
                                     file_name="calm.csv", row_count=1, status=ValidationRun.Status.PASSED)
        html = main(self.client.get(OVERVIEW).content.decode())
        self.assertNotIn("Review open violations", html)
        self.assertIn("No open violations. Every recorded violation has a decision.", html)
        self.assertIn("Every dataset has an active contract and a recorded run", html)

    def test_long_lists_show_five_and_say_how_many_there_are(self):
        owner = User.objects.create_user("busy_owner", password="pw")
        dataset = Dataset.objects.create(name="Busy Extract", owner=owner, source_team="Ops")
        contract = Contract.objects.create(dataset=dataset, version_number=1, status=Contract.Status.ACTIVE)
        for i in range(7):
            run = ValidationRun.objects.create(contract=contract, file_name=f"busy_{i}.csv", row_count=10,
                                               status=ValidationRun.Status.FAILED,
                                               started_at=timezone.now() - timedelta(days=i))
            rule = ValidationRule.objects.create(contract=contract, column_name=f"c{i}", rule_type="NOT_NULL")
            Violation.objects.create(run=run, rule=rule, failed_row_count=1, message="m")
        response = self.client.get(OVERVIEW)
        self.assertEqual(len(response.context["open_violations"]), 5)
        self.assertEqual(len(response.context["recent_runs"]), 5)
        self.assertContains(response, "Showing the 5 most recent of 7.")
        self.assertEqual(response.context["open_violations"][0].run.file_name, "busy_0.csv")


def outer_table(sql):
    """The table a query reads FROM at its top level, ignoring subqueries."""
    outer = sql
    while re.search(r"\([^()]*\)", outer):
        outer = re.sub(r"\([^()]*\)", "", outer)
    return re.search(r'FROM "(\w+)"', outer).group(1)


class WorkspaceQueryCountTests(WorkspaceData):
    """Every query the rendered page makes, before and after the workspace grows in every state."""

    SIGN_IN_TABLES = {"django_session", "auth_user"}
    PAGE_QUERIES = 5  # datasets, their contracts, open violations, their count, recent runs

    def captured(self):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(OVERVIEW)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "data_quality/dataset_overview.html")
        return [outer_table(q["sql"]) for q in captured.captured_queries]

    def all_queries(self):
        return len(self.captured())

    def page_queries(self):
        return [t for t in self.captured() if t not in self.SIGN_IN_TABLES]

    def test_the_page_itself_makes_five_queries(self):
        """
        Stage 3C.1: the rendered request's queries, split by the table each
        one reads at its top level. The sign-in ones (session, user) belong to
        Django's auth middleware, so they are counted apart rather than pinned:
        a change there must not fail a test about this page.
        """
        tables = self.captured()
        page = [t for t in tables if t not in self.SIGN_IN_TABLES]
        self.assertEqual(page, ["data_quality_dataset", "data_quality_contract", "data_quality_violation",
                                "data_quality_violation", "data_quality_validationrun"])
        self.assertTrue(set(tables) - set(page) <= self.SIGN_IN_TABLES)

    def test_the_page_queries_stay_at_five_as_the_workspace_grows(self):
        self.assertEqual(len(self.page_queries()), self.PAGE_QUERIES)
        owner = User.objects.create_user("growth_owner_2", password="pw")
        for i in range(6):
            ds = Dataset.objects.create(name=f"Grown {i}", owner=owner, source_team="Growth")
            ct = Contract.objects.create(dataset=ds, version_number=1, status=Contract.Status.ACTIVE)
            run = ValidationRun.objects.create(contract=ct, file_name="g.csv", row_count=5,
                                               status=ValidationRun.Status.FAILED)
            rule = ValidationRule.objects.create(contract=ct, column_name="c", rule_type="NOT_NULL")
            Violation.objects.create(run=run, rule=rule, failed_row_count=1, message="m")
        self.assertEqual(len(self.page_queries()), self.PAGE_QUERIES)

    def test_the_page_costs_the_same_however_much_it_shows(self):
        before = self.all_queries()
        owner = User.objects.create_user("growth_owner", password="pw")
        for i in range(4):
            ds = Dataset.objects.create(name=f"Growth {i}", owner=owner, source_team="Growth")
            Dataset.objects.create(name=f"Growth no contract {i}", owner=owner, source_team="Growth")
            Contract.objects.create(dataset=Dataset.objects.create(name=f"Growth draft {i}", owner=owner,
                                                                  source_team="Growth"),
                                    version_number=1, status=Contract.Status.DRAFT)
            ct = Contract.objects.create(dataset=ds, version_number=1, status=Contract.Status.ACTIVE)
            for status in (ValidationRun.Status.PASSED, ValidationRun.Status.FAILED, ValidationRun.Status.ERROR):
                run = ValidationRun.objects.create(contract=ct, file_name="g.csv", row_count=5, status=status)
                if status == ValidationRun.Status.FAILED:
                    for resolution in (Violation.Resolution.OPEN, Violation.Resolution.CONTRACT_UPDATED):
                        rule = ValidationRule.objects.create(contract=ct, column_name=f"{resolution}{i}",
                                                             rule_type="NOT_NULL")
                        Violation.objects.create(run=run, rule=rule, failed_row_count=1, message="m",
                                                 resolution=resolution)
        self.assertEqual(self.all_queries(), before)


class BreadcrumbRuleTests(WorkspaceData):
    TOP_LEVEL = ("data_quality:dataset-cbv-base", "data_quality:dataset-list", "data_quality:contract-search",
                 "data_quality:dataset-manage", "data_quality:quality-history", "data_quality:charts",
                 "data_quality:reports", "data_quality:analytics", "data_quality:handbook-ask")

    def test_top_level_pages_carry_no_breadcrumb(self):
        for name in self.TOP_LEVEL:
            with self.subTest(page=name):
                self.assertNotIn('class="breadcrumbs"', main(self.client.get(reverse(name)).content.decode()))

    def crumbs(self, url):
        html = main(self.client.get(url).content.decode())
        return re.search(r'<nav class="breadcrumbs" aria-label="Breadcrumb">\s*<ol>(.*?)</ol>', html, flags=re.S).group(1)

    def test_the_dataset_page_names_its_parent_and_itself(self):
        crumbs = self.crumbs(self.alpha.get_absolute_url())
        self.assertIn(f'<li><a href="{reverse("data_quality:dataset-list")}">Datasets</a></li>', crumbs)
        self.assertIn('<li aria-current="page">Alpha Export</li>', crumbs)

    def test_the_explain_page_leads_back_through_its_dataset(self):
        crumbs = self.crumbs(reverse("data_quality:violation-explain", args=[self.open_violation.pk]))
        items = re.findall(r"<li[^>]*>(.*?)</li>", crumbs, flags=re.S)
        self.assertEqual(len(items), 3)
        self.assertIn(f'href="{self.alpha.get_absolute_url()}">Alpha Export</a>', items[1])
        self.assertIn('<li aria-current="page">Investigate violation</li>', crumbs)

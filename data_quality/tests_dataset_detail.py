"""
Product redesign, Stage 3G - Dataset detail.

"Where it stands" replaces the old Dataset facts panel: the version in force
(or "No active version"; a Draft or Retired version never governs), the newest
recorded run with its own outcome and the version it was checked against, and
the violations with their scope stated. A new "Recorded runs" panel lists every
run, newest first. Contract versions keep every version, with the version as
the row header and a link to the Contracts search (a substring match, and it
says so). The Stage 3D violations section is unchanged, byte for byte.

The view reads everything in a fixed number of queries (the template used to
count each version's rules separately). The browser side (layout at 1440,
1024, 768, 390 and 320, zoom, forced colours) is recorded in
docs/redesign/stage_3g/.
"""
import hashlib
import re
from datetime import datetime, timedelta, timezone as dt_timezone
from html import unescape
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from data_quality.models import Contract, Dataset, ValidationRule, ValidationRun, Violation
from data_quality.tests import StylesheetMixin, empty_state_actions

TEMPLATE = Path(settings.BASE_DIR) / "data_quality/templates/data_quality/dataset_detail.html"
# The Stage 3D violations section: from its UX Stage 4 comment to its closing </section>.
VIOLATIONS_MARKER = "    {% comment %}\n        UX Stage 4: this dataset's recorded violations"
VIOLATIONS_SHA256 = "dca40e1350d74baa448b75e33759034b582b1256819e7621e4a2a506d9a315c7"


def text_of(fragment):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def section(html, section_id):
    match = re.search(rf'<section class="panel" id="{section_id}".*?</section>', html, re.S)
    assert match, f"no #{section_id} section"
    return match.group(0)


def when(day):
    return datetime(2026, 9, 1, 9, 0, tzinfo=dt_timezone.utc) - timedelta(days=day)


class DetailData(TestCase):
    """
    enrollment  v1, v2 Retired and v3 Active; runs under v1 and v2 only, the
                newest under v2: "No run recorded under v3 yet" is true.
    older       v2 Active has an older run; the newest run used v1. The
                sentence would be false here and must not appear.
    current     the newest run used the active version.
    draft       a Draft version only, no runs.
    empty       no contract at all.
    errored     the newest run ended in an error.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("detail_owner", password="pw")

        def dataset(name, **kw):
            return Dataset.objects.create(name=name, owner=cls.user, source_team=kw.pop("team", "Registrar"), **kw)

        def version(ds, number, status, rules=1, note=""):
            contract = Contract.objects.create(dataset=ds, version_number=number, status=status, change_note=note)
            for index in range(rules):
                ValidationRule.objects.create(contract=contract, column_name=f"col{index}", rule_type="NOT_NULL")
            return contract

        def run(contract, name, status, day, rows=100):
            return ValidationRun.objects.create(contract=contract, submitted_by=cls.user, file_name=name,
                                                row_count=rows, status=status, started_at=when(day))

        def violation(the_run, resolution="OPEN", rows=3, rule=0):
            # One violation per rule per run (a model constraint): `rule` picks which.
            return Violation.objects.create(run=the_run, rule=the_run.contract.rules.order_by("pk")[rule],
                                            failed_row_count=rows, message="m", resolution=resolution)

        cls.enrollment = dataset("Monthly Enrollment Export", description="One row per student per term.")
        v1 = version(cls.enrollment, 1, "RETIRED", rules=1, note="Initial contract.")
        v2 = version(cls.enrollment, 2, "RETIRED", rules=2, note="Added uniqueness rule on student_id.")
        cls.v3 = version(cls.enrollment, 3, "ACTIVE", rules=3, note="Added AUDIT to allowed status values.")
        april = run(v1, "enrollment_2026_04.csv", "FAILED", 120, rows=4611)
        run(v2, "enrollment_2026_06.csv", "PASSED", 60, rows=4702)
        cls.august = run(v2, "enrollment_2026_08.csv", "FAILED", 1, rows=4812)
        violation(april, "DATA_ISSUE")
        violation(cls.august, "OPEN", rows=47)
        violation(cls.august, "CONTRACT_UPDATED", rows=4, rule=1)

        cls.older = dataset("Weekly Sales Extract", team="Finance")
        o1 = version(cls.older, 1, "RETIRED")
        o2 = version(cls.older, 2, "ACTIVE")
        run(o2, "sales_under_v2.csv", "PASSED", 10)
        run(o1, "sales_under_v1.csv", "FAILED", 1)

        cls.current = dataset("Payroll Deductions Export", team="Human Resources")
        run(version(cls.current, 1, "ACTIVE", rules=2), "payroll_2026_08.csv", "PASSED", 5, rows=3402)

        cls.draft = dataset("Course Catalog Snapshot", team="Provost Office")
        version(cls.draft, 1, "DRAFT", rules=3, note="Draft contract, not yet in use.")

        cls.empty = dataset("Facilities Work Orders", team="Operations")

        cls.errored = dataset("Library Circulation Log", team="University Library")
        run(version(cls.errored, 1, "ACTIVE"), "circulation_2026_08.csv", "ERROR", 3, rows=980)

    def setUp(self):
        self.client.force_login(self.user)

    def html(self, ds):
        response = self.client.get(reverse("data_quality:dataset-detail", args=[ds.pk]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def standing(self, ds):
        return section(self.html(ds), "standing")

    def item(self, ds, label):
        match = re.search(rf"<dt>{label}</dt>\s*<dd>(.*?)</dd>", self.standing(ds), re.S)
        self.assertIsNotNone(match, f"no {label} in Where it stands")
        return match.group(1)


# --- Where it stands ---------------------------------------------------------------------------------

class ContractInForceTests(DetailData):
    def test_the_active_version_is_named_with_its_active_stamp(self):
        item = self.item(self.enrollment, "Contract in force")
        self.assertEqual(text_of(item), "v3 Active 3 rules")
        self.assertIn('<span class="badge badge--active">Active</span>', item)

    def test_a_draft_only_dataset_has_no_active_version(self):
        item = self.item(self.draft, "Contract in force")
        self.assertEqual(text_of(item), "No active version No version is Active, so none governs validation.")
        self.assertNotIn("badge", item)
        self.assertNotIn("v1", item)

    def test_a_dataset_with_no_contract_has_no_active_version(self):
        self.assertEqual(text_of(self.item(self.empty, "Contract in force")),
                         "No active version No contract versions yet.")

    def test_the_highest_active_version_is_the_one_in_force(self):
        # No constraint stops two Active versions; the page picks the highest, as Contracts does.
        Contract.objects.create(dataset=self.current, version_number=2, status="ACTIVE")
        self.assertTrue(text_of(self.item(self.current, "Contract in force")).startswith("v2 Active"))


class LatestRunTests(DetailData):
    def test_the_latest_run_shows_its_file_date_outcome_and_version(self):
        item = self.item(self.enrollment, "Latest recorded run")
        self.assertIn('<span class="standing__value standing__file">enrollment_2026_08.csv</span>', item)
        self.assertIn('<span class="badge badge--failed">Failed</span>', item)
        self.assertIn("2026-08-31 &middot; checked against contract v2", item)

    def test_passed_failed_and_error_use_the_runs_own_labels(self):
        cases = ((self.current, "passed", "Passed"), (self.enrollment, "failed", "Failed"), (self.errored, "error", "Error"))
        for ds, slug, label in cases:
            with self.subTest(dataset=ds.name):
                self.assertIn(f'<span class="badge badge--{slug}">{label}</span>', self.item(ds, "Latest recorded run"))

    def test_an_errored_run_says_it_may_not_have_been_fully_checked(self):
        self.assertIn("This run ended in an error and may not have been fully checked.",
                      text_of(self.item(self.errored, "Latest recorded run")))
        self.assertNotIn("error", text_of(self.item(self.current, "Latest recorded run")).lower())

    def test_no_runs(self):
        for ds in (self.draft, self.empty):
            with self.subTest(dataset=ds.name):
                self.assertEqual(text_of(self.item(ds, "Latest recorded run")), "No validation runs recorded yet")

    def test_a_run_under_another_version_says_so_and_that_none_used_the_active_one(self):
        text = text_of(self.item(self.enrollment, "Latest recorded run"))
        self.assertIn("v3 is the version in force; this run used v2. No run recorded under v3 yet.", text)

    def test_an_older_run_under_the_active_version_rules_out_the_no_run_sentence(self):
        text = text_of(self.item(self.older, "Latest recorded run"))
        self.assertIn("v2 is the version in force; this run used v1.", text)
        self.assertNotIn("No run recorded under", text)

    def test_the_sentence_appears_once_the_check_is_true_and_goes_once_it_is_not(self):
        self.assertIn("No run recorded under v3 yet.", text_of(self.standing(self.enrollment)))
        ValidationRun.objects.create(contract=self.v3, submitted_by=self.user, file_name="old_under_v3.csv",
                                     row_count=1, status="PASSED", started_at=when(400))
        text = text_of(self.standing(self.enrollment))
        self.assertIn("v3 is the version in force; this run used v2.", text)
        self.assertNotIn("No run recorded under", text)

    def test_a_run_under_the_active_version_needs_no_note(self):
        text = text_of(self.item(self.current, "Latest recorded run"))
        self.assertNotIn("version in force", text)
        self.assertNotIn("No run recorded under", text)

    def test_no_active_version_never_claims_a_missing_run(self):
        Contract.objects.filter(dataset=self.enrollment, version_number=3).update(status="RETIRED")
        text = text_of(self.standing(self.enrollment))
        self.assertIn("No active version", text)
        self.assertNotIn("version in force", text)
        self.assertNotIn("No run recorded under", text)


class ViolationScopeTests(DetailData):
    def test_totals_say_all_runs_and_how_many_came_from_the_latest(self):
        item = self.item(self.enrollment, "Violations")
        self.assertEqual(text_of(item), "3 recorded across all runs 1 open · 2 from the latest run Go to violations")

    def test_none_open_and_none_from_a_later_clean_run(self):
        Violation.objects.filter(rule__contract__dataset=self.enrollment).update(resolution="DATA_ISSUE")
        ValidationRun.objects.create(contract=self.v3, submitted_by=self.user, file_name="enrollment_2026_09.csv",
                                     row_count=10, status="PASSED", started_at=when(0))
        self.assertIn("None open · none from the latest run", text_of(self.item(self.enrollment, "Violations")))

    def test_no_violations(self):
        self.assertEqual(text_of(self.item(self.current, "Violations")), "None recorded Go to violations")

    def test_the_jump_link_targets_the_existing_violations_section(self):
        html = self.html(self.enrollment)
        self.assertIn('<a class="standing__link" href="#violations">Go to violations</a>', section(html, "standing"))
        self.assertIn('<section class="panel" id="violations" aria-labelledby="violations-title">', html)


class StandingLayoutTests(DetailData):
    def test_source_and_owner_are_said_once_in_the_subtitle(self):
        html = self.html(self.enrollment)
        self.assertEqual(html.count("Source: Registrar &middot; Owner: detail_owner"), 1)
        standing = self.standing(self.enrollment)
        self.assertNotIn("Registrar", standing)
        self.assertNotIn("detail_owner", standing)

    def test_the_registered_date_stays_as_a_quiet_fact(self):
        registered = self.enrollment.created_at.strftime("%Y-%m-%d")
        self.assertIn(f'<div class="standing__item standing__item--quiet">\n                    <dt>Registered</dt>\n'
                      f'                    <dd>{registered}</dd>', self.standing(self.enrollment))

    def test_the_description_leads_under_the_subtitle(self):
        html = self.html(self.enrollment)
        header = html[html.index('<div class="page__header">'):html.index('<div class="page__actions">')]
        self.assertIn('<p class="dataset-lead">One row per student per term.</p>', header)
        self.assertNotIn('class="prose"', html)
        self.assertNotIn('class="dataset-lead"', self.html(self.current))  # no description, no empty paragraph

    def test_the_old_facts_panel_is_gone(self):
        html = self.html(self.enrollment)
        self.assertNotIn('<h2 class="panel__title">Dataset</h2>', html)
        self.assertNotIn('class="factlist"', html)

    def test_section_order_and_the_wide_frame(self):
        html = self.html(self.enrollment)
        self.assertIn('<main class="page" id="main" data-surface="dataset">', html)
        order = [html.index(f'id="{name}" aria-labelledby="{name}-title"') for name in ("standing", "versions", "runs", "violations")]
        self.assertEqual(order, sorted(order))
        self.assertEqual(html.count("<h1"), 1)
        self.assertEqual(re.findall(r'<h2 class="panel__title"[^>]*>([^<]+)</h2>', html),
                         ["Where it stands", "Contract versions", "Recorded runs", "Violations"])


# --- Recorded runs -----------------------------------------------------------------------------------

def run_rows(html):
    tbody = re.search(r"<tbody[^>]*>(.*?)</tbody>", section(html, "runs"), re.S).group(1)
    return [text_of(row) for row in re.findall(r"<tr role=\"row\">(.*?)</tr>", tbody, re.S)]


class RecordedRunsTests(DetailData):
    def test_every_run_newest_first_with_its_version_rows_and_outcome(self):
        self.assertEqual(run_rows(self.html(self.enrollment)), [
            "enrollment_2026_08.csv 2026-08-31 v2 4,812 Failed",
            "enrollment_2026_06.csv 2026-07-03 v2 4,702 Passed",
            "enrollment_2026_04.csv 2026-05-04 v1 4,611 Failed",
        ])

    def test_the_count_says_all_are_listed(self):
        self.assertIn('<p class="results__summary">3 runs recorded, newest first. All are listed.</p>',
                      section(self.html(self.enrollment), "runs"))
        self.assertIn("1 run recorded, newest first.", section(self.html(self.current), "runs"))

    def test_the_file_is_the_row_header_and_cells_are_labelled(self):
        runs = section(self.html(self.enrollment), "runs")
        self.assertIn('<th scope="row" role="rowheader" data-label="File">enrollment_2026_08.csv</th>', runs)
        for label in ("Date", "Contract", "Rows", "Outcome"):
            self.assertEqual(runs.count(f'role="cell" data-label="{label}"'), 3)
        self.assertIn('<caption class="visually-hidden">Recorded validation runs of Monthly Enrollment Export, newest first</caption>', runs)

    def test_an_error_run_is_listed_with_its_error_stamp(self):
        self.assertEqual(run_rows(self.html(self.errored)), ["circulation_2026_08.csv 2026-08-29 v1 980 Error"])

    def test_no_runs(self):
        runs = section(self.html(self.draft), "runs")
        self.assertIn("No validation runs recorded yet.", runs)
        self.assertNotIn('role="table"', runs)
        self.assertNotIn("results__summary", runs)

    def test_a_long_history_is_listed_in_full(self):
        contract = Contract.objects.get(dataset=self.current, version_number=1)
        for index in range(150):
            ValidationRun.objects.create(contract=contract, submitted_by=self.user, file_name=f"history_{index:03d}.csv",
                                         row_count=index, status="PASSED", started_at=when(10 + index))
        html = self.html(self.current)
        rows = run_rows(html)
        self.assertEqual(len(rows), 151)
        self.assertEqual([row.split()[0] for row in rows[1:]], [f"history_{index:03d}.csv" for index in range(150)])
        self.assertIn("151 runs recorded, newest first. All are listed.", html)


# --- Contract versions -------------------------------------------------------------------------------

def version_rows(html):
    tbody = re.search(r"<tbody[^>]*>(.*?)</tbody>", section(html, "versions"), re.S).group(1)
    return [text_of(row) for row in re.findall(r"<tr role=\"row\">(.*?)</tr>", tbody, re.S)]


class ContractVersionsTests(DetailData):
    def test_every_version_with_its_status_rule_count_and_note(self):
        self.assertEqual(version_rows(self.html(self.enrollment)), [
            "v3 Active 3 Added AUDIT to allowed status values.",
            "v2 Retired 2 Added uniqueness rule on student_id.",
            "v1 Retired 1 Initial contract.",
        ])

    def test_the_version_is_the_row_header(self):
        versions = section(self.html(self.enrollment), "versions")
        self.assertEqual(re.findall(r'<th scope="row" role="rowheader" data-label="Version">(v\d+)</th>', versions),
                         ["v3", "v2", "v1"])
        self.assertIn('<td role="cell" data-label="Rules" class="num">3</td>', versions)
        self.assertIn('<td role="cell" data-label="Change note" class="muted">', versions)

    def test_the_draft_keeps_its_draft_stamp(self):
        self.assertIn('<span class="badge badge--draft">Draft</span>', section(self.html(self.draft), "versions"))

    def test_the_contracts_link_uses_the_named_route_and_says_it_is_a_substring_search(self):
        versions = section(self.html(self.enrollment), "versions")
        href = reverse("data_quality:contract-search") + "?q=" + quote("Monthly Enrollment Export")
        self.assertIn(f'<a href="{href}">Open in Contracts</a>', versions)
        self.assertIn("Searches dataset names containing &ldquo;Monthly Enrollment Export&rdquo;, "
                      "so similar names can appear too.", versions)
        response = self.client.get(href)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["query"], "Monthly Enrollment Export")

    def test_a_name_with_reserved_characters_is_encoded(self):
        ds = Dataset.objects.create(name="Sensor Readings & Lab #3?", owner=self.user, source_team="Research")
        Contract.objects.create(dataset=ds, version_number=1, status="ACTIVE")
        href = reverse("data_quality:contract-search") + "?q=" + quote("Sensor Readings & Lab #3?")
        self.assertIn(f'<a href="{href}">Open in Contracts</a>', self.html(ds))
        self.assertEqual(self.client.get(href).context["query"], "Sensor Readings & Lab #3?")

    def test_no_contract_keeps_its_empty_state_and_has_no_contracts_link(self):
        html = self.html(self.empty)
        versions = section(html, "versions")
        self.assertIn("No contract versions yet for this dataset.", versions)
        self.assertNotIn("Open in Contracts", versions)
        self.assertNotIn('role="table"', versions)
        contracts_action, runs_action, violations_action = empty_state_actions(html)
        self.assertIn("+ New contract version", contracts_action)
        self.assertNotIn("btn", runs_action)
        self.assertIn("View / edit rules", versions)
        self.assertIn("Editing contract rules is not available yet.", versions)


# --- Protected and unchanged -------------------------------------------------------------------------

class ProtectedTests(DetailData):
    def test_the_stage_3d_violations_section_is_unchanged_byte_for_byte(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        start = text.index(VIOLATIONS_MARKER)
        end = text.index("    </section>\n", start) + len("    </section>\n")
        self.assertEqual(hashlib.sha256(text[start:end].encode("utf-8")).hexdigest(), VIOLATIONS_SHA256)

    def test_investigate_links_and_their_names_are_intact(self):
        violations = section(self.html(self.enrollment), "violations")
        self.assertEqual(violations.count(">Investigate<span class=\"visually-hidden\">"), 3)
        self.assertIn("3 violations recorded, newest run first. 1 is still open.", violations)

    def test_the_violations_empty_states_are_intact(self):
        self.assertIn("1 validation run recorded, none with a violation. 1 ended in an error and may not have been "
                      "fully checked.", text_of(section(self.html(self.errored), "violations")))
        self.assertIn("No validation runs have been recorded for this dataset yet.",
                      text_of(section(self.html(self.draft), "violations")))

    def test_the_breadcrumb_is_unchanged(self):
        html = self.html(self.enrollment)
        self.assertIn('<nav class="breadcrumbs" aria-label="Breadcrumb">', html)
        self.assertRegex(html, r'<li><a href="/datasets/">Datasets</a></li>\s*<li aria-current="page">Monthly Enrollment Export</li>')

    def test_the_page_still_needs_a_sign_in(self):
        self.client.logout()
        response = self.client.get(reverse("data_quality:dataset-detail", args=[self.enrollment.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(str(settings.LOGIN_URL)) or "/accounts/login/" in response["Location"])

    def test_unavailable_actions_are_unchanged(self):
        html = self.html(self.enrollment)
        self.assertEqual(html.count("btn--disabled"), 2)
        self.assertIn("Uploading files is not available yet.", html)


class QueryCountTests(DetailData):
    def count(self, ds):
        url = reverse("data_quality:dataset-detail", args=[ds.pk])
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.client.get(url).status_code, 200)
        return len(queries)

    def test_six_queries_whatever_the_dataset(self):
        # session, user, dataset, versions (rule counts annotated), runs, violations
        for ds in (self.enrollment, self.older, self.current, self.draft, self.empty, self.errored):
            with self.subTest(dataset=ds.name):
                self.assertEqual(self.count(ds), 6)

    def test_flat_as_versions_runs_and_violations_grow(self):
        before = self.count(self.enrollment)
        for number in range(4, 24):
            contract = Contract.objects.create(dataset=self.enrollment, version_number=number, status="RETIRED")
            rule = ValidationRule.objects.create(contract=contract, column_name="c", rule_type="NOT_NULL")
            the_run = ValidationRun.objects.create(contract=contract, submitted_by=self.user, file_name=f"f{number}.csv",
                                                   row_count=1, status="FAILED", started_at=when(500 + number))
            Violation.objects.create(run=the_run, rule=rule, failed_row_count=1, message="m")
        self.assertEqual(self.count(self.enrollment), before)


# --- Stylesheet --------------------------------------------------------------------------------------

class DetailStylesheetTests(StylesheetMixin, TestCase):
    def section(self):
        return self.css[self.css.index("/* ---- 25. dataset detail"):]

    def test_the_wide_frame_and_safe_wrapping(self):
        css = self.section()
        self.assertIn('.page[data-surface="dataset"] { max-width: 1200px; }', css)
        self.assertIn('.page[data-surface="dataset"] .page__title,\n.page[data-surface="dataset"] .breadcrumbs li '
                      '{ overflow-wrap: anywhere; }', css)
        self.assertRegex(css, r"\.dataset-lead \{[^}]*overflow-wrap: anywhere;")
        self.assertIn(".standing__file { overflow-wrap: anywhere; }", css)
        self.assertRegex(css, r'\.dtable tbody th\[scope="row"\] \{[^}]*overflow-wrap: anywhere;')

    def test_runs_and_versions_reflow_into_labelled_blocks_on_a_phone(self):
        phone = self.section()[self.section().index("@media (max-width: 40em)"):]
        self.assertIn(".dtable thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }", phone)
        self.assertIn("content: attr(data-label);", phone)
        self.assertIn(".panel:has(.dtable) { overflow: visible; background: var(--surface); }", phone)
        self.assertIn('.dtable [data-label="Change note"] { grid-column: 1 / -1; max-width: none; }', phone)
        self.assertNotRegex(phone, r"display:\s*none")

    def test_the_new_tables_do_not_use_the_violations_classes(self):
        self.assertNotIn(".vtable", re.sub(r"/\*.*?\*/", "", self.section(), flags=re.S))
        self.assertNotIn("vtable", section_markup_above_violations())

    def test_nothing_moves(self):
        css = re.sub(r"/\*.*?\*/", "", self.section(), flags=re.S)
        for banned in ("animation", "transition", "box-shadow", "gradient", "@keyframes"):
            self.assertNotIn(banned, css)
        self.assertNotRegex(css, r"(?<!text-)transform")  # text-transform (labels) is type, not motion


def section_markup_above_violations():
    text = TEMPLATE.read_text(encoding="utf-8")
    return text[:text.index(VIOLATIONS_MARKER)]

"""
Product redesign, Stage 3F - Contracts and Manage datasets.

Contracts: the status counts as one summary line in the search panel, and the
matching versions grouped by dataset in one table (one <tbody> per dataset,
headed by a rowgroup header that names the version in force), every matching
version visible, newest first. A status filter that leaves the active version
out says so. The Stage 3D violation lookup is unchanged, byte for byte.

Manage datasets: registration first; the registered datasets and their
source-team filter after it, with a link to the Dataset registry. A failed
registration reopens on the form (#register) with an error summary
(role="alert") that links to each field. Everything the view does is
unchanged: same form, validation, POST, redirect and message.

The browser side (layout, focus and scroll after a failed submission) is
recorded in docs/redesign/stage_3f/.
"""
import hashlib
import re
from html import unescape

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from data_quality.forms import DatasetForm
from data_quality.models import Contract, Dataset
from data_quality.tests import StylesheetMixin

CONTRACTS = reverse("data_quality:contract-search")
MANAGE = reverse("data_quality:dataset-manage")
TEMPLATE = "data_quality/templates/data_quality/contract_search.html"
# The Stage 3D violation lookup: from its Stage 3 comment to the end of the template.
LOOKUP_MARKER = "    {% comment %}\n        UX Stage 3: Home links straight here"
LOOKUP_SHA256 = "35b7fbb77edc20a7603c0a027ffb514ffa393134ef928f10d954bda770132b49"


def text_of(fragment):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


class ContractData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("contracts_owner", password="pw")
        cls.enrollment = Dataset.objects.create(name="Monthly Enrollment Export", owner=cls.user, source_team="Registrar")
        cls.catalog = Dataset.objects.create(name="Course Catalog Snapshot", owner=cls.user, source_team="Provost Office")
        cls.sales = Dataset.objects.create(name="Weekly Sales Extract", owner=cls.user, source_team="Finance")
        for v, status in ((1, "RETIRED"), (2, "RETIRED"), (3, "ACTIVE")):
            Contract.objects.create(dataset=cls.enrollment, version_number=v, status=status, change_note=f"Enrollment v{v}")
        Contract.objects.create(dataset=cls.catalog, version_number=1, status="DRAFT", change_note="")
        for v, status in ((1, "RETIRED"), (2, "ACTIVE")):
            Contract.objects.create(dataset=cls.sales, version_number=v, status=status, change_note=f"Sales v{v}")

    def setUp(self):
        self.client.force_login(self.user)

    def html(self, query=""):
        return self.client.get(CONTRACTS + query).content.decode()

    def table(self, html):
        start = html.index('<table class="datatable ctable"')
        return html[start:html.index("</table>", start)]

    def groups(self, html):
        """{dataset name: (heading text, [version row texts])} in page order."""
        result = {}
        for body in re.findall(r'<tbody role="rowgroup" class="ctable__group">(.*?)</tbody>', self.table(html), flags=re.S):
            head = re.search(r'<th scope="rowgroup"[^>]*>(.*?)</th>', body, flags=re.S).group(1)
            name = text_of(re.search(r"<a [^>]*>(.*?)</a>", head).group(1))
            rows = re.findall(r'<th scope="row"[^>]*>(v\d+)</th>', body)
            result[name] = (text_of(head), rows)
        return result


# --- Contracts: grouping ------------------------------------------------------------------------

class ContractGroupingTests(ContractData):
    def test_each_dataset_heads_its_group_once_and_every_version_is_shown(self):
        groups = self.groups(self.html())
        self.assertEqual(list(groups), ["Course Catalog Snapshot", "Monthly Enrollment Export", "Weekly Sales Extract"])
        self.assertEqual(sum(len(rows) for _, rows in groups.values()), Contract.objects.count())
        self.assertEqual(self.html().count('scope="rowgroup"'), 3)

    def test_versions_are_newest_first_within_a_group(self):
        groups = self.groups(self.html())
        self.assertEqual(groups["Monthly Enrollment Export"][1], ["v3", "v2", "v1"])
        self.assertEqual(groups["Weekly Sales Extract"][1], ["v2", "v1"])

    def test_each_heading_names_the_version_in_force(self):
        groups = self.groups(self.html())
        self.assertIn("Active version: v3", groups["Monthly Enrollment Export"][0])
        self.assertIn("Active version: v2", groups["Weekly Sales Extract"][0])
        self.assertIn("No active version", groups["Course Catalog Snapshot"][0])
        for heading, _ in groups.values():
            self.assertNotIn("not in these results", heading)

    def test_a_status_filter_that_hides_the_active_version_says_so(self):
        html = self.html("?status=RETIRED")
        groups = self.groups(html)
        self.assertEqual(list(groups), ["Monthly Enrollment Export", "Weekly Sales Extract"])
        self.assertEqual(groups["Monthly Enrollment Export"][1], ["v2", "v1"])
        self.assertIn("Active version: v3 (not in these results)", groups["Monthly Enrollment Export"][0])
        self.assertIn("Active version: v2 (not in these results)", groups["Weekly Sales Extract"][0])
        # No shown version is presented as active.
        self.assertNotIn("badge--active", self.table(html))

    def test_filtering_on_active_shows_the_active_version_without_the_note(self):
        groups = self.groups(self.html("?status=ACTIVE"))
        self.assertEqual({name: rows for name, (_, rows) in groups.items()},
                         {"Monthly Enrollment Export": ["v3"], "Weekly Sales Extract": ["v2"]})
        for heading, _ in groups.values():
            self.assertNotIn("not in these results", heading)

    def test_the_name_search_keeps_a_datasets_versions_together(self):
        groups = self.groups(self.html("?q=enroll"))
        self.assertEqual(list(groups), ["Monthly Enrollment Export"])
        self.assertEqual(groups["Monthly Enrollment Export"][1], ["v3", "v2", "v1"])

    def test_the_view_supplies_the_real_active_version_number(self):
        response = self.client.get(CONTRACTS + "?status=RETIRED")
        self.assertEqual({c.dataset.name: c.dataset_active_version for c in response.context["filtered_contracts"]},
                         {"Monthly Enrollment Export": 3, "Weekly Sales Extract": 2})

    def test_no_contract_actions_are_offered(self):
        table = text_of(self.table(self.html())).lower()
        for word in ("edit", "activate", "delete", "retire", "resolve"):
            self.assertNotRegex(table, rf"\b{word}\b")


class ContractSummaryAndSemanticsTests(ContractData):
    def test_the_summary_line_keeps_every_status_count(self):
        html = self.html()
        summary = re.search(r'<p class="contracts-summary">(.*?)</p>', html, flags=re.S).group(1)
        counts = dict(re.findall(r'<span class="badge badge--(\w+)">\w+</span>\s+<span class="contracts-summary__count">(\d+)</span>', summary))
        self.assertEqual(counts, {"active": "2", "draft": "1", "retired": "3"})
        self.assertNotIn("Contract status breakdown", html)  # the separate panel is gone

    def test_the_search_fields_and_parameters_are_unchanged(self):
        html = self.html("?q=Sales&status=ACTIVE")
        self.assertRegex(html, r'<form method="get" class="contracts-search__form" action="/contracts/search/">')
        self.assertIn('<input type="text" id="q" name="q" value="Sales"', html)
        self.assertRegex(html, r'<option value="ACTIVE"\s+selected>Active</option>')

    def test_cells_are_tied_to_their_dataset_version_and_column(self):
        table = self.table(self.html())
        self.assertIn('<th scope="col" role="columnheader" id="ct-version">Version</th>', table)
        enrollment_v3 = Contract.objects.get(dataset=self.enrollment, version_number=3)
        group = f"ct-ds-{self.enrollment.pk}"
        self.assertIn(f'<th scope="rowgroup" role="rowheader" colspan="3" id="{group}">', table)
        self.assertIn(f'<th scope="row" role="rowheader" id="ct-{enrollment_v3.pk}" headers="{group} ct-version" data-label="Version">v3</th>', table)
        self.assertIn(f'headers="{group} ct-{enrollment_v3.pk} ct-status" data-label="Status"', table)
        self.assertIn(f'headers="{group} ct-{enrollment_v3.pk} ct-note" data-label="Change note"', table)
        self.assertIn('<tbody role="rowgroup" class="ctable__group">', table)

    def test_the_empty_states_keep_their_words(self):
        self.assertIn("No contracts match that search.", self.html("?q=nothing-like-this"))
        Contract.objects.all().delete()
        self.assertIn("No contracts exist yet.", self.html())


class ContractQueryTests(ContractData):
    """Discovery baselines: GET 5 queries, lookup POST 7 (2 of each are the session and user)."""

    def counts(self):
        out = {}
        for label, call in (("get", lambda: self.client.get(CONTRACTS)),
                            ("filtered", lambda: self.client.get(CONTRACTS + "?status=RETIRED")),
                            ("lookup", lambda: self.client.post(CONTRACTS, {"dataset": "", "resolution": ""}))):
            from django.db import connection
            from django.test.utils import CaptureQueriesContext
            with CaptureQueriesContext(connection) as q:
                self.assertEqual(call().status_code, 200)
            out[label] = len(q)
        return out

    def test_query_counts_hold_the_baseline_and_stay_flat_as_versions_grow(self):
        self.assertEqual(self.counts(), {"get": 5, "filtered": 5, "lookup": 7})
        for i in range(5):
            ds = Dataset.objects.create(name=f"Grown {i}", owner=self.user, source_team="Growth")
            for v in range(1, 5):
                Contract.objects.create(dataset=ds, version_number=v, status="ACTIVE" if v == 4 else "RETIRED")
        self.assertEqual(self.counts(), {"get": 5, "filtered": 5, "lookup": 7})


class LookupPreservedTests(ContractData):
    def test_the_lookup_section_of_the_template_is_unchanged(self):
        source = open(TEMPLATE, encoding="utf-8").read()
        self.assertEqual(hashlib.sha256(source[source.index(LOOKUP_MARKER):].encode()).hexdigest(), LOOKUP_SHA256)

    def test_the_lookup_still_comes_after_the_contracts_and_still_posts(self):
        html = self.html("?resolution=OPEN")
        self.assertLess(html.index('id="contracts-results-title"'), html.index('id="violation-lookup"'))
        self.assertIn('<form method="post" action="/contracts/search/#violation-results">', html)
        self.assertIn("Open is selected. Press Look up violations to see them.", html)


class ContractStylesheetTests(StylesheetMixin, TestCase):
    def section(self):
        return self.css[self.css.index("/* ---- 24. contracts and manage"):]

    def test_both_pages_use_the_wide_frame(self):
        self.assertIn('.page[data-surface="contracts"],\n.page[data-surface="manage"] { max-width: 1200px; }', self.section())

    def test_versions_reflow_into_labelled_blocks_on_a_phone(self):
        phone = self.section()[self.section().index("@media (max-width: 40em)"):]
        self.assertIn(".ctable thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }", phone)
        self.assertIn("content: attr(data-label);", phone)
        self.assertIn(".panel.contracts-results { overflow: visible;", phone)
        self.assertNotRegex(phone, r"display:\s*none")

    def test_nothing_moves(self):
        css = re.sub(r"/\*.*?\*/", "", self.section(), flags=re.S)
        for banned in ("animation", "transition", "box-shadow", "gradient"):
            self.assertNotIn(banned, css)


# --- Manage datasets ---------------------------------------------------------------------------

class ManageData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("manage_owner", password="pw")
        cls.registrar = Dataset.objects.create(name="Monthly Enrollment Export", owner=cls.user, source_team="Registrar")
        Dataset.objects.create(name="Weekly Sales Extract", owner=cls.user, source_team="Finance")

    def setUp(self):
        self.client.force_login(self.user)

    def html(self, query=""):
        return self.client.get(MANAGE + query).content.decode()


class ManageLayoutTests(ManageData):
    def test_registration_comes_first_then_the_list(self):
        html = self.html()
        self.assertRegex(html, r"<h1[^>]*>\s*Manage datasets\s*</h1>")
        self.assertIn("<title>Manage datasets - DataPact</title>", html)
        self.assertLess(html.index("Register a new dataset"), html.index("Registered datasets"))
        self.assertLess(html.index('<form method="post"'), html.index('<form method="get" class="manage-filter"'))

    def test_the_filter_still_works_and_the_registry_is_linked(self):
        response = self.client.get(MANAGE + "?team=Regist")
        self.assertEqual(list(response.context["datasets"]), [self.registrar])
        html = response.content.decode()
        self.assertIn('<input type="text" id="team" name="team" value="Regist"', html)
        self.assertIn(f'href="{reverse("data_quality:dataset-list")}">Open the Dataset registry</a>', html)
        self.assertIn("No datasets match that filter.", self.html("?team=nobody"))

    def test_the_owner_placeholder_reads_choose_an_owner_and_stays_blank(self):
        self.assertIn('<option value="" selected>Choose an owner</option>', self.html())
        form = DatasetForm(data={"name": "X", "owner": "", "source_team": "Ops"})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["owner"], ["This field is required."])

    def test_no_error_summary_before_a_submission(self):
        self.assertNotIn('id="register-errors"', self.html())


class ManageErrorRecoveryTests(ManageData):
    def submit(self, **data):
        return self.client.post(MANAGE, {"name": "", "owner": "", "source_team": "", "description": "", **data})

    def summary(self, html):
        start = html.index('<div class="form-errors" id="register-errors" role="alert" tabindex="-1">')
        return html[start:html.index("</div>", start)]

    def test_a_failed_submission_returns_to_the_form_with_a_linked_summary(self):
        response = self.submit()
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(f'<form method="post" action="{MANAGE}#register">', html)
        # The section is the fragment's target but not focusable, so scrolling to it
        # does not take focus away from the summary (checked in a browser too).
        self.assertIn('<section class="panel manage-register" id="register" aria-labelledby="register-title">', html)
        links = re.findall(r'<a href="#(id_\w+)">([^<]+)</a>', self.summary(html))
        self.assertEqual(links, [("id_name", "Name: This field is required."),
                                 ("id_owner", "Owner: This field is required."),
                                 ("id_source_team", "Source team: This field is required.")])
        for field_id, _ in links:  # each link lands on a real input that names its error
            self.assertRegex(html, rf'id="{field_id}"[^>]*aria-describedby="{field_id}_error"|aria-describedby="{field_id}_error"[^>]*id="{field_id}"')
            self.assertRegex(html, rf'<(input|select)[^>]*aria-invalid="true"[^>]*id="{field_id}"|<(input|select)[^>]*id="{field_id}"[^>]*aria-invalid="true"')
            self.assertIn(f'id="{field_id}_error"', html)  # the field's own error stays

    def test_the_summary_takes_focus(self):
        html = self.submit().content.decode()
        self.assertIn('window.addEventListener("load", function () {', html)
        self.assertIn('var summary = document.getElementById("register-errors");', html)
        self.assertIn("window.requestAnimationFrame(function () { summary.focus(); });", html)

    def test_a_duplicate_name_is_still_rejected_and_named_in_the_summary(self):
        response = self.submit(name="Monthly Enrollment Export", owner=self.user.pk, source_team="Registrar")
        self.assertEqual(Dataset.objects.filter(name="Monthly Enrollment Export").count(), 1)
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertIn('<a href="#id_name">', self.summary(response.content.decode()))

    def test_a_valid_registration_behaves_as_before(self):
        response = self.client.post(MANAGE, {"name": "Facilities Work Orders", "owner": self.user.pk,
                                             "source_team": "Operations", "description": ""})
        dataset = Dataset.objects.get(name="Facilities Work Orders")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, dataset.get_absolute_url())
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertEqual(messages, ['Registered dataset "Facilities Work Orders".'])

    def test_the_tested_labels_stay(self):
        html = self.html()
        self.assertIn(">Source team</th>", html)
        self.assertRegex(html, r'<label for="[^"]+">Source team</label>')
        self.assertIn(">Register dataset</button>", html)


class ManageQueryTests(ManageData):
    """Discovery baseline: 4 queries (session, user, datasets, the owner choices)."""

    def test_get_filter_and_invalid_post_stay_at_four(self):
        for label, call in (("get", lambda: self.client.get(MANAGE)), ("filter", lambda: self.client.get(MANAGE + "?team=Reg")),
                            ("invalid post", lambda: self.client.post(MANAGE, {"name": ""}))):
            with self.subTest(request=label), self.assertNumQueries(4):
                self.assertEqual(call().status_code, 200)

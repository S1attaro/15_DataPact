import importlib
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.db.models import QuerySet
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import resolve, reverse

from . import views
from . import charts
from .models import Contract, Dataset, ValidationRule, ValidationRun, Violation


class DatasetOverviewViewTests(TestCase):
    """Base CBV (django.views.View) at data_quality:dataset-cbv-base."""

    def test_empty_state_renders_without_error(self):
        response = self.client.get(reverse("data_quality:dataset-cbv-base"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "data_quality/dataset_overview.html")
        self.assertContains(response, "No datasets registered yet")
        self.assertEqual(list(response.context["rows"]), [])

    def test_shows_dataset_with_no_active_contract(self):
        owner = User.objects.create_user("owner1", password="pw")
        dataset = Dataset.objects.create(
            name="Monthly Enrollment Export", owner=owner, source_team="Registrar"
        )
        Contract.objects.create(
            dataset=dataset, version_number=1, status=Contract.Status.DRAFT
        )
        response = self.client.get(reverse("data_quality:dataset-cbv-base"))
        row = response.context["rows"][0]
        self.assertEqual(row["dataset"], dataset)
        self.assertEqual(row["contract_count"], 1)
        self.assertIsNone(row["active_contract"])

    def test_computes_contract_count_and_active_version(self):
        owner = User.objects.create_user("owner1", password="pw")
        dataset = Dataset.objects.create(
            name="Monthly Enrollment Export", owner=owner, source_team="Registrar"
        )
        Contract.objects.create(
            dataset=dataset, version_number=1, status=Contract.Status.RETIRED
        )
        active = Contract.objects.create(
            dataset=dataset, version_number=2, status=Contract.Status.ACTIVE
        )
        response = self.client.get(reverse("data_quality:dataset-cbv-base"))
        row = response.context["rows"][0]
        self.assertEqual(row["contract_count"], 2)
        self.assertEqual(row["active_contract"], active)


class DatasetListViewTests(TestCase):
    """Generic CBV: ListView at data_quality:dataset-list."""

    def test_empty_state(self):
        response = self.client.get(reverse("data_quality:dataset-list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "data_quality/dataset_list.html")
        self.assertContains(response, "No datasets registered yet")
        self.assertEqual(list(response.context["datasets"]), [])

    def test_lists_datasets_ordered_by_name(self):
        owner = User.objects.create_user("owner1", password="pw")
        Dataset.objects.create(name="Weekly Sales Extract", owner=owner, source_team="Sales")
        Dataset.objects.create(name="Course Catalog Snapshot", owner=owner, source_team="Registrar")

        response = self.client.get(reverse("data_quality:dataset-list"))
        names = [d.name for d in response.context["datasets"]]
        self.assertEqual(names, ["Course Catalog Snapshot", "Weekly Sales Extract"])


class DatasetDetailViewTests(TestCase):
    """Generic CBV: DetailView at data_quality:dataset-detail."""

    def setUp(self):
        self.owner = User.objects.create_user("owner1", password="pw")
        self.dataset = Dataset.objects.create(
            name="Monthly Enrollment Export",
            owner=self.owner,
            source_team="Registrar",
        )

    def test_detail_shows_dataset_and_empty_contract_state(self):
        response = self.client.get(
            reverse("data_quality:dataset-detail", args=[self.dataset.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "data_quality/dataset_detail.html")
        self.assertEqual(response.context["dataset"], self.dataset)
        self.assertContains(response, "No contract versions yet")

    def test_detail_lists_contract_versions(self):
        Contract.objects.create(
            dataset=self.dataset, version_number=1, status=Contract.Status.RETIRED
        )
        Contract.objects.create(
            dataset=self.dataset, version_number=2, status=Contract.Status.ACTIVE
        )
        response = self.client.get(
            reverse("data_quality:dataset-detail", args=[self.dataset.pk])
        )
        versions = [c.version_number for c in response.context["contracts"]]
        self.assertEqual(sorted(versions), [1, 2])

    def test_unknown_dataset_returns_404(self):
        response = self.client.get(
            reverse("data_quality:dataset-detail", args=[9999])
        )
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------
# Section 3 - Templates / UI
# Author: Ashok Chacko (aschacko)
#
# These tests cover the template layer rather than the views: that
# every page really does inherit the shell from base.html, that the
# {% empty %} branches fire, and that the registry template does not
# depend on the kind of view that rendered it.
# ---------------------------------------------------------------

class BaseTemplateInheritanceTests(TestCase):
    """Section 3A: base.html is the single source of the site shell."""

    def setUp(self):
        self.owner = User.objects.create_user("owner1", password="pw")
        self.dataset = Dataset.objects.create(
            name="Monthly Enrollment Export", owner=self.owner, source_team="Registrar"
        )

    def test_every_page_inherits_base(self):
        urls = [
            reverse("data_quality:dataset-list"),
            reverse("data_quality:dataset-cbv-base"),
            reverse("data_quality:dataset-detail", args=[self.dataset.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertTemplateUsed(response, "data_quality/base.html")
                # Shell pieces that only base.html provides.
                self.assertContains(response, "DATA<span>PACT</span>", html=False)
                self.assertContains(response, "INFO 490 Team 15")

    def test_title_block_is_overridden_per_page(self):
        response = self.client.get(reverse("data_quality:dataset-list"))
        self.assertContains(response, "<title>Dataset Registry - DataPact</title>", html=False)

        response = self.client.get(
            reverse("data_quality:dataset-detail", args=[self.dataset.pk])
        )
        self.assertContains(
            response, "<title>Monthly Enrollment Export - DataPact</title>", html=False
        )

    def test_current_page_is_marked_in_the_nav(self):
        response = self.client.get(reverse("data_quality:dataset-list"))
        self.assertContains(response, 'class="is-active"')


class EmptyStateTests(TestCase):
    """Section 3B: the {% empty %} branch and the shared empty-state partial."""

    def test_registry_empty_state_uses_the_shared_partial(self):
        response = self.client.get(reverse("data_quality:dataset-list"))
        self.assertTemplateUsed(response, "data_quality/includes/_empty_state.html")
        self.assertContains(response, "No datasets registered yet")
        self.assertContains(response, "Register your first dataset")

    def test_registry_hides_column_headers_when_there_is_nothing_to_show(self):
        response = self.client.get(reverse("data_quality:dataset-list"))
        self.assertNotContains(response, "SOURCE TEAM")
        self.assertNotContains(response, "<thead>", html=False)

    def test_detail_empty_state_is_about_contracts_not_datasets(self):
        owner = User.objects.create_user("owner1", password="pw")
        dataset = Dataset.objects.create(
            name="Weekly Sales Extract", owner=owner, source_team="Finance"
        )
        response = self.client.get(
            reverse("data_quality:dataset-detail", args=[dataset.pk])
        )
        self.assertTemplateUsed(response, "data_quality/includes/_empty_state.html")
        self.assertContains(response, "No contract versions yet")
        self.assertNotContains(response, "No datasets registered yet")


class TemplateReuseTests(TestCase):
    """
    Section 3C: dataset_list.html is written against one context variable and
    nothing else, so any view can render it.

    Rendering it directly - no view, no URL, just a context dict - is the
    proof. If this passes, a function-based view calling render() with the
    same dict gets the same page.
    """

    def setUp(self):
        self.owner = User.objects.create_user("owner1", password="pw")
        Dataset.objects.create(
            name="Monthly Enrollment Export", owner=self.owner, source_team="Registrar"
        )

    def test_renders_from_a_plain_context_dict(self):
        html = render_to_string(
            "data_quality/dataset_list.html",
            {"datasets": Dataset.objects.select_related("owner")},
        )
        self.assertIn("Monthly Enrollment Export", html)
        self.assertIn("Registrar", html)

    def test_view_label_is_overridable_and_defaults_to_the_listview(self):
        html = render_to_string(
            "data_quality/dataset_list.html",
            {
                "datasets": Dataset.objects.all(),
                "view_label": "Function-based view - render()",
            },
        )
        self.assertIn("Function-based view - render()", html)

        response = self.client.get(reverse("data_quality:dataset-list"))
        self.assertContains(response, "Generic CBV - ListView")

    def test_empty_state_still_fires_without_a_view(self):
        html = render_to_string("data_quality/dataset_list.html", {"datasets": []})
        self.assertIn("No datasets registered yet", html)


# ---------------------------------------------------------------
# Tejas Jaggi: render() FBV, template reuse, split settings/security
# ---------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_DIR = REPO_ROOT / "datapact_project" / "settings"
EMPTY_STATE_MESSAGE = "No datasets registered yet"

# Looks like a real key to the production checks but is only ever used here.
VALID_TEST_KEY = "unit-test-only-key-" + "x" * 40


def load_settings(mode, **env):
    """
    Re-import settings/base.py and settings/<mode>.py with `env` layered over
    the real environment, and return the mode module.

    Both modules validate their configuration at import time, so the only way
    to observe them under different values is to reload them. `patch.dict`
    restores os.environ on exit; `restore_settings_modules()` resets the
    module objects so nothing leaks into later tests.
    """
    with patch.dict(os.environ, env):
        importlib.reload(importlib.import_module("datapact_project.settings.base"))
        return importlib.reload(importlib.import_module(f"datapact_project.settings.{mode}"))


def restore_settings_modules():
    """Put base/development back to real-environment state; drop production so
    its next import starts clean (it may have raised part-way through)."""
    sys.modules.pop("datapact_project.settings.production", None)
    importlib.reload(importlib.import_module("datapact_project.settings.base"))
    importlib.reload(importlib.import_module("datapact_project.settings.development"))


class DatasetRenderViewTests(TestCase):
    """FBV using render() at data_quality:dataset-render (Section 2, View 2)."""

    url = "/datasets/render/"

    def make_dataset(self, name, owner, source_team="Registrar"):
        return Dataset.objects.create(name=name, owner=owner, source_team=source_team)

    def test_url_name_and_path(self):
        self.assertEqual(reverse("data_quality:dataset-render"), self.url)
        match = resolve(self.url)
        self.assertIs(match.func, views.dataset_render)
        self.assertEqual(match.view_name, "data_quality:dataset-render")

    def test_status_and_templates(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "data_quality/dataset_list.html")
        self.assertTemplateUsed(response, "data_quality/base.html")

    def test_context_holds_dataset_queryset(self):
        response = self.client.get(self.url)
        self.assertIn("datasets", response.context)
        datasets = response.context["datasets"]
        self.assertIsInstance(datasets, QuerySet)
        self.assertIs(datasets.model, Dataset)

    def test_populated_state_lists_every_dataset(self):
        owner = User.objects.create_user("owner1", password="pw")
        self.make_dataset("Weekly Sales Extract", owner, source_team="Sales")
        self.make_dataset("Course Catalog Snapshot", owner)

        response = self.client.get(self.url)
        self.assertContains(response, "Weekly Sales Extract")
        self.assertContains(response, "Course Catalog Snapshot")
        self.assertNotContains(response, EMPTY_STATE_MESSAGE)
        names = [d.name for d in response.context["datasets"]]
        self.assertEqual(names, ["Course Catalog Snapshot", "Weekly Sales Extract"])

    def test_empty_state_message(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["datasets"]), [])
        self.assertContains(response, EMPTY_STATE_MESSAGE)

    def test_reuses_listview_template(self):
        owner = User.objects.create_user("owner1", password="pw")
        self.make_dataset("Monthly Enrollment Export", owner)

        fbv = self.client.get(self.url)
        cbv = self.client.get(reverse("data_quality:dataset-list"))
        self.assertEqual(fbv.templates[0].name, "data_quality/dataset_list.html")
        self.assertEqual(fbv.templates[0].name, cbv.templates[0].name)
        self.assertEqual(list(fbv.context["datasets"]), list(cbv.context["datasets"]))

    def test_owner_is_fetched_with_datasets(self):
        owners = [User.objects.create_user(f"owner{i}", password="pw") for i in range(3)]
        for i, owner in enumerate(owners):
            self.make_dataset(f"Dataset {i}", owner)

        # One SELECT for datasets joined to owners; no per-row owner lookups
        # when the template prints dataset.owner.username.
        with self.assertNumQueries(1):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for owner in owners:
            self.assertContains(response, owner.username)

    def test_view_label_names_the_render_fbv(self):
        # The template's caption defaults to the ListView, so the FBV has to
        # pass view_label itself for /datasets/render/ to be identifiable.
        response = self.client.get(reverse("data_quality:dataset-render"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "data_quality/dataset_list.html")
        self.assertContains(response, "Function-based view - render()")
        self.assertNotContains(response, "Generic CBV - ListView (DatasetListView)")


class SettingsSplitTests(TestCase):
    """Split settings and .env handling (Section 1A/1B)."""

    def tearDown(self):
        restore_settings_modules()

    def test_database_is_repo_root_db_sqlite3(self):
        # settings.DATABASES is rewritten by the test runner, so check the
        # freshly loaded modules. Guards the BASE_DIR depth after the move to
        # settings/base.py.
        self.assertEqual(Path(settings.BASE_DIR), REPO_ROOT)
        for mode, hosts in (("development", ""), ("production", "localhost")):
            with self.subTest(mode=mode):
                module = load_settings(
                    mode, SECRET_KEY=VALID_TEST_KEY, ALLOWED_HOSTS=hosts, DATABASE_NAME=""
                )
                self.assertEqual(Path(module.BASE_DIR), REPO_ROOT)
                self.assertEqual(
                    Path(module.DATABASES["default"]["NAME"]), REPO_ROOT / "db.sqlite3"
                )

    def test_development_debug_true_with_local_fallback_hosts(self):
        dev = load_settings("development", SECRET_KEY=VALID_TEST_KEY, ALLOWED_HOSTS="", DATABASE_NAME="")
        self.assertIs(dev.DEBUG, True)
        self.assertEqual(dev.ALLOWED_HOSTS, ["localhost", "127.0.0.1"])

    def test_production_debug_false_and_parses_hosts(self):
        prod = load_settings(
            "production",
            SECRET_KEY=VALID_TEST_KEY,
            ALLOWED_HOSTS=" datapact.example.com , ,127.0.0.1 ",
            DATABASE_NAME="",
        )
        self.assertIs(prod.DEBUG, False)
        self.assertEqual(prod.ALLOWED_HOSTS, ["datapact.example.com", "127.0.0.1"])

    def test_production_requires_allowed_hosts(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "ALLOWED_HOSTS is empty"):
            load_settings("production", SECRET_KEY=VALID_TEST_KEY, ALLOWED_HOSTS="", DATABASE_NAME="")

    def test_production_rejects_insecure_secret_key(self):
        for bad_key in ("django-insecure-" + "y" * 40, "replace-with-a-new-random-key"):
            with self.subTest(key=bad_key[:16]):
                with self.assertRaisesMessage(ImproperlyConfigured, "SECRET_KEY"):
                    load_settings(
                        "production", SECRET_KEY=bad_key, ALLOWED_HOSTS="localhost", DATABASE_NAME=""
                    )

    def test_development_accepts_insecure_key_only_production_refuses(self):
        dev = load_settings(
            "development", SECRET_KEY="django-insecure-" + "y" * 40, ALLOWED_HOSTS="", DATABASE_NAME=""
        )
        self.assertTrue(dev.SECRET_KEY.startswith("django-insecure-"))

    def test_require_env_rejects_missing_and_blank_values(self):
        base = importlib.import_module("datapact_project.settings.base")
        name = "DATAPACT_TEST_ONLY_VAR"

        with patch.dict(os.environ):
            os.environ.pop(name, None)
            with self.assertRaises(ImproperlyConfigured) as cm:
                base.require_env(name)
        self.assertIn(name, str(cm.exception))
        self.assertIn(".env.example", str(cm.exception))

        for blank in ("", "   "):
            with self.subTest(value=repr(blank)), patch.dict(os.environ, {name: blank}):
                with self.assertRaisesMessage(ImproperlyConfigured, ".env.example"):
                    base.require_env(name)

        with patch.dict(os.environ, {name: "  value  "}):
            self.assertEqual(base.require_env(name), "value")

    def test_no_literal_secret_key_in_settings_source(self):
        literal_assignment = re.compile(r"^\s*SECRET_KEY\s*=\s*['\"]", re.MULTILINE)
        real_looking_key = re.compile(r"django-insecure-[^'\"\s]{20,}")
        for path in sorted(SETTINGS_DIR.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertIsNone(literal_assignment.search(source))
                self.assertIsNone(real_looking_key.search(source))

    def test_database_name_override_is_development_only(self):
        dev = load_settings(
            "development", SECRET_KEY=VALID_TEST_KEY, ALLOWED_HOSTS="", DATABASE_NAME="db.local.sqlite3"
        )
        self.assertEqual(Path(dev.DATABASES["default"]["NAME"]), REPO_ROOT / "db.local.sqlite3")

        prod = load_settings(
            "production", SECRET_KEY=VALID_TEST_KEY, ALLOWED_HOSTS="localhost", DATABASE_NAME="db.local.sqlite3"
        )
        self.assertEqual(Path(prod.DATABASES["default"]["NAME"]), REPO_ROOT / "db.sqlite3")


# ---------------------------------------------------------------
# Section 2: ContractSearchView
# Author: Hriday Agarwal
# ---------------------------------------------------------------

class ContractSearchViewGetTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner1", password="pw")
        self.enrollment = Dataset.objects.create(
            name="Monthly Enrollment Export", owner=self.owner, source_team="Registrar"
        )
        self.sales = Dataset.objects.create(
            name="Weekly Sales Extract", owner=self.owner, source_team="Finance"
        )
        Contract.objects.create(
            dataset=self.enrollment, version_number=1, status=Contract.Status.RETIRED
        )
        Contract.objects.create(
            dataset=self.enrollment, version_number=2, status=Contract.Status.ACTIVE
        )
        Contract.objects.create(
            dataset=self.sales, version_number=1, status=Contract.Status.DRAFT
        )

    def test_no_filter_lists_every_contract_and_correct_total(self):
        response = self.client.get(reverse("data_quality:contract-search"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "data_quality/contract_search.html")
        self.assertEqual(response.context["total_contracts"], 3)
        self.assertEqual(len(response.context["filtered_contracts"]), 3)
        self.assertIsNone(response.context["violation_results"])

    def test_query_param_filters_by_related_dataset_name(self):
        response = self.client.get(reverse("data_quality:contract-search"), {"q": "Enrollment"})
        contracts = list(response.context["filtered_contracts"])
        self.assertEqual(len(contracts), 2)
        self.assertTrue(all(c.dataset_id == self.enrollment.pk for c in contracts))

    def test_status_param_filters_exact(self):
        response = self.client.get(reverse("data_quality:contract-search"), {"status": "ACTIVE"})
        contracts = list(response.context["filtered_contracts"])
        self.assertEqual(len(contracts), 1)
        self.assertEqual(contracts[0].status, Contract.Status.ACTIVE)

    def test_query_and_status_combine(self):
        response = self.client.get(
            reverse("data_quality:contract-search"), {"q": "Enrollment", "status": "RETIRED"}
        )
        contracts = list(response.context["filtered_contracts"])
        self.assertEqual(len(contracts), 1)
        self.assertEqual(contracts[0].version_number, 1)

    def test_no_match_shows_empty_state(self):
        response = self.client.get(reverse("data_quality:contract-search"), {"q": "Nonexistent"})
        self.assertEqual(len(response.context["filtered_contracts"]), 0)
        self.assertContains(response, "No contracts match that search.")

    def test_status_breakdown_groups_and_counts(self):
        response = self.client.get(reverse("data_quality:contract-search"))
        breakdown = {row["status"]: row["total"] for row in response.context["status_breakdown"]}
        self.assertEqual(breakdown, {"ACTIVE": 1, "DRAFT": 1, "RETIRED": 1})

    def test_empty_database_aggregation_shows_empty_state(self):
        Contract.objects.all().delete()
        response = self.client.get(reverse("data_quality:contract-search"))
        self.assertEqual(response.context["total_contracts"], 0)
        self.assertContains(response, "No contracts exist yet.")


class ContractSearchViewPostTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user("owner1", password="pw")
        dataset = Dataset.objects.create(
            name="Monthly Enrollment Export", owner=owner, source_team="Registrar"
        )
        other_dataset = Dataset.objects.create(
            name="Weekly Sales Extract", owner=owner, source_team="Finance"
        )
        contract = Contract.objects.create(
            dataset=dataset, version_number=1, status=Contract.Status.ACTIVE
        )
        other_contract = Contract.objects.create(
            dataset=other_dataset, version_number=1, status=Contract.Status.ACTIVE
        )
        rule = ValidationRule.objects.create(
            contract=contract, column_name="credit_hours", rule_type=ValidationRule.RuleType.RANGE
        )
        other_rule = ValidationRule.objects.create(
            contract=other_contract, column_name="amount", rule_type=ValidationRule.RuleType.RANGE
        )
        run = contract.runs.create(file_name="f.csv", row_count=10, status="FAILED")
        other_run = other_contract.runs.create(file_name="g.csv", row_count=5, status="FAILED")
        self.violation = Violation.objects.create(
            run=run, rule=rule, failed_row_count=3, message="out of range",
            resolution=Violation.Resolution.OPEN,
        )
        self.other_violation = Violation.objects.create(
            run=other_run, rule=other_rule, failed_row_count=1, message="out of range",
            resolution=Violation.Resolution.DATA_ISSUE,
        )

    def test_get_does_not_run_the_violation_lookup(self):
        response = self.client.get(reverse("data_quality:contract-search"))
        self.assertIsNone(response.context["violation_results"])

    def test_post_filters_by_related_dataset_name(self):
        response = self.client.post(
            reverse("data_quality:contract-search"), {"dataset": "Enrollment", "resolution": ""}
        )
        self.assertEqual(response.status_code, 200)
        results = list(response.context["violation_results"])
        self.assertEqual(results, [self.violation])

    def test_post_filters_by_resolution_exact(self):
        response = self.client.post(
            reverse("data_quality:contract-search"), {"dataset": "", "resolution": "DATA_ISSUE"}
        )
        results = list(response.context["violation_results"])
        self.assertEqual(results, [self.other_violation])

    def test_post_with_no_filters_returns_all_violations(self):
        response = self.client.post(
            reverse("data_quality:contract-search"), {"dataset": "", "resolution": ""}
        )
        self.assertEqual(len(response.context["violation_results"]), 2)

    def test_post_no_match_shows_empty_state(self):
        response = self.client.post(
            reverse("data_quality:contract-search"), {"dataset": "Nonexistent", "resolution": ""}
        )
        self.assertEqual(len(response.context["violation_results"]), 0)
        self.assertContains(response, "No violations matched that lookup.")

    def test_post_requires_csrf_token_from_a_real_browser_form(self):
        self.client.handler.enforce_csrf_checks = True
        response = self.client.post(
            reverse("data_quality:contract-search"), {"dataset": "", "resolution": ""}
        )
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------
# Section 5: DatasetManageView
# Author: Hriday Agarwal
# ---------------------------------------------------------------

class DatasetManageViewGetTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner1", password="pw")
        self.registrar_ds = Dataset.objects.create(
            name="Monthly Enrollment Export", owner=self.owner, source_team="Registrar"
        )
        self.finance_ds = Dataset.objects.create(
            name="Weekly Sales Extract", owner=self.owner, source_team="Finance"
        )

    def test_no_filter_lists_every_dataset(self):
        response = self.client.get(reverse("data_quality:dataset-manage"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "data_quality/dataset_manage.html")
        self.assertEqual(len(response.context["datasets"]), 2)

    def test_team_query_param_filters_by_source_team(self):
        response = self.client.get(reverse("data_quality:dataset-manage"), {"team": "Regist"})
        datasets = list(response.context["datasets"])
        self.assertEqual(datasets, [self.registrar_ds])
        self.assertEqual(response.context["team"], "Regist")

    def test_no_match_shows_empty_state(self):
        response = self.client.get(reverse("data_quality:dataset-manage"), {"team": "Nonexistent"})
        self.assertEqual(len(response.context["datasets"]), 0)
        self.assertContains(response, "No datasets match that filter.")

    def test_get_form_is_unbound_and_has_no_errors(self):
        response = self.client.get(reverse("data_quality:dataset-manage"))
        self.assertFalse(response.context["form"].is_bound)


class DatasetManageViewPostTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner1", password="pw")

    def _payload(self, **overrides):
        payload = {
            "name": "Facilities Work Orders",
            "owner": self.owner.pk,
            "source_team": "Operations",
            "description": "",
        }
        payload.update(overrides)
        return payload

    def test_valid_post_creates_dataset_and_redirects_to_its_detail_page(self):
        response = self.client.post(reverse("data_quality:dataset-manage"), self._payload())
        self.assertEqual(response.status_code, 302)
        dataset = Dataset.objects.get(name="Facilities Work Orders", owner=self.owner)
        self.assertEqual(response.url, dataset.get_absolute_url())

    def test_redirect_target_shows_success_message(self):
        response = self.client.post(
            reverse("data_quality:dataset-manage"), self._payload(), follow=True
        )
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("Facilities Work Orders", str(messages[0]))

    def test_missing_required_field_is_rejected_without_creating_a_row(self):
        response = self.client.post(reverse("data_quality:dataset-manage"), self._payload(name=""))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Dataset.objects.filter(source_team="Operations").exists())
        self.assertTrue(response.context["form"].errors)

    def test_duplicate_owner_and_name_is_rejected_by_model_constraint(self):
        Dataset.objects.create(
            name="Facilities Work Orders", owner=self.owner, source_team="Operations"
        )
        response = self.client.post(reverse("data_quality:dataset-manage"), self._payload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Dataset.objects.filter(name="Facilities Work Orders", owner=self.owner).count(), 1
        )
        self.assertTrue(response.context["form"].errors)

    def test_team_filter_survives_a_failed_submission(self):
        response = self.client.post(
            reverse("data_quality:dataset-manage"), self._payload(name="", team="Operations")
        )
        self.assertEqual(response.context["team"], "Operations")

    def test_post_requires_csrf_token_from_a_real_browser_form(self):
        self.client.handler.enforce_csrf_checks = True
        response = self.client.post(reverse("data_quality:dataset-manage"), self._payload())
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Dataset.objects.filter(source_team="Operations").exists())


# ---------------------------------------------------------------
# A3 Section 1 (URL linking & navigation) and Section 4 (Matplotlib
# visualization)
# Author: Tejas Jaggi (tejasj2)
# ---------------------------------------------------------------

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "data_quality"


def nav_links(html):
    """Return every href in the site header of a rendered page."""
    header = html[html.index("<header"):html.index("</header>")]
    return re.findall(r'<a[^>]+href="([^"]+)"', header)


class HomePageTests(TestCase):
    """The root URL is a real page, not a 404 (Section 1)."""

    def test_home_route_reverses_to_the_site_root(self):
        self.assertEqual(reverse("data_quality:home"), "/")

    def test_root_url_resolves_to_the_home_view(self):
        self.assertEqual(resolve("/").view_name, "data_quality:home")

    def test_home_page_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "data_quality/home.html")
        self.assertTemplateUsed(response, "data_quality/base.html")

    def test_home_page_links_to_the_main_sections(self):
        response = self.client.get("/")
        for route in (
            "data_quality:dataset-list",
            "data_quality:dataset-cbv-base",
            "data_quality:quality-history",
        ):
            with self.subTest(route=route):
                self.assertContains(response, f'href="{reverse(route)}"')

    def test_home_page_summary_counts_come_from_the_database(self):
        owner = User.objects.create_user("owner1", password="pw")
        dataset = Dataset.objects.create(
            name="Monthly Enrollment Export", owner=owner, source_team="Registrar"
        )
        contract = Contract.objects.create(
            dataset=dataset, version_number=1, status=Contract.Status.ACTIVE
        )
        ValidationRun.objects.create(
            contract=contract,
            file_name="enrollment_2026_09.csv",
            row_count=10,
            status=ValidationRun.Status.PASSED,
        )
        response = self.client.get("/")
        self.assertEqual(response.context["dataset_count"], 1)
        self.assertEqual(response.context["run_count"], 1)

    def test_home_page_works_on_an_empty_database(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["dataset_count"], 0)


class NavigationTests(TestCase):
    """Site navigation is reversed, not hard-coded (Section 1)."""

    def test_navigation_offers_at_least_three_working_links(self):
        html = self.client.get("/").content.decode()
        hrefs = {href for href in nav_links(html) if href.startswith("/")}
        self.assertGreaterEqual(len(hrefs), 3)
        for href in hrefs:
            with self.subTest(href=href):
                self.assertEqual(self.client.get(href).status_code, 200)

    def test_quality_history_is_reachable_from_the_navigation(self):
        html = self.client.get("/").content.decode()
        self.assertIn(reverse("data_quality:quality-history"), nav_links(html))

    def test_templates_do_not_hard_code_application_paths(self):
        # Every internal link must come from {% url %} or get_absolute_url so
        # that renaming a route cannot silently break navigation.
        offenders = []
        for template in sorted(TEMPLATE_DIR.rglob("*.html")):
            for number, line in enumerate(
                template.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if re.search(r'href="/(?!\s*")', line):
                    offenders.append(f"{template.name}:{number}")
        self.assertEqual(offenders, [])


class DatasetUrlTests(TestCase):
    """Primary-key detail routes and get_absolute_url (Section 1)."""

    def setUp(self):
        self.owner = User.objects.create_user("owner1", password="pw")
        self.dataset = Dataset.objects.create(
            name="Monthly Enrollment Export", owner=self.owner, source_team="Registrar"
        )

    def test_get_absolute_url_points_at_the_primary_key_detail_route(self):
        self.assertEqual(
            self.dataset.get_absolute_url(),
            reverse("data_quality:dataset-detail", kwargs={"pk": self.dataset.pk}),
        )
        self.assertEqual(self.dataset.get_absolute_url(), f"/datasets/{self.dataset.pk}/")

    def test_registry_links_each_dataset_to_its_own_detail_page(self):
        response = self.client.get(reverse("data_quality:dataset-list"))
        self.assertContains(response, f'href="{self.dataset.get_absolute_url()}"')

    def test_following_the_registry_link_loads_that_dataset(self):
        listing = self.client.get(reverse("data_quality:dataset-list")).content.decode()
        href = re.search(r'href="(/datasets/\d+/)"', listing).group(1)
        detail = self.client.get(href)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.context["dataset"], self.dataset)

    def test_detail_links_are_built_by_the_model_not_by_hand(self):
        # Section 1 asks for get_absolute_url() to be used in the templates
        # rather than rebuilding the URL from a primary key at each call site.
        for name in ("dataset_list.html", "dataset_overview.html"):
            with self.subTest(template=name):
                source = (TEMPLATE_DIR / name).read_text(encoding="utf-8")
                self.assertIn("get_absolute_url", source)
                self.assertNotIn("'data_quality:dataset-detail'", source)


class RunOutcomeAggregationTests(TestCase):
    """ORM aggregation behind the chart (Section 4)."""

    def setUp(self):
        owner = User.objects.create_user("owner1", password="pw")
        dataset = Dataset.objects.create(
            name="Monthly Enrollment Export", owner=owner, source_team="Registrar"
        )
        self.contract = Contract.objects.create(
            dataset=dataset, version_number=1, status=Contract.Status.ACTIVE
        )

    def _run(self, status):
        return ValidationRun.objects.create(
            contract=self.contract,
            file_name=f"{status.lower()}.csv",
            row_count=100,
            status=status,
        )

    def test_counts_group_runs_by_status(self):
        self._run(ValidationRun.Status.PASSED)
        self._run(ValidationRun.Status.FAILED)
        self._run(ValidationRun.Status.FAILED)
        totals = {value: total for value, _, total in charts.run_outcome_counts()}
        self.assertEqual(totals[ValidationRun.Status.PASSED], 1)
        self.assertEqual(totals[ValidationRun.Status.FAILED], 2)

    def test_a_status_with_no_runs_is_kept_at_zero(self):
        self._run(ValidationRun.Status.PASSED)
        totals = {value: total for value, _, total in charts.run_outcome_counts()}
        self.assertEqual(totals[ValidationRun.Status.ERROR], 0)
        self.assertIn(ValidationRun.Status.ERROR, totals)

    def test_rows_follow_the_model_declaration_order_not_the_database(self):
        # Created out of order on purpose: the chart's x-axis must stay stable.
        self._run(ValidationRun.Status.ERROR)
        self._run(ValidationRun.Status.PASSED)
        values = [value for value, _, _ in charts.run_outcome_counts()]
        self.assertEqual(values, [value for value, _ in ValidationRun.Status.choices])

    def test_every_status_choice_is_represented(self):
        rows = charts.run_outcome_counts()
        self.assertEqual(len(rows), len(ValidationRun.Status.choices))

    def test_labels_are_the_human_readable_choice_labels(self):
        labels = {value: label for value, label, _ in charts.run_outcome_counts()}
        self.assertEqual(labels[ValidationRun.Status.PASSED], "Passed")

    def test_empty_database_reports_zero_for_every_status(self):
        self.assertEqual([total for _, _, total in charts.run_outcome_counts()], [0, 0, 0])

    def test_aggregation_is_a_single_query(self):
        self._run(ValidationRun.Status.PASSED)
        with self.assertNumQueries(1):
            charts.run_outcome_counts()


class RunOutcomesChartTests(TestCase):
    """The PNG image endpoint (Section 4)."""

    url_name = "data_quality:run-outcomes-chart"

    def setUp(self):
        owner = User.objects.create_user("owner1", password="pw")
        dataset = Dataset.objects.create(
            name="Monthly Enrollment Export", owner=owner, source_team="Registrar"
        )
        self.contract = Contract.objects.create(
            dataset=dataset, version_number=1, status=Contract.Status.ACTIVE
        )
        ValidationRun.objects.create(
            contract=self.contract,
            file_name="enrollment.csv",
            row_count=100,
            status=ValidationRun.Status.FAILED,
        )

    def test_chart_route_reverses_and_resolves(self):
        url = reverse(self.url_name)
        self.assertEqual(url, "/quality/run-outcomes.png")
        self.assertEqual(resolve(url).view_name, self.url_name)

    def test_endpoint_returns_a_png_image(self):
        response = self.client.get(reverse(self.url_name))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")

    def test_response_body_is_a_real_png(self):
        body = self.client.get(reverse(self.url_name)).content
        self.assertTrue(body.startswith(PNG_MAGIC))
        self.assertGreater(len(body), 1000)

    def test_endpoint_still_returns_a_png_with_no_runs_recorded(self):
        ValidationRun.objects.all().delete()
        response = self.client.get(reverse(self.url_name))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(PNG_MAGIC))

    def test_repeated_requests_do_not_accumulate_figures(self):
        # Every request builds a figure. If one is held anywhere after the
        # response, memory grows with traffic, which is the failure this
        # endpoint is most likely to have and least likely to notice.
        import gc

        from matplotlib.figure import Figure

        def live_figures():
            gc.collect()
            return sum(1 for obj in gc.get_objects() if isinstance(obj, Figure))

        self.client.get(reverse(self.url_name))
        before = live_figures()
        for _ in range(4):
            self.client.get(reverse(self.url_name))
        self.assertLessEqual(live_figures(), before)

    def test_chart_does_not_touch_pyplots_global_figure_registry(self):
        # Drawing goes through Figure/FigureCanvasAgg on purpose: pyplot's
        # registry is process-wide, and Django answers requests on threads.
        import matplotlib.pyplot as plt

        plt.close("all")
        self.client.get(reverse(self.url_name))
        self.assertEqual(plt.get_fignums(), [])

    def test_chart_is_drawn_from_the_database_not_a_fixed_picture(self):
        first = self.client.get(reverse(self.url_name)).content
        for _ in range(4):
            ValidationRun.objects.create(
                contract=self.contract,
                file_name="another.csv",
                row_count=10,
                status=ValidationRun.Status.PASSED,
            )
        self.assertNotEqual(first, self.client.get(reverse(self.url_name)).content)


class QualityHistoryPageTests(TestCase):
    """The page that presents the chart (Section 4)."""

    url_name = "data_quality:quality-history"

    def test_page_renders(self):
        response = self.client.get(reverse(self.url_name))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "data_quality/quality_history.html")
        self.assertTemplateUsed(response, "data_quality/base.html")

    def test_page_embeds_the_chart_through_a_reversed_url(self):
        response = self.client.get(reverse(self.url_name))
        self.assertContains(
            response, f'src="{reverse("data_quality:run-outcomes-chart")}"'
        )

    def test_chart_image_carries_descriptive_alt_text(self):
        html = self.client.get(reverse(self.url_name)).content.decode()
        img = re.search(r"<img[^>]+>", html).group(0)
        alt = re.search(r'alt="([^"]*)"', img).group(1)
        self.assertGreater(len(alt), 20)
        self.assertNotIn("chart.png", alt.lower())

    def test_page_shows_the_same_totals_as_the_aggregation(self):
        response = self.client.get(reverse(self.url_name))
        self.assertEqual(response.context["outcomes"], charts.run_outcome_counts())

    def test_page_renders_with_no_runs_recorded(self):
        response = self.client.get(reverse(self.url_name))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["run_total"], 0)

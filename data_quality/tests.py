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
from .models import Contract, Dataset


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

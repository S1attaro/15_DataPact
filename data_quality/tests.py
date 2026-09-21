from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

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

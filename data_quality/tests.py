from django.contrib.auth.models import User
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

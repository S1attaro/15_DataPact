"""
A5.1 Part 3.1 - exactly one public API, everything else protected.
Author: Tejas Jaggi.

The rubric's wording is "out of all the APIs, one must be public while rest
as protected", so the interesting assertion is not "this endpoint is open"
but "only this endpoint is open". The sweep below enumerates every JSON
route and counts, which is what makes an accidentally-public endpoint added
later a test failure rather than a quiet hole.
"""

import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

# Every JSON-returning route in the project, with the arguments needed to
# reverse it. Add to this list when a JSON endpoint is added - the counting
# test below reads it.
JSON_ROUTES = [
    ("data_quality:api-run-outcomes", []),
    ("data_quality:api-run-volume", []),
    ("data_quality:dataset-api", []),
    ("data_quality:dataset-lookup", []),
    ("data_quality:vega-chart-spec", [1]),
    ("data_quality:vega-chart-spec", [2]),
]

PUBLIC_ROUTE = "data_quality:api-run-outcomes"


class PublicApiTests(TestCase):
    """The one endpoint A5.1 Part 3.1 asks us to leave open."""

    def setUp(self):
        self.url = reverse(PUBLIC_ROUTE)

    def test_anonymous_callers_get_data(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_it_returns_clean_json_only(self):
        body = self.client.get(self.url).content.decode()
        self.assertNotIn("<", body)
        rows = json.loads(body)
        self.assertIsInstance(rows, list)

    def test_it_is_backed_by_the_real_database(self):
        from data_quality.models import Contract, Dataset, ValidationRun

        owner = User.objects.create_user("owner1", password="pw")
        dataset = Dataset.objects.create(name="D", owner=owner, source_team="T")
        contract = Contract.objects.create(
            dataset=dataset, version_number=1, status=Contract.Status.ACTIVE
        )
        ValidationRun.objects.create(
            contract=contract, file_name="a.csv", row_count=1,
            status=ValidationRun.Status.PASSED,
        )
        rows = json.loads(self.client.get(self.url).content)
        self.assertEqual({r["outcome"]: r["runs"] for r in rows}["Passed"], 1)

    def test_it_allows_cross_origin_reads(self):
        # The Vega-Lite editor fetches data.url from vega.github.io, so
        # without this header the submitted spec fails with a CORS error in
        # exactly the place the grader will open it.
        response = self.client.get(self.url)
        self.assertEqual(response["Access-Control-Allow-Origin"], "*")

    def test_signing_in_does_not_change_the_public_response(self):
        anon = self.client.get(self.url).content
        self.client.force_login(User.objects.create_user("m", password="pw"))
        self.assertEqual(self.client.get(self.url).content, anon)


class ProtectedApiTests(TestCase):
    """Every other JSON endpoint refuses anonymous callers."""

    def setUp(self):
        self.user = User.objects.create_user("member", password="pw")
        self.protected = [
            (name, args) for name, args in JSON_ROUTES if name != PUBLIC_ROUTE
        ]

    def test_anonymous_callers_get_401_json_not_an_html_login_page(self):
        for name, args in self.protected:
            with self.subTest(route=name, args=args):
                response = self.client.get(reverse(name, args=args))
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response["Content-Type"], "application/json")
                # A 302 to the login page would hand a script 200 + HTML,
                # which reads as success and parses as nothing.
                self.assertNotIn("<", response.content.decode())

    def test_anonymous_callers_receive_no_data(self):
        for name, args in self.protected:
            with self.subTest(route=name, args=args):
                body = json.loads(self.client.get(reverse(name, args=args)).content)
                self.assertEqual(list(body.keys()), ["detail"])

    def test_signed_in_callers_get_their_data_back(self):
        self.client.force_login(self.user)
        for name, args in self.protected:
            with self.subTest(route=name, args=args):
                url = reverse(name, args=args)
                # dataset-lookup reaches an external API; it is covered for
                # access control only, with its own error path tested in
                # tests.py. Without ?q= it answers 400 before any network
                # call, which is enough to prove the auth gate let it past.
                expected = 400 if name == "data_quality:dataset-lookup" else 200
                self.assertEqual(self.client.get(url).status_code, expected)


class OnlyOnePublicApiTests(TestCase):
    """The counting test: one open endpoint, not two."""

    def test_exactly_one_json_route_answers_an_anonymous_request(self):
        open_routes = []
        for name, args in JSON_ROUTES:
            url = reverse(name, args=args)
            if self.client.get(url).status_code == 200:
                open_routes.append(url)
        self.assertEqual(open_routes, [reverse(PUBLIC_ROUTE)])

    def test_the_public_view_is_marked_as_such_in_code(self):
        # Belt and braces: the decorator records the decision, so "public"
        # is a property someone can grep for rather than the absence of a
        # decorator that was never added.
        #
        # Found by namespace rather than by position in the root URLconf.
        # Mounting allauth moves our include off the end of that list, and
        # indexing it would then quietly inspect allauth's routes, find no
        # marked view, and report that the public endpoint had vanished.
        from django.urls import get_resolver

        includes = [
            resolver
            for resolver in get_resolver().url_patterns
            if getattr(resolver, "namespace", None) == "data_quality"
        ]
        self.assertEqual(
            len(includes), 1, "expected exactly one data_quality include in the root URLconf"
        )

        marked = [
            pattern.name
            for pattern in includes[0].url_patterns
            if getattr(pattern.callback, "datapact_public", False)
        ]
        self.assertEqual(marked, ["api-run-outcomes"])


class ExportAccessTests(TestCase):
    """The CSV/JSON downloads are browser downloads, so they redirect."""

    def setUp(self):
        self.user = User.objects.create_user("member", password="pw")
        self.routes = [
            "data_quality:export-validation-runs-csv",
            "data_quality:export-validation-runs-json",
        ]

    def test_anonymous_downloads_are_refused(self):
        for name in self.routes:
            with self.subTest(route=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("data_quality:login"), response["Location"])

    def test_signed_in_downloads_still_work(self):
        self.client.force_login(self.user)
        for name in self.routes:
            with self.subTest(route=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertIn("attachment", response["Content-Disposition"])

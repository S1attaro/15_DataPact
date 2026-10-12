"""
A5.1 Part 1 - username/password authentication. Author: Tejas Jaggi.

A separate module rather than more lines on tests.py: four people appended
to the tail of that file during A4 and all four conflicted. Django's runner
discovers any test*.py, so this costs nothing and removes the conflict.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class SignupTests(TestCase):
    """Part 1.1 - the signup half of "custom login and signup pages"."""

    def setUp(self):
        self.url = reverse("data_quality:signup")

    def test_signup_page_renders_with_a_csrf_token(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/signup.html")
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_valid_signup_creates_the_user_and_logs_them_in(self):
        response = self.client.post(
            self.url,
            {
                "username": "newcomer",
                "password1": "Spindrift-Harbour-41",
                "password2": "Spindrift-Harbour-41",
            },
        )
        self.assertRedirects(response, reverse("data_quality:home"))
        self.assertTrue(User.objects.filter(username="newcomer").exists())
        # Signed in, not bounced to the login page having just typed it twice.
        self.assertEqual(int(self.client.session["_auth_user_id"]),
                         User.objects.get(username="newcomer").pk)

    def test_the_password_is_stored_hashed_not_in_plain_text(self):
        self.client.post(
            self.url,
            {
                "username": "newcomer",
                "password1": "Spindrift-Harbour-41",
                "password2": "Spindrift-Harbour-41",
            },
        )
        user = User.objects.get(username="newcomer")
        self.assertNotEqual(user.password, "Spindrift-Harbour-41")
        self.assertTrue(user.check_password("Spindrift-Harbour-41"))

    def test_mismatched_passwords_are_rejected(self):
        response = self.client.post(
            self.url,
            {
                "username": "newcomer",
                "password1": "Spindrift-Harbour-41",
                "password2": "Spindrift-Harbour-42",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newcomer").exists())
        self.assertTrue(response.context["form"].errors)

    def test_a_password_the_validators_reject_does_not_create_an_account(self):
        # "password" is in Django's common-password list; this proves
        # AUTH_PASSWORD_VALIDATORS is actually reached from this form.
        response = self.client.post(
            self.url,
            {"username": "newcomer", "password1": "password", "password2": "password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newcomer").exists())

    def test_a_duplicate_username_is_rejected_rather_than_raising(self):
        User.objects.create_user("taken", password="Spindrift-Harbour-41")
        response = self.client.post(
            self.url,
            {
                "username": "taken",
                "password1": "Different-Passphrase-77",
                "password2": "Different-Passphrase-77",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username="taken").count(), 1)

    def test_an_already_signed_in_visitor_is_sent_home(self):
        User.objects.create_user("member", password="Spindrift-Harbour-41")
        self.client.login(username="member", password="Spindrift-Harbour-41")
        self.assertRedirects(self.client.get(self.url), reverse("data_quality:home"))


class LoginLogoutTests(TestCase):
    """Part 1.1 and 1.2 - login, logout, and failing safely."""

    def setUp(self):
        self.url = reverse("data_quality:login")
        self.user = User.objects.create_user("member", password="Spindrift-Harbour-41")

    def test_login_page_renders_with_a_csrf_token(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/login.html")
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_correct_credentials_sign_the_user_in(self):
        response = self.client.post(
            self.url, {"username": "member", "password": "Spindrift-Harbour-41"}
        )
        self.assertRedirects(response, reverse("data_quality:home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_a_wrong_password_does_not_sign_anyone_in(self):
        response = self.client.post(
            self.url, {"username": "member", "password": "not-the-password"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(response.context["form"].errors)

    def test_an_unknown_username_fails_the_same_way_as_a_wrong_password(self):
        # Same status and no session either way: the page must not become an
        # oracle for which usernames exist.
        unknown = self.client.post(
            self.url, {"username": "ghost", "password": "Spindrift-Harbour-41"}
        )
        wrong = self.client.post(
            self.url, {"username": "member", "password": "nope"}
        )
        self.assertEqual(unknown.status_code, wrong.status_code)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_ends_the_session(self):
        self.client.login(username="member", password="Spindrift-Harbour-41")
        self.assertIn("_auth_user_id", self.client.session)
        response = self.client.post(reverse("data_quality:logout"))
        self.assertRedirects(response, reverse("data_quality:home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_rejects_get(self):
        # A GET logout can be fired by any <img> on another site, which would
        # sign our users out without them asking. Django made it POST-only in
        # 4.1; this guards against someone "fixing" the nav with a plain link.
        self.client.login(username="member", password="Spindrift-Harbour-41")
        self.assertEqual(self.client.get(reverse("data_quality:logout")).status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_honours_the_next_parameter(self):
        target = reverse("data_quality:reports")
        response = self.client.post(
            f"{self.url}?next={target}",
            {"username": "member", "password": "Spindrift-Harbour-41"},
        )
        self.assertRedirects(response, target)

    def test_login_refuses_to_redirect_to_another_site(self):
        # Django's own safety check. Asserted here because this is the thing
        # that turns a login page into an open redirect if it is ever
        # replaced with a hand-rolled view.
        response = self.client.post(
            f"{self.url}?next=https://example.com/phish",
            {"username": "member", "password": "Spindrift-Harbour-41"},
        )
        self.assertRedirects(response, reverse("data_quality:home"))


class ProtectedPageTests(TestCase):
    """Part 1.4 - private sections of the site require a login."""

    PROTECTED = [
        "data_quality:dataset-list",
        "data_quality:dataset-cbv-base",
        "data_quality:dataset-manual",
        "data_quality:dataset-render",
        "data_quality:contract-search",
        "data_quality:dataset-manage",
        "data_quality:quality-history",
        "data_quality:run-outcomes-chart",
        "data_quality:charts",
        "data_quality:reports",
        "data_quality:export-validation-runs-csv",
        "data_quality:export-validation-runs-json",
    ]

    def setUp(self):
        self.user = User.objects.create_user("member", password="Spindrift-Harbour-41")

    def test_anonymous_visitors_are_redirected_to_the_login_page(self):
        for name in self.PROTECTED:
            with self.subTest(route=name):
                url = reverse(name)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("data_quality:login"), response["Location"])
                # and the page they wanted is remembered
                self.assertIn(url, response["Location"])

    def test_signed_in_users_get_the_pages(self):
        self.client.force_login(self.user)
        for name in self.PROTECTED:
            with self.subTest(route=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_the_home_page_stays_public(self):
        # Deliberate: there has to be a landing page that an anonymous
        # visitor can reach in order to find the login and signup links.
        self.assertEqual(self.client.get(reverse("data_quality:home")).status_code, 200)

    def test_auth_pages_are_reachable_without_an_account(self):
        for name in ("data_quality:login", "data_quality:signup"):
            with self.subTest(route=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)


class AuthSettingsTests(TestCase):
    """Part 1.3 - the redirect settings are configured, not left at defaults."""

    def test_login_and_redirect_urls_point_at_real_routes(self):
        from django.conf import settings

        self.assertEqual(settings.LOGIN_URL, "data_quality:login")
        self.assertEqual(settings.LOGIN_REDIRECT_URL, "data_quality:home")
        self.assertEqual(settings.LOGOUT_REDIRECT_URL, "data_quality:home")
        # Names, not paths - so these fail loudly if a route is renamed.
        for name in (settings.LOGIN_URL, settings.LOGIN_REDIRECT_URL,
                     settings.LOGOUT_REDIRECT_URL):
            with self.subTest(setting=name):
                reverse(name)

"""
UX Stage 3J - the sign-in and account pages in the product redesign.

Presentation only. What must not change, pinned here or in tests_auth.py / tests_oauth_security.py:
the Google button (its partial byte for byte, and the {% block oauth %} that includes it on both pages),
CSRF and the `next` field, the views, forms, validators, OAuth settings and the three redirect settings
(LOGIN_URL, LOGIN_REDIRECT_URL, LOGOUT_REDIRECT_URL, A5.1 Part 1.3).

What changes, checked here: Log in and Sign up in the Answer Key form style (labels without colons, one
error summary, a wrong password reported once, one short guidance line per sign-up field tied to its input),
and every django-allauth page rendered inside DataPact's own shell instead of allauth's bare layout.
"""

import hashlib
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from data_quality.tests_oauth_security import CONNECT_PAGE, TEST_PROVIDERS, complete_google_login

TEMPLATES = Path(settings.BASE_DIR) / "data_quality" / "templates"
CSS = Path(settings.BASE_DIR) / "data_quality" / "static" / "data_quality" / "css" / "datapact.css"
GOOGLE_PARTIAL_SHA256 = "53aee4be32bce8a77802a477d206fffbc882f94e506cc9f7ef75fbde57619c9e"
OAUTH_BLOCK = ('{% block oauth %}\n'
               '                <div class="authsplit"><span>or</span></div>\n'
               '                {% include "data_quality/includes/_google_button.html" %}\n'
               '            {% endblock %}')
WRONG_PASSWORD = "Please enter a correct username and password"


def main_of(html):
    return html[html.index("<main"):html.index("</main>")]


# --- What must not change -----------------------------------------------------------------------

class GoogleSignInIsUntouchedTests(TestCase):
    def test_the_google_button_partial_is_byte_for_byte_unchanged(self):
        source = (TEMPLATES / "data_quality" / "includes" / "_google_button.html").read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), GOOGLE_PARTIAL_SHA256)

    def test_both_pages_still_include_it_in_the_oauth_block(self):
        for name in ("login.html", "signup.html"):
            text = (TEMPLATES / "registration" / name).read_text(encoding="utf-8").replace("\r\n", "\n")
            self.assertEqual(text.count(OAUTH_BLOCK), 1, name)

    @override_settings(SOCIALACCOUNT_PROVIDERS=TEST_PROVIDERS)
    def test_continue_with_google_shows_on_both_pages_when_configured(self):
        for route in ("data_quality:login", "data_quality:signup"):
            html = self.client.get(reverse(route)).content.decode()
            self.assertIn("Continue with Google", html, route)
            self.assertRegex(html, r'<form method="post" action="/accounts/google/login/\?process=login[^"]*">', route)

    def test_without_credentials_the_existing_note_shows(self):
        for route in ("data_quality:login", "data_quality:signup"):
            self.assertContains(self.client.get(reverse(route)), "Google sign-in is not configured.")

    def test_the_redirect_settings_are_unchanged(self):
        self.assertEqual(settings.LOGIN_URL, "data_quality:login")
        self.assertEqual(settings.LOGIN_REDIRECT_URL, "data_quality:home")
        self.assertEqual(settings.LOGOUT_REDIRECT_URL, "data_quality:home")


# --- Log in and Sign up -------------------------------------------------------------------------

class LoginPageTests(TestCase):
    def setUp(self):
        User.objects.create_user("member", password="Spindrift-Harbour-41")

    def test_frame_labels_and_fields(self):
        html = main_of(self.client.get(reverse("data_quality:login"), {"next": "/reports/"}).content.decode())
        self.assertIn('data-surface="auth"', self.client.get(reverse("data_quality:login")).content.decode())
        self.assertIn('<label for="id_username">Username</label>', html)
        self.assertIn('<label for="id_password">Password</label>', html)
        self.assertNotIn("Username:", html)
        self.assertIn('autocomplete="username"', html)
        self.assertIn('autocomplete="current-password"', html)
        self.assertIn('<input type="hidden" name="next" value="/reports/">', html)
        self.assertIn('<button type="submit" class="btn btn--primary">Log in</button>', html)

    def test_a_wrong_password_is_reported_once_in_one_summary(self):
        response = self.client.post(reverse("data_quality:login"), {"username": "member", "password": "nope"})
        html = main_of(response.content.decode())
        self.assertEqual(html.count(WRONG_PASSWORD), 1)
        self.assertEqual(html.count('role="alert"'), 1)
        self.assertIn('<div class="form-errors" id="auth-errors" role="alert" tabindex="-1">', html)
        self.assertIn("You were not signed in.", html)
        # Focus moves to the summary after the page loads (the Manage page's pattern).
        self.assertIn('document.getElementById("auth-errors")', response.content.decode())

    def test_an_empty_field_is_named_in_the_summary_and_under_the_field(self):
        html = main_of(self.client.post(reverse("data_quality:login"), {"username": "", "password": ""}).content.decode())
        self.assertIn('<a href="#id_username">Username: This field is required.</a>', html)
        self.assertIn('<a href="#id_password">Password: This field is required.</a>', html)
        self.assertIn('aria-invalid="true"', html)

    def test_no_summary_on_a_fresh_page(self):
        html = main_of(self.client.get(reverse("data_quality:login")).content.decode())
        self.assertNotIn('role="alert"', html)
        self.assertNotIn('id="auth-errors"', html)


class SignupPageTests(TestCase):
    def post(self, **data):
        values = {"username": "newcomer", "password1": "Spindrift-Harbour-41", "password2": "Spindrift-Harbour-41"}
        values.update(data)
        return self.client.post(reverse("data_quality:signup"), values)

    def test_frame_labels_and_one_guidance_line_per_field(self):
        html = main_of(self.client.get(reverse("data_quality:signup")).content.decode())
        for field, label in (("username", "Username"), ("password1", "Password"), ("password2", "Password confirmation")):
            self.assertIn(f'<label for="id_{field}">{label}</label>', html)
            # Each field's guidance keeps the id Django's widget already points aria-describedby at.
            self.assertEqual(len(re.findall(rf'<p class="helptext" id="id_{field}_helptext">', html)), 1, field)
            self.assertRegex(html, rf'<input[^>]*aria-describedby="id_{field}_helptext"[^>]*id="id_{field}"|'
                                   rf'<input[^>]*id="id_{field}"[^>]*aria-describedby="id_{field}_helptext"')
        self.assertIn("At least 8 characters, not a common password, not only numbers", html)
        # Django's default help (a bulleted list of the four rules) is not printed as well.
        self.assertNotIn("Your password can’t be too similar to your other personal information.", html)
        self.assertNotIn("Username:", html)
        self.assertIn('autocomplete="new-password"', html)

    def test_validator_messages_still_reach_the_page(self):
        html = main_of(self.post(password1="password", password2="password").content.decode())
        self.assertIn("This password is too common.", html)
        self.assertIn('<div class="form-errors" id="auth-errors" role="alert" tabindex="-1">', html)
        self.assertIn("Your account was not created.", html)
        self.assertFalse(User.objects.filter(username="newcomer").exists())

    def test_mismatched_passwords_are_named(self):
        html = main_of(self.post(password2="Spindrift-Harbour-42").content.decode())
        self.assertIn("The two password fields didn’t match.", html)
        self.assertIn('<a href="#id_password2">Password confirmation: The two password fields didn’t match.</a>', html)

    def test_a_good_signup_still_works(self):
        response = self.post()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="newcomer").exists())


# --- django-allauth pages -----------------------------------------------------------------------

class AllauthLayoutTests(TestCase):
    SIGNED_OUT = ("/accounts/password/reset/", "/accounts/3rdparty/login/cancelled/",
                  "/accounts/3rdparty/login/error/", "/accounts/inactive/")
    SIGNED_IN = ("/accounts/email/", "/accounts/password/change/", "/accounts/3rdparty/")

    def check_in_shell(self, response, path):
        html = response.content.decode()
        self.assertTemplateUsed(response, "data_quality/base.html")
        self.assertIn('data-surface="account"', html, path)
        self.assertIn("datapact.css", html, path)
        self.assertNotIn("<strong>Menu:</strong>", html, path)
        self.assertEqual(len(re.findall(r'<h1 class="page__title">', html)), 1, path)
        self.assertEqual(html.count("<h1"), 1, path)
        self.assertRegex(html, r"<title>\s*[^<]*\S\s*- DataPact</title>", path)

    def test_signed_out_pages_use_the_datapact_shell(self):
        for path in self.SIGNED_OUT:
            with self.subTest(path=path):
                self.check_in_shell(self.client.get(path), path)

    def test_signed_in_pages_use_the_shell_and_an_account_nav(self):
        self.client.force_login(User.objects.create_user("member", password="Spindrift-Harbour-41"))
        for path in self.SIGNED_IN:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.check_in_shell(response, path)
                html = main_of(response.content.decode())
                nav = html[html.index('<nav class="account-nav" aria-label="Account settings">'):]
                nav = nav[:nav.index("</nav>")]
                self.assertEqual(re.findall(r'<a href="([^"]+)"', nav),
                                 ["/accounts/email/", "/accounts/password/change/", "/accounts/3rdparty/"])
                self.assertEqual(nav.count('aria-current="page"'), 1)
                self.assertIn(f'<a href="{path}" aria-current="page">', nav)
                # allauth's own "Sign Out" link is a GET to a POST-only logout; it is not offered.
                self.assertNotIn('<a href="/accounts/logout/"', html)

    def test_buttons_take_the_site_button_styles(self):
        self.client.force_login(User.objects.create_user("member", password="Spindrift-Harbour-41"))
        html = main_of(self.client.get("/accounts/password/change/").content.decode())
        self.assertRegex(html, r'<button[^>]*class="btn btn--primary"[^>]*>\s*Change Password\s*</button>')
        html = main_of(self.client.get("/accounts/password/reset/").content.decode())
        self.assertRegex(html, r'<button[^>]*class="btn btn--primary"[^>]*>\s*Reset My Password\s*</button>')

    def test_allauth_fields_are_written_out_with_their_help_tied_to_the_input(self):
        # as_p broke the password rules out of their help text (a <ul> inside a <p>), leaving
        # aria-describedby pointing at an empty span. Now the help is a <div> with that id.
        self.client.force_login(User.objects.create_user("member", password="Spindrift-Harbour-41"))
        html = main_of(self.client.get("/accounts/password/change/").content.decode())
        self.assertIn('<label for="id_oldpassword">Current Password</label>', html)
        self.assertNotIn("Current Password:", html)
        help_text = re.search(r'<div class="helptext" id="id_password1_helptext">(.*?)</div>', html, re.S)
        self.assertIsNotNone(help_text)
        self.assertIn("Your password must contain at least 8 characters.", help_text.group(1))
        self.assertRegex(html, r'<input[^>]*aria-describedby="id_password1_helptext"')
        self.assertIn('name="csrfmiddlewaretoken"', html)

    def test_allauth_field_errors_still_show(self):
        self.client.force_login(User.objects.create_user("member", password="Spindrift-Harbour-41"))
        html = main_of(self.client.post("/accounts/password/change/", {
            "oldpassword": "wrong", "password1": "Spindrift-Harbour-99", "password2": "Spindrift-Harbour-99"}).content.decode())
        self.assertIn('class="errorlist"', html)
        self.assertIn('aria-invalid="true"', html)

    def test_the_email_page_keeps_its_scripts(self):
        self.client.force_login(User.objects.create_user("member", password="Spindrift-Harbour-41"))
        html = self.client.get("/accounts/email/").content.decode()
        head = html[:html.index("</head>")]
        self.assertIn("account/js/account.js", head)
        self.assertIn("account/js/onload.js", head)
        self.assertIn('data-allauth-onload="allauth.account.forms.manageEmailForm"', head)

    @override_settings(SOCIALACCOUNT_PROVIDERS=TEST_PROVIDERS)
    def test_the_google_connect_page_uses_the_shell(self):
        # The page a colliding Google address is sent to (tests_oauth_security), rendered for real.
        User.objects.create_superuser("tejasj2", "tejasj2@illinois.edu", "Spindrift-Harbour-41")
        request, response = complete_google_login("tejasj2@illinois.edu")
        self.assertEqual(response.url, CONNECT_PAGE)
        request.session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = request.session.session_key
        page = self.client.get(CONNECT_PAGE)
        self.assertEqual(page.status_code, 200)
        self.check_in_shell(page, CONNECT_PAGE)
        self.assertFalse(page.wsgi_request.user.is_authenticated)


# --- Stylesheet ----------------------------------------------------------------------------------

class AuthStylesheetTests(TestCase):
    def section(self):
        css = CSS.read_text(encoding="utf-8")
        return css[css.index("/* ---- 27. sign-in and account pages"):]

    def test_both_surfaces_and_a_phone_layout_without_hiding(self):
        css = self.section()
        self.assertIn('.page[data-surface="auth"]', css)
        self.assertIn('.page[data-surface="account"]', css)
        if "@media (max-width: 40em)" in css:
            self.assertNotRegex(css[css.index("@media (max-width: 40em)"):], r"display:\s*none")

    def test_nothing_moves(self):
        css = re.sub(r"/\*.*?\*/", "", self.section(), flags=re.S)
        for banned in ("animation", "transition", "box-shadow", "gradient", "@keyframes"):
            self.assertNotIn(banned, css)
        self.assertNotRegex(css, r"(?<!text-)transform")

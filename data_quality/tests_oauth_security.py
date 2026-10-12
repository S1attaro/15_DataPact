"""
A5.1 integration - Google sign-in must not inherit an existing account.
Author: Tejas Jaggi.

Why this module exists
----------------------
db.sqlite3 is tracked in Git for A4, and the accounts seeded into it are
superusers whose email addresses are real, guessable university addresses
(netid@illinois.edu). Part 2 originally shipped with

    SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
    SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

which signs a Google user into whichever local account already holds that
email. Those two facts together mean that on the deployed site, whoever
controls one of those addresses could press "Continue with Google" and be
handed a superuser account with /admin/ attached, without ever knowing a
password. Google would report the address as genuinely verified, so no
provider-side check prevents it - the flaw is that the stored address is
treated as proof of identity.

Both settings are therefore off, and these tests pin that down. They assert
observed allauth behaviour (checked against allauth 65.14.3), not what the
setting names suggest should happen: turning a flag off is only worth
anything if the flow actually changes, so the assertions below describe the
flow.

The tests deliberately cover the safe case too. A security fix that also
breaks Google sign-in is not a fix, so test_a_brand_new_google_user_can_still
_sign_in proves Part 2 still works.
"""

from django.contrib.auth.models import AnonymousUser, User
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings

from allauth.account.models import EmailAddress
from allauth.core import context as allauth_context
from allauth.socialaccount.adapter import get_adapter as get_social_adapter
from allauth.socialaccount.helpers import complete_social_login
from allauth.socialaccount.models import SocialAccount, SocialLogin

# A stand-in Google app, so these tests do not depend on real credentials
# being present in .env. The values are obvious placeholders on purpose.
TEST_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "APP": {
            "client_id": "test-client-id.apps.googleusercontent.com",
            "secret": "test-secret-not-a-real-credential",
            "key": "",
        },
    }
}

# The signup page allauth sends a colliding login to. Landing here is the
# safe outcome: it asks who you are instead of assuming.
CONNECT_PAGE = "/accounts/3rdparty/signup/"


def complete_google_login(email, verified=True, uid="1234567890"):
    """
    Run allauth's post-callback step for a Google profile with this email.

    The real callback view needs a live token exchange with Google, so this
    hands allauth an already-fetched profile instead, which is the same entry
    point the provider code reaches once the token round-trip has happened.
    Returns (request, response) so a caller can inspect who ended up signed in.
    """
    request = RequestFactory().get("/accounts/google/login/callback/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request.user = AnonymousUser()
    with allauth_context.request_context(request):
        sociallogin = SocialLogin(
            user=User(email=email),
            account=SocialAccount(
                provider="google", uid=uid, extra_data={"email": email}
            ),
            email_addresses=[
                EmailAddress(email=email, verified=verified, primary=True)
            ],
            provider=get_social_adapter().get_provider(request, "google"),
        )
        sociallogin.state = {"process": "login"}
        response = complete_social_login(request, sociallogin)
    return request, response


class EmailAuthenticationIsOffTests(TestCase):
    """The settings themselves, so a later edit has to be deliberate."""

    def test_social_email_authentication_is_disabled(self):
        from django.conf import settings

        self.assertFalse(settings.SOCIALACCOUNT_EMAIL_AUTHENTICATION)
        self.assertFalse(settings.SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT)

    def test_local_email_verification_stays_off_while_there_is_no_mail_backend(self):
        # Not an oversight. There is no SMTP configuration in this project, so
        # requiring confirmation would leave every new account stuck waiting
        # for a message that is never sent. The protection above does not
        # depend on verification being on.
        from django.conf import settings

        self.assertEqual(settings.ACCOUNT_EMAIL_VERIFICATION, "none")


@override_settings(SOCIALACCOUNT_PROVIDERS=TEST_PROVIDERS)
class GoogleCannotTakeOverAnExistingAccountTests(TestCase):
    """The privilege-escalation path, closed."""

    def setUp(self):
        # Mirrors what seed_demo.py puts into the tracked database: a
        # superuser whose address is a predictable university address.
        self.privileged = User.objects.create_superuser(
            "tejasj2", "tejasj2@illinois.edu", "Spindrift-Harbour-41"
        )

    def test_a_matching_google_email_does_not_sign_in_as_the_superuser(self):
        request, response = complete_google_login("tejasj2@illinois.edu")

        self.assertFalse(request.user.is_authenticated)
        self.assertNotEqual(getattr(request.user, "pk", None), self.privileged.pk)

    def test_a_matching_google_email_is_sent_to_the_connect_page_instead(self):
        # The flow does not dead-end; it just stops short of handing over the
        # account. Someone who really owns that login can still link Google
        # from inside it.
        _, response = complete_google_login("tejasj2@illinois.edu")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, CONNECT_PAGE)

    def test_no_social_account_is_attached_to_the_privileged_user(self):
        complete_google_login("tejasj2@illinois.edu")

        self.assertFalse(SocialAccount.objects.filter(user=self.privileged).exists())

    def test_no_shadow_account_is_created_for_the_colliding_address(self):
        # Neither outcome is acceptable: signing into the superuser, or
        # quietly minting a second account that owns the same address.
        complete_google_login("tejasj2@illinois.edu")

        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().pk, self.privileged.pk)

    def test_an_unverified_google_email_is_refused_the_same_way(self):
        # Belt and braces. allauth would not trust an unverified address even
        # with email authentication on, so this must not regress if someone
        # turns the setting back on without reading why it is off.
        request, response = complete_google_login(
            "tejasj2@illinois.edu", verified=False
        )

        self.assertFalse(request.user.is_authenticated)
        self.assertEqual(response.url, CONNECT_PAGE)
        self.assertFalse(SocialAccount.objects.filter(user=self.privileged).exists())


@override_settings(SOCIALACCOUNT_PROVIDERS=TEST_PROVIDERS)
class GoogleSignInStillWorksTests(TestCase):
    """Part 2 is not collateral damage of the fix above."""

    def setUp(self):
        self.privileged = User.objects.create_superuser(
            "tejasj2", "tejasj2@illinois.edu", "Spindrift-Harbour-41"
        )

    def test_a_brand_new_google_user_can_still_sign_in(self):
        request, response = complete_google_login(
            "stranger@gmail.com", uid="999000111"
        )

        self.assertTrue(request.user.is_authenticated)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.count(), 2)
        self.assertTrue(
            SocialAccount.objects.filter(
                user=request.user, provider="google"
            ).exists()
        )

    def test_a_new_google_user_gets_no_privileges(self):
        # The point of the whole module: arriving through Google must not be
        # a way to acquire someone else's standing.
        request, _ = complete_google_login("stranger@gmail.com", uid="999000111")

        self.assertFalse(request.user.is_staff)
        self.assertFalse(request.user.is_superuser)
        self.assertNotEqual(request.user.pk, self.privileged.pk)

    def test_password_login_is_untouched_by_any_of_this(self):
        # The seeded accounts are still reachable the documented way, which
        # is what the course demo material relies on.
        self.assertTrue(
            self.client.login(
                username="tejasj2", password="Spindrift-Harbour-41"
            )
        )

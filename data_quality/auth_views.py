"""
Username/password authentication for A5.1 Part 1 - Tejas Jaggi.

Login and logout are Django's own class-based views, pointed at our
templates. They are not reimplemented here: Django's versions already do the
session cycling, the "next" handling and the redirect safety check that a
hand-written view usually gets wrong, and rewriting them would mean
re-earning that for nothing.

Signup is ours, because Django ships a form but no view for it.

This module is separate from views.py so that the authentication logic and
the A1-A4 views are not the same merge conflict, and separate from the
templates so that Ashok can restyle the pages (Part 1.5 / Part 2.4) without
touching any of this.
"""

from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy


class DataPactLoginView(LoginView):
    """
    Login page.

    redirect_authenticated_user sends an already-logged-in visitor to the
    home page instead of showing them a login form they do not need.

    The form is Django's AuthenticationForm, so a wrong password re-renders
    the page with an error rather than saying anything about which half of
    the pair was wrong, and the session key is cycled on success.
    """

    template_name = "registration/login.html"
    authentication_form = AuthenticationForm
    redirect_authenticated_user = True


class DataPactLogoutView(LogoutView):
    """
    Logout.

    POST-only, which is Django's default from 4.1 and the reason it is: a
    GET logout can be triggered by any image tag pointing at the URL, so a
    page on another site could sign our users out. The nav posts a small
    CSRF-protected form instead.
    """

    next_page = reverse_lazy("data_quality:home")


def signup(request):
    """
    Create an account and sign the new user in.

    UserCreationForm enforces AUTH_PASSWORD_VALIDATORS, so the length,
    common-password and numeric-only rules configured in settings apply
    here, and it rejects a duplicate username rather than raising
    IntegrityError.

    login() on success means a new account does not land on the login page
    having just typed the password twice.

    The backend is named explicitly because form.save() returns a user that
    was never run through authenticate(), so it carries no .backend. With a
    single backend Django guesses correctly, but once a second one is
    configured - which Google sign-in does - it refuses to guess and raises
    ValueError instead. Naming it here keeps signup working either way.
    """
    if request.user.is_authenticated:
        return redirect("data_quality:home")

    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("data_quality:home")
    else:
        form = UserCreationForm()

    return render(request, "registration/signup.html", {"form": form})

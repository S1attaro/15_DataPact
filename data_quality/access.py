"""
Access control for A5.1 - Tejas Jaggi.

A browser page and a JSON API should fail differently when nobody is logged
in. Django's own login_required answers both with a 302 to the login page,
which is right for a page and wrong for an API: a script calling
/api/run-volume/ with no session gets 200 and a chunk of HTML, which looks
like success and parses like garbage. So APIs get their own decorator that
answers 401 in the same JSON shape the endpoint would have used.

The other decorator marks the single endpoint A5.1 asks us to leave open.
Marking it is the point: "public" is then a deliberate, greppable property of
one view rather than the absence of a decorator on sixteen.
"""

from functools import wraps

from django.http import JsonResponse

# The Vega-Lite editor at vega.github.io fetches data.url straight from the
# browser, so the public endpoint is read cross-origin and needs this header
# or the chart fails with a CORS error. Scoped to the one public, read-only,
# aggregate endpoint rather than installed site-wide, so nothing else gains
# cross-origin access and no new dependency is needed.
PUBLIC_API_CORS_ORIGIN = "*"


def api_login_required(view):
    """
    Require a logged-in user, answering 401 JSON instead of redirecting.

    Used on every JSON endpoint except the one public one, so an
    unauthenticated caller gets a machine-readable refusal and no data.
    """

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"detail": "Authentication required."},
                status=401,
            )
        return view(request, *args, **kwargs)

    wrapper.datapact_public = False
    return wrapper


def public_api(view):
    """
    Mark a view as the deliberately public API and allow cross-origin reads.

    A5.1 Part 3 requires exactly one endpoint to stay open so other people -
    and the Vega-Lite editor - can read it without an account. The attribute
    is what the access-control test asserts against, so adding a second
    public endpoint by accident fails the suite rather than shipping.
    """

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        response = view(request, *args, **kwargs)
        response["Access-Control-Allow-Origin"] = PUBLIC_API_CORS_ORIGIN
        return response

    wrapper.datapact_public = True
    return wrapper

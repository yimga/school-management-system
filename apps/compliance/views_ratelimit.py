"""
Custom rate limit error handler.
"""

from django.http import HttpResponse, JsonResponse
from django.template import loader


def _wants_machine_response(request) -> bool:
    """True when the caller is a programmatic client (fetch/XHR/API), not a
    top-level browser navigation.

    Returning the full branded HTML error page to a ``fetch()``/XHR caller is
    actively harmful: the client throws the body away, but the server still
    rendered an entire dashboard shell (all context processors + the analytics
    viz mount) — hundreds of KB and a heavy render — for a request that only
    needed a one-line "slow down". On shared-NAT networks (a whole school behind
    one public IP collectively blowing a per-IP budget) this turns a benign
    throttle into a worker-starving render storm.

    We treat a request as machine-facing when ANY of these hold:
      * the path is an API path,
      * the client explicitly Accepts JSON,
      * ``X-Requested-With: XMLHttpRequest`` (jQuery / classic XHR), or
      * Fetch Metadata says this is not a document navigation
        (``Sec-Fetch-Dest`` present and not ``document``). Browsers set
        ``Sec-Fetch-Dest: empty`` on ``fetch()``/XHR and ``document`` on a
        real navigation, so this catches header-less ``fetch()`` callers.
    """
    path = request.path or ""
    if path.startswith("/api/") or path.startswith("/compliance/api/"):
        return True

    accept = request.META.get("HTTP_ACCEPT", "")
    if "application/json" in accept:
        return True

    if request.META.get("HTTP_X_REQUESTED_WITH", "").lower() == "xmlhttprequest":
        return True

    fetch_dest = request.META.get("HTTP_SEC_FETCH_DEST", "").lower()
    if fetch_dest and fetch_dest != "document":
        return True

    return False


def ratelimit_error(request, exception=None):
    """
    Custom handler for rate limit exceeded errors.
    Returns JSON for API / fetch / XHR requests, HTML for top-level navigations.
    """
    if _wants_machine_response(request):
        return JsonResponse(
            {
                "error": "Rate limit exceeded",
                "message": "Too many requests. Please try again later.",
                "retry_after": "60s",
            },
            status=429,
        )

    # HTML response for genuine browser navigations only.
    template = loader.get_template("errors/429.html")
    context = {
        "message": "Too many requests. Please try again in a moment.",
    }
    return HttpResponse(template.render(context, request), status=429)

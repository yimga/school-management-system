"""
Custom rate limit error handler.
"""

from django.http import HttpResponse, JsonResponse
from django.template import loader


def ratelimit_error(request, exception=None):
    """
    Custom handler for rate limit exceeded errors.
    Returns JSON for API requests, HTML for web requests.
    """
    is_api_request = (
        request.path.startswith("/api/")
        or request.path.startswith("/compliance/api/")
        or request.META.get("HTTP_ACCEPT", "").startswith("application/json")
    )

    if is_api_request:
        return JsonResponse(
            {
                "error": "Rate limit exceeded",
                "message": "Too many requests. Please try again later.",
                "retry_after": "60s",
            },
            status=429,
        )

    # HTML response for web requests
    template = loader.get_template("errors/429.html")
    context = {
        "message": "Too many requests. Please try again in a moment.",
    }
    return HttpResponse(template.render(context, request), status=429)

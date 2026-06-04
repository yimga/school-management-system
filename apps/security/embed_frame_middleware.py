"""
Allow same-origin Studio / operator iframe embeds when ``?embed=1``.

Global ``X_FRAME_OPTIONS`` defaults to DENY; without this override, Launch Studio
and Automation Studio iframes show "refused to connect" in the browser.
"""

from __future__ import annotations

from django.conf import settings


def _request_wants_embed(request) -> bool:
    if not request:
        return False
    raw = (request.GET.get("embed") or "").strip().lower()
    return raw in ("1", "true", "yes")


class EmbedSameOriginFrameMiddleware:
    """After XFrameOptionsMiddleware, relax framing for explicit embed requests."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not _request_wants_embed(request):
            return response
        # Honor views that explicitly exempt framing (previews, etc.).
        if getattr(response, "xframe_options_exempt", False):
            return response
        response["X-Frame-Options"] = "SAMEORIGIN"
        # CSP frame-ancestors is set in ContentSecurityPolicyMiddleware; ensure
        # embed documents can be nested on the same host when CSP is enforced.
        csp = response.get("Content-Security-Policy") or ""
        if csp and "frame-ancestors" in csp and "'self'" not in csp:
            extra = getattr(settings, "CSP_EXTRA_FRAME_ANCESTORS", ()) or ()
            if "'self'" not in extra:
                response["Content-Security-Policy"] = csp.replace(
                    "frame-ancestors",
                    "frame-ancestors 'self'",
                    1,
                )
        return response

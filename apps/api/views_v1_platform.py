"""Developer platform discovery: API key context and scope introspection."""

from __future__ import annotations

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_GET


@method_decorator(require_GET, name="dispatch")
class IntegrationContextView(View):
    """
    Returns auth mode and effective scopes for the current request.
    Used by integrations and tests; safe read-only output.
    """

    def get(self, request):
        school = getattr(request, "school", None)
        key = getattr(request, "app_api_key", None)
        oauth_pair = getattr(request, "oauth_access_pair", None)
        inst = getattr(request, "app_installation", None)
        scopes = getattr(request, "app_scope", None)
        app_authenticated = key is not None or oauth_pair is not None
        return JsonResponse(
            {
                "school_id": str(school.id) if school else None,
                "app_auth": app_authenticated,
                "app_auth_mode": (
                    "oauth_access_token"
                    if oauth_pair is not None
                    else ("api_key" if key is not None else None)
                ),
                "marketplace_installation_id": str(inst.id) if inst else None,
                "app_scope": list(scopes) if scopes is not None else None,
            }
        )


@method_decorator(require_GET, name="dispatch")
class IntegrationScopedPingView(View):
    """Example enforcement: requires ``ping:read`` (API key or OAuth access token)."""

    def get(self, request):
        if getattr(request, "app_installation", None) is None:
            return JsonResponse(
                {"error": "App installation context required (API key or OAuth)"},
                status=401,
            )
        scopes = getattr(request, "app_scope", None) or frozenset()
        if "ping:read" not in scopes:
            return JsonResponse({"error": "Insufficient scope (need ping:read)"}, status=403)
        return JsonResponse({"ok": True, "scope": "ping:read"})

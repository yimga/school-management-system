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
        inst = getattr(request, "app_installation", None)
        scopes = getattr(request, "app_scope", None)
        return JsonResponse(
            {
                "school_id": str(school.id) if school else None,
                "app_auth": key is not None,
                "marketplace_installation_id": str(inst.id) if inst else None,
                "app_scope": list(scopes) if scopes is not None else None,
            }
        )


@method_decorator(require_GET, name="dispatch")
class IntegrationScopedPingView(View):
    """Example enforcement: requires ``ping:read`` on the API key principal."""

    def get(self, request):
        if getattr(request, "app_api_key", None) is None:
            return JsonResponse({"error": "App API key required"}, status=401)
        scopes = getattr(request, "app_scope", None) or frozenset()
        if "ping:read" not in scopes:
            return JsonResponse({"error": "Insufficient scope (need ping:read)"}, status=403)
        return JsonResponse({"ok": True, "scope": "ping:read"})

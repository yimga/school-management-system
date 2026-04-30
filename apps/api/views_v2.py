"""Public API v2 — contract-versioned JSON envelope (developer platform)."""

from __future__ import annotations

from django.views import View
from django.views.decorators.http import require_GET
from django.utils.decorators import method_decorator

from apps.api.api_contract import CONTRACT_VERSION, api_success
from apps.api.api_v1_manifest import build_api_v1_manifest_data


@method_decorator(require_GET, name="dispatch")
class ApiV2PingView(View):
    """GET /api/v2/ping — liveness + contract version."""

    def get(self, request):
        return api_success(
            {"message": "RunMyCampus API", "api_version": "2"},
            meta={"contract_version": CONTRACT_VERSION},
        )


@method_decorator(require_GET, name="dispatch")
class ApiV2ManifestView(View):
    """
    GET /api/v2/manifest.json — same discovery as v1 plus v2 fields and OAuth URLs.
    """

    def get(self, request):
        from django.http import JsonResponse

        base = request.build_absolute_uri("/").rstrip("/")
        payload = build_api_v1_manifest_data(request)
        payload["api_version"] = "2.0"
        payload["contract_version"] = CONTRACT_VERSION
        payload["oauth"] = {
            "authorize_url": f"{base}/api/v1/oauth/authorize/",
            "token_url": f"{base}/api/v1/oauth/token/",
            "grant_types": [
                "authorization_code",
                "client_credentials",
                "refresh_token",
            ],
        }
        payload["links"] = {
            "v1_manifest": f"{base}/api/v1/manifest.json",
            "v2_ping": f"{base}/api/v2/ping/",
            "developer_hub": f"{base}/developer/",
        }
        return JsonResponse(payload)

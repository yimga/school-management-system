"""API views for schools: /api/config for dynamic branding (Phase 2)."""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status


def _offline_enabled_for_request(request):
    """True if offline is enabled: global switch on and (no school or school has offline_mode via Policy Registry)."""
    from apps.platform_runtime.helpers import get_effective_site_settings
    from apps.policies.policy_registry import get_effective_policy
    site = get_effective_site_settings(request=request)
    school = getattr(request, "school", None)
    if not school:
        return bool(site.enable_offline_mode)
    try:
        enabled = get_effective_policy(school, user=getattr(request, "user", None), capability="offline_mode").get("enabled", False)
    except Exception:
        enabled = False
    return bool(site.enable_offline_mode) and enabled


class SchoolConfigAPI(APIView):
    """
    GET /api/config — returns current school branding and features from request host.
    Used by SPA/mobile when not using server-rendered context.
    Rate-limited per IP to avoid abuse (see ALLOWANY_API_AUDIT.md).
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from apps.api.rate_limit import throttle_ip_request
        allowed, retry_after = throttle_ip_request(
            request,
            scope="school_config_api",
            max_count=120,
            window_seconds=60,
        )
        if not allowed:
            return Response(
                {"detail": "Request limit exceeded. Retry later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(retry_after)},
            )
        school = getattr(request, "school", None)
        if not school:
            from apps.platform_runtime.helpers import get_effective_site_settings

            site = get_effective_site_settings(request=request)
            return Response({
                "schoolName": None,
                "logoUrl": None,
                "primaryColor": "#0d6efd",
                "accentColor": "#198754",
                "features": {},
                "offlineEnabled": bool(site.enable_offline_mode),
            })
        from apps.policies.policy_registry import get_effective_policy
        policy = get_effective_policy(school, user=getattr(request, "user", None))
        features = policy.get("features") or {}
        return Response({
            "schoolName": school.name,
            "logoUrl": getattr(school, "logo_url", None) or "",
            "primaryColor": getattr(school, "primary_color", None) or "#0d6efd",
            "accentColor": getattr(school, "accent_color", None) or "#198754",
            "features": features,
            "offlineEnabled": _offline_enabled_for_request(request),
        })

"""API views for schools: /api/config for dynamic branding (Phase 2)."""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny


def _offline_enabled_for_request(request):
    """True if offline is enabled: global switch on and (no school or school has offline_mode via Policy Registry)."""
    from apps.siteconfig.models import SiteSettings
    from apps.policies.resolver import get_effective_policy
    site = SiteSettings.get_solo()
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
    """
    permission_classes = [AllowAny]

    def get(self, request):
        school = getattr(request, "school", None)
        if not school:
            from apps.siteconfig.models import SiteSettings
            site = SiteSettings.get_solo()
            return Response({
                "schoolName": None,
                "logoUrl": None,
                "primaryColor": "#0d6efd",
                "accentColor": "#198754",
                "features": {},
                "offlineEnabled": bool(site.enable_offline_mode),
            })
        from apps.policies.resolver import get_effective_policy
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

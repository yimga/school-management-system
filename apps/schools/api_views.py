"""API views for schools: /api/config for dynamic branding (Phase 2)."""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny


def _offline_enabled_for_request(request):
    """True if offline is enabled: global switch on and (no school or school has offline_mode module)."""
    from apps.siteconfig.models import SiteSettings
    site = SiteSettings.get_solo()
    school = getattr(request, "school", None)
    return bool(site.enable_offline_mode) and (not school or school.has_feature("offline_mode"))


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
        features = getattr(school, "features", None) or {}
        return Response({
            "schoolName": school.name,
            "logoUrl": getattr(school, "logo_url", None) or "",
            "primaryColor": getattr(school, "primary_color", None) or "#0d6efd",
            "accentColor": getattr(school, "accent_color", None) or "#198754",
            "features": features,
            "offlineEnabled": _offline_enabled_for_request(request),
        })

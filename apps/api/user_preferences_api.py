"""
API for user portal preferences (e.g. pinned sidebar items for Quick access).
"""

from django.db import DatabaseError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from apps.platform_runtime.helpers import get_effective_site_settings
from apps.runtime_blueprints.models import DashboardUserPreference
from apps.siteconfig.portal_sidebar_items import build_portal_sidebar_items

PREFERENCE_NAV_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    TypeError,
    ValueError,
)


class PortalPreferencesAPI(APIView):
    """
    GET: return pinned_sidebar_items for the current user.
    PATCH: update pinned_sidebar_items (list of sidebar item ids). Only ids present in
    the user's portal sidebar are accepted.
    """

    permission_classes = [IsAuthenticated]

    def _allowed_ids(self, request):
        try:
            site = getattr(request, "site", None) or (
                getattr(request, "SITE", None) if hasattr(request, "SITE") else None
            )
            if site is None:
                site = get_effective_site_settings(request=request)
            items = build_portal_sidebar_items(request, site)
            return {
                str(item.get("id"))
                for item in items
                if item.get("id") and item.get("url")
            }
        except PREFERENCE_NAV_FAILURES:
            return set()

    def get(self, request):
        prefs = getattr(request.user, "dashboard_preferences", None)
        if not prefs:
            return Response({"pinned_sidebar_items": []})
        pinned = list(prefs.pinned_sidebar_items or [])
        return Response({"pinned_sidebar_items": pinned})

    def patch(self, request):
        data = getattr(request, "data", None) or request.POST
        raw = data.get("pinned_sidebar_items")
        if raw is None:
            return Response(
                {"error": "pinned_sidebar_items is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(raw, list):
            return Response(
                {"error": "pinned_sidebar_items must be a list"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        allowed = self._allowed_ids(request)
        # Keep order, only include allowed ids
        pinned = [str(x).strip() for x in raw if str(x).strip() in allowed]
        # Deduplicate preserving order
        seen = set()
        pinned_dedup = []
        for pid in pinned:
            if pid not in seen:
                seen.add(pid)
                pinned_dedup.append(pid)

        prefs, _ = DashboardUserPreference.objects.get_or_create(
            user=request.user, defaults={"pinned_sidebar_items": []}
        )
        prefs.pinned_sidebar_items = pinned_dedup
        prefs.save(update_fields=["pinned_sidebar_items", "updated_at"])

        return Response({"pinned_sidebar_items": prefs.pinned_sidebar_items})


class ControlPlanePreferencesAPI(APIView):
    """
    GET: return control_plane_pinned_items for the current user (Manager Quick access).
    PATCH: update control_plane_pinned_items (list of control plane nav item ids).
    Only ids present in build_control_plane_nav are accepted.
    Use on manager host only (e.g. /api/control-plane-preferences/).
    """

    permission_classes = [IsAuthenticated]

    def _allowed_ids(self, request):
        try:
            from apps.schools.control_plane_nav import build_control_plane_nav

            groups = build_control_plane_nav(request)
            allowed = set()
            for grp in groups:
                for it in grp.get("items") or []:
                    iid = it.get("id")
                    if iid and it.get("url"):
                        allowed.add(str(iid))
            return allowed
        except PREFERENCE_NAV_FAILURES:
            return set()

    def get(self, request):
        prefs = getattr(request.user, "dashboard_preferences", None)
        if not prefs:
            return Response({"control_plane_pinned_items": []})
        pinned = list(getattr(prefs, "control_plane_pinned_items", None) or [])
        return Response({"control_plane_pinned_items": pinned})

    def patch(self, request):
        data = getattr(request, "data", None) or request.POST
        raw = data.get("control_plane_pinned_items")
        if raw is None:
            return Response(
                {"error": "control_plane_pinned_items is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(raw, list):
            return Response(
                {"error": "control_plane_pinned_items must be a list"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        allowed = self._allowed_ids(request)
        pinned = [str(x).strip() for x in raw if str(x).strip() in allowed]
        seen = set()
        pinned_dedup = []
        for pid in pinned:
            if pid not in seen:
                seen.add(pid)
                pinned_dedup.append(pid)

        prefs, _ = DashboardUserPreference.objects.get_or_create(
            user=request.user,
            defaults={"control_plane_pinned_items": []},
        )
        prefs.control_plane_pinned_items = pinned_dedup
        prefs.save(update_fields=["control_plane_pinned_items", "updated_at"])

        return Response(
            {"control_plane_pinned_items": prefs.control_plane_pinned_items}
        )

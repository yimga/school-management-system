"""
API for user portal preferences (e.g. pinned sidebar items for Quick access).
"""

from django.db import DatabaseError
from drf_spectacular.utils import OpenApiTypes, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.siteconfig.config_service import get_effective_site_settings
from apps.runtime_blueprints.models import DashboardUserPreference
from apps.siteconfig.portal_sidebar_items import build_portal_sidebar_items


_PortalPinnedResponse = inline_serializer(
    name="PortalPinnedSidebarItemsResponse",
    fields={"pinned_sidebar_items": serializers.ListField(child=serializers.CharField())},
)

_PortalPinnedRequest = inline_serializer(
    name="PortalPinnedSidebarItemsPatch",
    fields={"pinned_sidebar_items": serializers.ListField(child=serializers.CharField())},
)

_CPPinnedResponse = inline_serializer(
    name="ControlPlanePinnedItemsResponse",
    fields={"control_plane_pinned_items": serializers.ListField(child=serializers.CharField())},
)

_CPPinnedRequest = inline_serializer(
    name="ControlPlanePinnedItemsPatch",
    fields={"control_plane_pinned_items": serializers.ListField(child=serializers.CharField())},
)

PREFERENCE_NAV_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    TypeError,
    ValueError,
)


@extend_schema(tags=["User preferences"])
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
                # config-resolver-allow: namespace object passed to build_portal_sidebar_items
                site = get_effective_site_settings(request=request)
            items = build_portal_sidebar_items(request, site)
            return {
                str(item.get("id"))
                for item in items
                if item.get("id") and item.get("url")
            }
        except PREFERENCE_NAV_FAILURES:
            return set()

    @extend_schema(responses={200: _PortalPinnedResponse})
    def get(self, request):
        prefs = getattr(request.user, "dashboard_preferences", None)
        if not prefs:
            return Response({"pinned_sidebar_items": []})
        pinned = list(prefs.pinned_sidebar_items or [])
        return Response({"pinned_sidebar_items": pinned})

    @extend_schema(request=_PortalPinnedRequest, responses={200: _PortalPinnedResponse, 400: OpenApiTypes.OBJECT})
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


_DashboardPackResponse = inline_serializer(
    name="DashboardPackPreferenceResponse",
    fields={
        "role": serializers.CharField(),
        "selected": serializers.CharField(allow_blank=True),
        "available": serializers.ListField(child=serializers.DictField()),
    },
)

_DashboardPackRequest = inline_serializer(
    name="DashboardPackPreferencePatch",
    fields={"dashboard_pack": serializers.CharField(allow_blank=True)},
)


@extend_schema(tags=["User preferences"])
class DashboardPackPreferenceAPI(APIView):
    """
    Per-user dashboard-pack switcher (Dashboard Packs revival, Phase 3).

    GET: the user's current pack choice for their role + the packs they may switch
    between (the active packs in their role family).
    PATCH: set ``dashboard_pack`` (a DashboardPack.code) for the user's role. Only codes
    in the allowed set are accepted; an empty string clears the choice (revert to the
    school/role default).
    """

    permission_classes = [IsAuthenticated]

    def _role(self, request):
        from apps.siteconfig.dashboard_pack_resolver import assignment_role_for_user_role

        return assignment_role_for_user_role(getattr(request.user, "role", ""))

    def _available(self, request):
        from apps.siteconfig.dashboard_pack_resolver import available_packs_for_user

        return available_packs_for_user(request.user)

    @extend_schema(responses={200: _DashboardPackResponse})
    def get(self, request):
        role = self._role(request)
        available = self._available(request)
        prefs = getattr(request.user, "dashboard_preferences", None)
        selected = ""
        if prefs and hasattr(prefs, "get_dashboard_pack"):
            selected = prefs.get_dashboard_pack(role)
        return Response({"role": role, "selected": selected, "available": available})

    @extend_schema(
        request=_DashboardPackRequest,
        responses={200: _DashboardPackResponse, 400: OpenApiTypes.OBJECT},
    )
    def patch(self, request):
        data = getattr(request, "data", None) or request.POST
        raw = data.get("dashboard_pack")
        if raw is None:
            return Response(
                {"error": "dashboard_pack is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        code = str(raw).strip()
        role = self._role(request)
        available = self._available(request)
        allowed_codes = {p["code"] for p in available}
        if code and code not in allowed_codes:
            return Response(
                {"error": "dashboard_pack not available for your role"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prefs, _ = DashboardUserPreference.objects.get_or_create(
            user=request.user, defaults={"role_dashboard_packs": {}}
        )
        prefs.set_dashboard_pack(role, code)
        prefs.save(update_fields=["role_dashboard_packs", "updated_at"])
        selected = prefs.get_dashboard_pack(role)
        return Response({"role": role, "selected": selected, "available": available})


@extend_schema(tags=["User preferences"])
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

    @extend_schema(responses={200: _CPPinnedResponse})
    def get(self, request):
        prefs = getattr(request.user, "dashboard_preferences", None)
        if not prefs:
            return Response({"control_plane_pinned_items": []})
        pinned = list(getattr(prefs, "control_plane_pinned_items", None) or [])
        return Response({"control_plane_pinned_items": pinned})

    @extend_schema(request=_CPPinnedRequest, responses={200: _CPPinnedResponse, 400: OpenApiTypes.OBJECT})
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

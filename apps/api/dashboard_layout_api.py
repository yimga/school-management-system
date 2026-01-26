"""
Dashboard layout APIs for drag/drop configuration.
Security-first: role-gated per page and user-scoped save.
"""
from __future__ import annotations

from typing import Any, Dict, List

from django.http import Http404
from django.db import models
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.siteconfig.models_dashboard import DashboardWidget, DashboardLayout


class DashboardWidgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardWidget
        fields = [
            "id",
            "name",
            "description",
            "widget_type",
            "page",
            "template_path",
            "default_width",
            "default_column",
            "default_order",
            "refresh_interval",
            "required_role",
            "allowed_roles",
            "order",
        ]


class DashboardLayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardLayout
        fields = ["layout"]

    def validate_layout(self, value: Dict[str, Any]):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Layout must be a JSON object.")
        return value


def _allowed_roles_for_page(page: str) -> List[str]:
    """Whitelist roles that can access a given dashboard page."""
    page = page.lower()
    role_backend = [
        "SUPERADMIN",
        "ADMIN",
        "IT_ADMIN",
        "LEADERSHIP",
        "PRINCIPAL",
        "VICE_PRINCIPAL",
        "DEAN",
        "CENSOR",
        "FINANCE_STAFF",
        "ACADEMICS_STAFF",
        "COMMS_STAFF",
    ]
    role_admin = [
        "SUPERADMIN",
        "ADMIN",
        "IT_ADMIN",
        "LEADERSHIP",
        "PRINCIPAL",
        "VICE_PRINCIPAL",
    ]
    return {
        "parent": ["PARENT"],
        "student": ["STUDENT"],
        "teacher": ["TEACHER", "DEPT_LEAD", "HOD"],
        # Backend dashboards / consoles (staff-only)
        "backend": role_backend,
        "backend-dashboard": role_backend,
        "backend_console": role_backend,
        # Django admin and admin-style dashboards
        "admin": role_admin,
        "admin-security": role_admin,
        # Additional dashboards
        "finance": ["SUPERADMIN", "ADMIN", "LEADERSHIP", "FINANCE_STAFF"],
        "analytics": ["SUPERADMIN", "ADMIN", "LEADERSHIP", "ACADEMICS_STAFF"],
        "entity-console": ["SUPERADMIN", "ADMIN", "LEADERSHIP", "IT_ADMIN"],
        # Portal KB is safe to show to any authenticated role.
        "portal-kb": ["SUPERADMIN", "ADMIN", "LEADERSHIP", "IT_ADMIN", "ACADEMICS_STAFF", "COMMS_STAFF", "TEACHER", "DEPT_LEAD", "HOD", "PARENT", "STUDENT"],
    }.get(page, [])


class DashboardLayoutAPI(APIView):
    """
    GET: return widgets + current layout for a page (role/user scoped).
    PUT/PATCH: save user-specific layout for the page.
    """

    permission_classes = [IsAuthenticated]

    def get_user_role(self, user: User) -> str:
        return (getattr(user, "role", "") or "").upper()

    def _enforce_page_access(self, page: str, user: User) -> None:
        allowed = _allowed_roles_for_page(page)
        role = self.get_user_role(user)
        if not allowed or role not in allowed:
            raise Http404()

    def get(self, request, page: str):
        page = page.lower()
        self._enforce_page_access(page, request.user)

        role = self.get_user_role(request.user)
        # Widgets: active, for this page, and allowed by role
        widgets_qs = DashboardWidget.objects.filter(page=page, is_active=True).order_by("order")
        widgets_qs = widgets_qs.filter(
            models.Q(required_role="ANY")
            | models.Q(required_role=role)
            | models.Q(allowed_roles__contains=[role])
        )
        widgets = DashboardWidgetSerializer(widgets_qs, many=True).data

        layout_obj = (
            DashboardLayout.objects.filter(user=request.user, page=page).first()
            or DashboardLayout.objects.filter(page=page, role=role, is_default=True).first()
        )
        layout_data = {"layout": layout_obj.layout if layout_obj else {}}

        return Response(
            {
                "page": page,
                "role": role,
                "layout": layout_data["layout"],
                "widgets": widgets,
            }
        )

    def put(self, request, page: str):
        return self._save(request, page)

    def patch(self, request, page: str):
        return self._save(request, page)

    def _save(self, request, page: str):
        page = page.lower()
        self._enforce_page_access(page, request.user)
        serializer = DashboardLayoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        layout_obj, _ = DashboardLayout.objects.get_or_create(
            user=request.user,
            page=page,
            defaults={"role": self.get_user_role(request.user)},
        )
        layout_obj.layout = serializer.validated_data["layout"]
        layout_obj.is_default = False
        layout_obj.save(update_fields=["layout", "is_default", "updated_at"])
        return Response({"status": "ok", "layout": layout_obj.layout}, status=status.HTTP_200_OK)

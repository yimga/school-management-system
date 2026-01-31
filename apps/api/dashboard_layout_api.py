"""
Dashboard layout APIs for drag/drop configuration.
Security-first: role-gated per page and user-scoped save.
"""
from __future__ import annotations

from typing import Any, Dict, List, Set

from django.http import Http404
from django.db import models
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.siteconfig.dashboard_views import _can_customize, _log_layout_audit, get_layout_for_page
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
            # Admin-configurable presentation controls (per-widget)
            "allowed_sizes",
            "default_size",
            "allowed_variants",
            "default_variant",
            "chart_type",
            "order",
        ]


class DashboardLayoutSerializer(serializers.Serializer):
    """
    Validates user-submitted layout payloads.

    Layout schema:
      { "items": [ { "id": "...", "column": "...", "order": 0, "size": "md", "variant": "default" }, ... ], "__settings__": {...} }

    Security: ensures widget IDs are allowed for the current user/page and prevents invalid size/variant values.
    """

    layout = serializers.DictField()

    def validate_layout(self, value: Dict[str, Any]):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Layout must be a JSON object.")

        items = value.get("items", [])
        if items is None:
            items = []
        if not isinstance(items, list):
            raise serializers.ValidationError("layout.items must be a list.")

        allowed_widgets: Dict[str, DashboardWidget] = self.context.get("allowed_widgets") or {}
        if not isinstance(allowed_widgets, dict):
            allowed_widgets = {}

        normalized: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise serializers.ValidationError(f"layout.items[{idx}] must be an object.")

            widget_id = str(item.get("id") or "").strip()
            if not widget_id:
                raise serializers.ValidationError(f"layout.items[{idx}].id is required.")
            if widget_id in seen_ids:
                raise serializers.ValidationError(f"Duplicate widget id '{widget_id}' in layout.")
            seen_ids.add(widget_id)

            widget = allowed_widgets.get(widget_id) if allowed_widgets else None
            if allowed_widgets and widget_id not in allowed_widgets:
                raise serializers.ValidationError(f"Widget '{widget_id}' is not allowed for this page/user.")

            column = str(item.get("column") or "").strip()
            if not column:
                raise serializers.ValidationError(f"layout.items[{idx}].column is required.")

            order = item.get("order", idx)
            try:
                order = int(order)
            except (TypeError, ValueError):
                raise serializers.ValidationError(f"layout.items[{idx}].order must be an integer.")

            size = item.get("size")
            if widget and size is not None:
                size = str(size).strip().lower()
                allowed_sizes = set(widget.resolved_allowed_sizes())
                if size not in allowed_sizes:
                    raise serializers.ValidationError(
                        f"layout.items[{idx}].size '{size}' is not allowed for widget '{widget_id}'."
                    )

            variant = item.get("variant")
            if widget and variant is not None:
                variant = str(variant).strip().lower()
                allowed_variants = set(widget.resolved_allowed_variants())
                if variant not in allowed_variants:
                    raise serializers.ValidationError(
                        f"layout.items[{idx}].variant '{variant}' is not allowed for widget '{widget_id}'."
                    )

            normalized.append(
                {
                    "id": widget_id,
                    "column": column,
                    "order": order,
                    "size": size,
                    "variant": variant,
                }
            )

        settings = value.get("__settings__", {}) or {}
        sanitized_settings = _sanitize_layout_settings(settings, allowed_widgets)

        return {"items": normalized, "__settings__": sanitized_settings}


ALLOWED_TILE_VARIANTS = {"default", "compact", "flat"}
ALLOWED_CHART_TYPES = {"line", "bar", "radar", "doughnut", "pie", "polarArea"}


def _sanitize_custom_links(raw_links: Any) -> list[dict]:
    clean_links = []
    if not raw_links:
        return clean_links
    for link in raw_links:
        if not isinstance(link, dict):
            continue
        label = str(link.get("label") or "").strip()
        url = str(link.get("url") or "").strip()
        icon = str(link.get("icon") or "bi-link").strip()
        if not label or not url:
            continue
        clean_links.append({"label": label[:60], "url": url[:256], "icon": icon or "bi-link"})
    return clean_links


def _sanitize_widget_meta(raw_meta: Any, allowed_widgets: Dict[str, DashboardWidget]) -> dict:
    clean_meta = {}
    if not isinstance(raw_meta, dict):
        return clean_meta
    for widget_id, config in raw_meta.items():
        if widget_id not in allowed_widgets or not isinstance(config, dict):
            continue
        widget = allowed_widgets[widget_id]
        size = str(config.get("size") or widget.default_size or "md").strip().lower()
        variant = str(config.get("variant") or widget.default_variant or "default").strip().lower()
        allowed_sizes = widget.resolved_allowed_sizes()
        allowed_variants = widget.resolved_allowed_variants()
        if size not in allowed_sizes:
            size = widget.default_size or (allowed_sizes[0] if allowed_sizes else "md")
        if variant not in allowed_variants:
            variant = widget.default_variant or (allowed_variants[0] if allowed_variants else "default")
        meta = {"size": size, "variant": variant}
        # chart_type for data visualizer widgets (user override)
        if getattr(widget, "widget_type", "") == "chart":
            ct = str(config.get("chart_type") or "").strip().lower()
            if ct and ct in ALLOWED_CHART_TYPES:
                meta["chart_type"] = ct
            elif str(getattr(widget, "chart_type", "") or "").strip():
                meta["chart_type"] = str(widget.chart_type or "").strip().lower()
        clean_meta[widget_id] = meta
    return clean_meta


def _sanitize_layout_settings(raw_settings: Any, allowed_widgets: Dict[str, DashboardWidget]) -> dict:
    settings = raw_settings if isinstance(raw_settings, dict) else {}
    sidebar_items = []
    for item in settings.get("sidebar_items") or []:
        sidebar_items.append(str(item))
    tile_variant = str(settings.get("tile_variant") or "default").strip().lower()
    if tile_variant not in ALLOWED_TILE_VARIANTS:
        tile_variant = "default"
    widget_meta = _sanitize_widget_meta(settings.get("widget_meta"), allowed_widgets)
    raw_hidden = settings.get("hidden_widget_ids") or []
    hidden_widget_ids = []
    if isinstance(raw_hidden, list):
        for w in raw_hidden:
            w = str(w).strip()
            if w and (not allowed_widgets or w in allowed_widgets):
                hidden_widget_ids.append(w)

    raw_pinned = settings.get("pinned_widgets") or []
    pinned_widgets = []
    if isinstance(raw_pinned, list):
        for p in raw_pinned:
            wid = p.get("widget_id") if isinstance(p, dict) else None
            if isinstance(p, dict) and wid and (not allowed_widgets or wid in allowed_widgets):
                pages = p.get("pages") or []
                if isinstance(pages, list):
                    pinned_widgets.append({
                        "widget_id": str(wid),
                        "pages": [str(x) for x in pages if x],
                    })

    return {
        "show_sidebar": bool(settings.get("show_sidebar")),
        "sidebar_items": sidebar_items,
        "tile_variant": tile_variant,
        "custom_links": _sanitize_custom_links(settings.get("custom_links")),
        "widget_meta": widget_meta,
        "hidden_widget_ids": hidden_widget_ids,
        "pinned_widgets": pinned_widgets,
    }


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
        "payroll": ["SUPERADMIN", "ADMIN", "LEADERSHIP", "FINANCE_STAFF"],
        "emis": role_backend,
        "entity-console": ["SUPERADMIN", "ADMIN", "LEADERSHIP", "IT_ADMIN"],
        # Portal KB is safe to show to any authenticated role.
        "portal-kb": ["SUPERADMIN", "ADMIN", "LEADERSHIP", "IT_ADMIN", "ACADEMICS_STAFF", "COMMS_STAFF", "TEACHER", "DEPT_LEAD", "HOD", "PARENT", "STUDENT"],
    }.get(page, [])


class AvailableWidgetsAPI(APIView):
    """
    GET: return available widgets for a dashboard page (role-scoped).
    Used by palette UI and AI Copilot for widget discovery.
    """
    permission_classes = [IsAuthenticated]

    def get_user_role(self, user: User) -> str:
        return (getattr(user, "role", "") or "").upper()

    def get(self, request):
        page = (request.GET.get("page") or "backend").strip().lower()
        allowed = _allowed_roles_for_page(page)
        role = self.get_user_role(request.user)
        if not allowed or role not in allowed:
            raise Http404()
        widgets_qs = DashboardWidget.objects.filter(page=page, is_active=True).order_by("order")
        widgets_qs = widgets_qs.filter(
            models.Q(required_role="ANY")
            | models.Q(required_role=role)
            | models.Q(allowed_roles__contains=[role])
        )
        widgets = DashboardWidgetSerializer(widgets_qs, many=True).data
        return Response({"page": page, "widgets": widgets})


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

        layout_obj = get_layout_for_page(request.user, page)
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

    def delete(self, request, page: str):
        """Reset layout to default (RBAC: requires _can_customize)."""
        page = page.lower()
        self._enforce_page_access(page, request.user)
        if not _can_customize(request.user):
            return Response(
                {"detail": "Only staff and allowed roles can reset dashboard layout."},
                status=status.HTTP_403_FORBIDDEN,
            )
        DashboardLayout.objects.filter(user=request.user, page=page).delete()
        return Response({"status": "ok", "layout": {}}, status=status.HTTP_200_OK)

    def _save(self, request, page: str):
        page = page.lower()
        self._enforce_page_access(page, request.user)
        if not _can_customize(request.user):
            return Response(
                {"detail": "Only staff and allowed roles can save dashboard layout."},
                status=status.HTTP_403_FORBIDDEN,
            )

        role = self.get_user_role(request.user)
        widgets_qs = DashboardWidget.objects.filter(page=page, is_active=True).order_by("order")
        widgets_qs = widgets_qs.filter(
            models.Q(required_role="ANY")
            | models.Q(required_role=role)
            | models.Q(allowed_roles__contains=[role])
        )
        allowed_widgets = {w.id: w for w in widgets_qs}

        serializer = DashboardLayoutSerializer(data=request.data, context={"allowed_widgets": allowed_widgets})
        serializer.is_valid(raise_exception=True)

        layout_obj, _ = DashboardLayout.objects.get_or_create(
            user=request.user,
            page=page,
            defaults={"role": self.get_user_role(request.user)},
        )
        old_layout = layout_obj.layout or {}
        old_settings = (old_layout.get("__settings__", {}) or {}).copy()
        new_layout = serializer.validated_data["layout"]
        layout_obj.layout = new_layout
        layout_obj.is_default = False
        layout_obj.save(update_fields=["layout", "is_default", "updated_at"])
        new_settings = (new_layout.get("__settings__", {}) or {})
        _log_layout_audit(request.user, old_settings, new_settings)
        return Response({"status": "ok", "layout": layout_obj.layout}, status=status.HTTP_200_OK)

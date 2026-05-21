"""Shopify-grade theme builder canvas — dual-plane layout + live preview."""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.http import require_http_methods

palette_logger = logging.getLogger(__name__)

from apps.schools.control_plane import is_control_plane_request, user_has_control_plane_access
from apps.siteconfig.theme_builder import TOKEN_FIELD_NAMES, default_layout, normalize_layout
from apps.siteconfig.theme_builder_plane import (
    PLANE_OPERATOR,
    PLANE_TENANT,
    build_publish_snapshot,
    list_publish_log,
    load_builder_layout,
    persist_builder_layout,
    persist_operator_brand_colors,
    persist_tenant_brand_colors,
    record_publish_event,
    resolve_theme_builder_plane,
    rollback_previous_publish,
)
from apps.siteconfig.views import get_theme_colors_context


def _settings_manage_required(user) -> bool:
    return getattr(user, "is_superuser", False) or (
        hasattr(user, "has_feature_permission")
        and user.has_feature_permission("settings.manage")
    )


def _builder_access_ok(request) -> bool:
    user = request.user
    if is_control_plane_request(request):
        return user_has_control_plane_access(user)
    return _settings_manage_required(user)


@login_required
@require_http_methods(["GET"])
def theme_builder(request):
    if not _builder_access_ok(request):
        raise PermissionDenied
    plane = resolve_theme_builder_plane(request)
    ctx = get_theme_colors_context(request)
    layout = load_builder_layout(request)
    if not (layout.get("blocks") or []):
        layout = default_layout()
    ctx["theme_builder_layout"] = layout
    ctx["theme_builder_layout_json"] = json.dumps(layout)
    ctx["theme_publish_log"] = list_publish_log(request)
    ctx["theme_builder_plane"] = plane
    ctx["operator_plane"] = plane == PLANE_OPERATOR
    if plane == PLANE_OPERATOR:
        ctx["theme_builder_plane_label"] = _("Platform operator")
        ctx["theme_builder_plane_hint"] = _(
            "Layout and chrome colors apply to RunMyCampus Manager only — not tenant schools."
        )
        template_name = "siteconfig/theme_builder_control_plane.html"
    else:
        school = getattr(request, "school", None)
        ctx["theme_builder_plane_label"] = _("School tenant")
        ctx["theme_builder_school_name"] = getattr(school, "name", "") or ""
        ctx["theme_builder_plane_hint"] = _(
            "Changes apply only to this school's portals and staff dashboards."
        )
        template_name = "siteconfig/theme_builder.html"
    return render(request, template_name, ctx)


class ThemeBuilderLayoutAPIView(View):
    """GET/POST /siteconfig/theme-experience/builder/api/layout/"""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        if not _builder_access_ok(request):
            return JsonResponse({"error": "Forbidden"}, status=403)
        try:
            layout = load_builder_layout(request)
        except PermissionDenied as exc:
            return JsonResponse({"error": str(exc)}, status=403)
        return JsonResponse({"layout": layout, "plane": resolve_theme_builder_plane(request)})

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        if not _builder_access_ok(request):
            return JsonResponse({"error": "Forbidden"}, status=403)
        try:
            data = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        layout = normalize_layout(data.get("layout") or data)
        try:
            persist_builder_layout(request, layout)
        except PermissionDenied as exc:
            return JsonResponse({"error": str(exc)}, status=403)
        return JsonResponse(
            {"ok": True, "layout": layout, "plane": resolve_theme_builder_plane(request)}
        )


class ThemeBuilderPublishAPIView(View):
    """POST /siteconfig/theme-experience/builder/api/publish/ — layout + brand tokens."""

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        if not _builder_access_ok(request):
            return JsonResponse({"error": "Forbidden"}, status=403)
        try:
            data = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        plane = resolve_theme_builder_plane(request)
        try:
            layout = normalize_layout(data.get("layout") or load_builder_layout(request))
            persist_builder_layout(request, layout)
        except PermissionDenied as exc:
            return JsonResponse({"error": str(exc)}, status=403)

        from apps.siteconfig.brand_guard_runtime import guard_brand_dict

        colors_in = data.get("colors") if isinstance(data.get("colors"), dict) else {}
        surface = layout.get("surface") or "light"
        guarded, adjusted = guard_brand_dict(colors_in, effective_surface=surface)
        publish = bool(data.get("publish"))

        if plane == PLANE_OPERATOR:
            if colors_in:
                persist_operator_brand_colors(guarded, request=request)
            if publish:
                record_publish_event(
                    request,
                    event_type="operator_builder_publish",
                    summary=build_publish_snapshot(layout, guarded, plane=plane),
                )
            return JsonResponse(
                {
                    "ok": True,
                    "layout": layout,
                    "plane": plane,
                    "brand_adjusted": adjusted,
                    "colors": {k: guarded.get(k) for k in TOKEN_FIELD_NAMES},
                }
            )

        if plane == PLANE_TENANT:
            if colors_in:
                result = persist_tenant_brand_colors(
                    request,
                    colors_in,
                    publish=publish,
                    effective_surface=str(surface),
                )
                if not result.get("ok"):
                    return JsonResponse(result, status=400)
                if publish:
                    record_publish_event(
                        request,
                        event_type="tenant_builder_publish",
                        summary=build_publish_snapshot(layout, result.get("colors", guarded), plane=plane),
                    )
                return JsonResponse(
                    {
                        "ok": True,
                        "layout": layout,
                        "plane": plane,
                        "brand_adjusted": result.get("brand_adjusted", adjusted),
                        "colors": result.get("colors", {}),
                    }
                )
            return JsonResponse(
                {
                    "ok": True,
                    "layout": layout,
                    "plane": plane,
                    "brand_adjusted": adjusted,
                    "colors": {k: guarded.get(k) for k in TOKEN_FIELD_NAMES},
                }
            )

        return JsonResponse(
            {
                "ok": True,
                "layout": layout,
                "plane": plane,
                "brand_adjusted": adjusted,
                "colors": {k: guarded.get(k) for k in TOKEN_FIELD_NAMES},
            }
        )


class ThemeBuilderPublishLogAPIView(View):
    """GET /siteconfig/theme-experience/builder/api/publish-log/"""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        if not _builder_access_ok(request):
            return JsonResponse({"error": "Forbidden"}, status=403)
        return JsonResponse(
            {
                "plane": resolve_theme_builder_plane(request),
                "entries": list_publish_log(request),
            }
        )


class ThemeBuilderRollbackAPIView(View):
    """POST /siteconfig/theme-experience/builder/api/rollback/ — restore previous publish."""

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        if not _builder_access_ok(request):
            return JsonResponse({"error": "Forbidden"}, status=403)
        result = rollback_previous_publish(request)
        status = 200 if result.get("ok") else 400
        return JsonResponse(result, status=status)


class ThemeBuilderPreviewAPIView(View):
    """POST — open full-site preview tab (session overlay) from builder tokens."""

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        if not _builder_access_ok(request):
            return JsonResponse({"error": "Forbidden"}, status=403)
        try:
            data = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        from apps.siteconfig.context_processors import SESSION_KEY

        colors = data.get("colors") if isinstance(data.get("colors"), dict) else {}
        surface = (data.get("surface") or "light").strip().lower()
        preview = dict(colors)
        preview["use_dark_mode"] = surface == "dark"
        preview["theme_brightness"] = "dark" if surface == "dark" else "light"
        request.session[SESSION_KEY] = preview
        request.session.modified = True
        try:
            request.session.save()
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            pass
        from django.urls import NoReverseMatch, reverse

        preview_path = "/"
        if resolve_theme_builder_plane(request) == PLANE_OPERATOR:
            candidates = (
                "super:dashboard",
                "siteconfig:operator_control_plane",
            )
        else:
            candidates = (
                "accounts:backend_dashboard",
                "authentication:backend_dashboard",
            )
        for name in candidates:
            try:
                preview_path = reverse(name)
                break
            except NoReverseMatch:
                continue

        return JsonResponse(
            {
                "ok": True,
                "preview_url": request.build_absolute_uri(preview_path),
                "plane": resolve_theme_builder_plane(request),
            }
        )


class PaletteGenerateView(LoginRequiredMixin, View):
    """POST /siteconfig/theme/palette/generate/

    Intelligent palette builder: operator submits one brand seed (or
    later, an extracted brand colour from a logo) and the platform
    returns a full WCAG-AA-compliant 11-stop palette via the AI gateway
    cloud tier — with a deterministic HSL fallback when the gateway is
    unavailable. NEVER raises on AI unreachable.

    Access model (rbac):
      * Staff / superuser: may generate for any tenant.
      * Tenant operator: may generate for the tenant on ``request.school``
        only (no ``school_id`` override accepted).
      * Anonymous: 401 (LoginRequiredMixin) — but POST-only so the gate
        usually shows as 405 to crawlers.
    """

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):  # noqa: ARG002
        # LoginRequiredMixin handles the auth gate; tenant-or-staff
        # gate runs inside post() so we can return a JSON error rather
        # than a redirect.
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        if not self._tenant_or_staff_ok(request):
            return JsonResponse({"error": "Forbidden"}, status=403)

        try:
            payload = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        seed_hex = str(payload.get("seed_hex") or "").strip()
        if not seed_hex:
            return JsonResponse(
                {"error": "Missing 'seed_hex'"}, status=400
            )
        raw_mode = str(payload.get("mode") or "dual").strip().lower()
        if raw_mode not in ("light", "dark", "dual"):
            raw_mode = "dual"

        # Lazy import — keeps URL config loadable even when AI deps shift.
        from services.ai_palette import generate_palette_from_seed

        try:
            result = generate_palette_from_seed(
                seed_hex,
                mode=raw_mode,  # type: ignore[arg-type]
                request=request,
            )
        except Exception:  # noqa: BLE001 — surface 500 only on true bugs
            palette_logger.exception("palette_generate_view: unexpected failure")
            return JsonResponse(
                {"error": "Palette generation failed unexpectedly"}, status=500
            )

        return JsonResponse({"ok": True, "palette": result.to_dict()})

    @staticmethod
    def _tenant_or_staff_ok(request) -> bool:
        user = request.user
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return True
        # Tenant operator: must have a school resolved on the request.
        if getattr(request, "school", None) is None:
            return False
        return _settings_manage_required(user) or _builder_access_ok(request)

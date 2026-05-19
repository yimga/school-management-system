"""Shopify-grade theme builder canvas — block layout + live preview."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View
from django.views.decorators.http import require_http_methods

from apps.siteconfig.theme_builder import (
    RUNTIME_PAYLOAD_KEY,
    default_layout,
    normalize_layout,
)
from apps.siteconfig.views import get_theme_colors_context


def _settings_manage_required(user) -> bool:
    return getattr(user, "is_superuser", False) or (
        hasattr(user, "has_feature_permission")
        and user.has_feature_permission("settings.manage")
    )


def _load_layout_from_runtime() -> dict:
    try:
        from apps.platform_runtime.models import RuntimeDefaults

        rt = RuntimeDefaults.get_singleton()
        payload = rt.payload if rt and isinstance(rt.payload, dict) else {}
        stored = payload.get(RUNTIME_PAYLOAD_KEY)
        return normalize_layout(stored)
    except (ImportError, AttributeError, TypeError, ValueError):
        return default_layout()


def _persist_layout(layout: dict) -> None:
    from apps.siteconfig.models import SiteSettings

    SiteSettings._persist_runtime_payload_updates({RUNTIME_PAYLOAD_KEY: layout})


@login_required
@require_http_methods(["GET"])
def theme_builder(request):
    if not _settings_manage_required(request.user):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied
    ctx = get_theme_colors_context(request)
    ctx["theme_builder_layout"] = _load_layout_from_runtime()
    ctx["theme_builder_layout_json"] = json.dumps(ctx["theme_builder_layout"])
    return render(
        request,
        "siteconfig/theme_builder.html",
        ctx,
    )


class ThemeBuilderLayoutAPIView(View):
    """GET/POST /siteconfig/theme-experience/builder/api/layout/"""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        if not _settings_manage_required(request.user):
            return JsonResponse({"error": "Forbidden"}, status=403)
        return JsonResponse({"layout": _load_layout_from_runtime()})

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        if not _settings_manage_required(request.user):
            return JsonResponse({"error": "Forbidden"}, status=403)
        try:
            data = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        layout = normalize_layout(data.get("layout") or data)
        _persist_layout(layout)
        return JsonResponse({"ok": True, "layout": layout})


class ThemeBuilderPublishAPIView(View):
    """POST /siteconfig/theme-experience/builder/api/publish/ — layout + brand tokens."""

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        if not _settings_manage_required(request.user):
            return JsonResponse({"error": "Forbidden"}, status=403)
        try:
            data = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        layout = normalize_layout(data.get("layout") or _load_layout_from_runtime())
        _persist_layout(layout)

        from apps.siteconfig.brand_guard_runtime import guard_brand_dict
        from apps.siteconfig.theme_builder import TOKEN_FIELD_NAMES

        colors_in = data.get("colors") if isinstance(data.get("colors"), dict) else {}
        surface = layout.get("surface") or "light"
        guarded, adjusted = guard_brand_dict(colors_in, effective_surface=surface)
        if colors_in:
            from apps.siteconfig.models import SiteSettings

            updates = {k: guarded.get(k) for k in TOKEN_FIELD_NAMES if guarded.get(k)}
            if updates:
                SiteSettings._persist_runtime_payload_updates(updates)

        if bool(data.get("publish")) and colors_in:
            from apps.siteconfig.config_service import get_effective_site_settings
            from apps.siteconfig.forms import ThemeColorsForm

            site = get_effective_site_settings(request=request)
            if site is None:
                from apps.siteconfig.views import build_platform_default_site_settings

                site = build_platform_default_site_settings()
            post_data = {k: guarded.get(k) for k in TOKEN_FIELD_NAMES if guarded.get(k)}
            if bool(data.get("preview_confirmed")):
                post_data["preview_confirmed"] = "1"
            form = ThemeColorsForm(post_data, instance=site, request=request)
            if not form.is_valid():
                return JsonResponse(
                    {"ok": False, "errors": form.errors},
                    status=400,
                )
            form.save()

        return JsonResponse(
            {
                "ok": True,
                "layout": layout,
                "brand_adjusted": adjusted,
                "colors": {k: guarded.get(k) for k in TOKEN_FIELD_NAMES},
            }
        )


class ThemeBuilderPreviewAPIView(View):
    """POST — open full-site preview tab (session overlay) from builder tokens."""

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        if not _settings_manage_required(request.user):
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
        from django.urls import NoReverseMatch, reverse

        preview_path = "/"
        for name in ("accounts:backend_dashboard", "authentication:backend_dashboard"):
            try:
                preview_path = reverse(name)
                break
            except NoReverseMatch:
                continue

        return JsonResponse(
            {
                "ok": True,
                "preview_url": request.build_absolute_uri(preview_path),
            }
        )

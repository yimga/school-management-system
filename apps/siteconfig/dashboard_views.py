"""
Utilities supporting dashboard customization workflows.
"""
import logging
import json
from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

from apps.siteconfig.models_dashboard import (
    DashboardLayout,
    DashboardLayoutAudit,
    DashboardUserPreference,
)

logger = logging.getLogger(__name__)

ALLOWED_CUSTOM_ROLES = {
    "ADMIN",
    "LEADERSHIP",
    "IT_ADMIN",
    "TEACHER",
    "PARENT",
    "SUPERADMIN",
}


def _can_customize(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    role = (getattr(user, "role", "") or "").upper()
    return bool(user.is_staff or user.is_superuser or role in ALLOWED_CUSTOM_ROLES)


def _log_layout_audit(user, old_settings, new_settings):
    """Persist layout setting shifts for RBAC auditing."""
    if not user or not user.is_authenticated:
        return
    old_settings = old_settings or {}
    new_settings = new_settings or {}

    old_meta = old_settings.get("widget_meta") or {}
    new_meta = new_settings.get("widget_meta") or {}
    widget_ids = set(old_meta.keys()) | set(new_meta.keys())
    for widget_id in widget_ids:
        before = old_meta.get(widget_id) or {}
        after = new_meta.get(widget_id) or {}
        if before == after:
            continue
        DashboardLayoutAudit.objects.create(
            user=user,
            widget_id=widget_id,
            action="widget_meta",
            summary=f"Updated widget {widget_id} metadata",
            details={"before": before, "after": after},
        )

    setting_keys = {"show_sidebar", "tile_variant", "sidebar_items", "custom_links"}
    if any(old_settings.get(key) != new_settings.get(key) for key in setting_keys):
        DashboardLayoutAudit.objects.create(
            user=user,
            action="settings",
            summary="Dashboard layout settings updated",
            details={
                "before": {key: old_settings.get(key) for key in setting_keys},
                "after": {key: new_settings.get(key) for key in setting_keys},
            },
        )


def _normalize_dashboard_settings(settings: dict) -> dict:
    sidebar_items = []
    for item in settings.get("sidebar_items") or []:
        value = str(item).strip()
        if value:
            sidebar_items.append(value)
    return {
        "show_sidebar": bool(settings.get("show_sidebar")),
        "sidebar_items": sidebar_items,
        "tile_variant": str(settings.get("tile_variant") or "default"),
        "custom_links": settings.get("custom_links") or [],
        "widget_meta": settings.get("widget_meta") or {},
    }


def _create_layout_from_legacy(user, page: str) -> DashboardLayout | None:
    if not user or not user.is_authenticated:
        return None

    try:
        preferences, _ = DashboardUserPreference.objects.get_or_create(user=user)
    except DatabaseError:
        return None

    legacy_layout = preferences.dashboard_layout or {}
    if not isinstance(legacy_layout, dict) or not legacy_layout:
        return None

    payload = {
        "items": [],
        "__settings__": {"legacy_layout": legacy_layout, "migrated_page": page},
    }
    layout_obj, created = DashboardLayout.objects.get_or_create(
        user=user,
        page=page,
        defaults={
            "role": (getattr(user, "role", "") or "").upper(),
            "layout": payload,
            "is_default": False,
        },
    )
    if created:
        preferences.dashboard_layout = {}
        preferences.save(update_fields=["dashboard_layout", "updated_at"])
    return layout_obj


def get_layout_for_page(user, page: str) -> DashboardLayout | None:
    """
    Single source for layout resolution: user override -> role default -> legacy migration.
    Use from both the dashboard layout API (GET) and load_dashboard_layout_settings().
    """
    if not user or not user.is_authenticated:
        return None
    layout_obj = DashboardLayout.objects.filter(user=user, page=page).first()
    if not layout_obj:
        role = (getattr(user, "role", "") or "").upper()
        layout_obj = DashboardLayout.objects.filter(page=page, role=role, is_default=True).first()
    if not layout_obj:
        layout_obj = _create_layout_from_legacy(user, page)
    return layout_obj


def load_dashboard_layout_settings(user, page: str) -> dict:
    """Return the latest dashboard meta settings (user override -> role default)."""
    layout_obj = get_layout_for_page(user, page)
    raw_settings = {}
    if layout_obj and isinstance(layout_obj.layout, dict):
        raw_settings = layout_obj.layout.get("__settings__", {}) or {}
    return _normalize_dashboard_settings(raw_settings)


@login_required
@require_http_methods(["POST"])
def update_theme(request):
    """Update user theme preference."""
    if not _can_customize(request.user):
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)
    
    try:
        data = json.loads(request.body)
        theme = (data.get("theme") or "system").lower()
        
        allowed = {"system", "light", "dark", "classic", "high_contrast"}
        if theme not in allowed:
            return JsonResponse({"success": False, "error": "Invalid theme"}, status=400)
        
        preferences, _ = DashboardUserPreference.objects.get_or_create(user=request.user)
        preferences.theme_preference = theme
        preferences.save()
        logger.info("User %s set theme preference to %s", request.user.username, theme)
        
        return JsonResponse({"success": True, "theme": theme})
    
    except Exception as e:
        logger.exception("Failed to update theme preference for %s", request.user.username)
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def update_accessibility_preferences(request):
    """Update accessibility settings."""
    if not _can_customize(request.user):
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)
    
    try:
        data = json.loads(request.body)
        
        preferences, _ = DashboardUserPreference.objects.get_or_create(user=request.user)
        preferences.high_contrast = data.get('high_contrast', preferences.high_contrast)
        preferences.reduced_motion = data.get('reduced_motion', preferences.reduced_motion)
        preferences.font_size = data.get('font_size', preferences.font_size)
        preferences.save()
        
        return JsonResponse({
            'success': True,
            'settings': {
                'high_contrast': preferences.high_contrast,
                'reduced_motion': preferences.reduced_motion,
                'font_size': preferences.font_size,
            }
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

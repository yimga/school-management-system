"""
Utilities supporting dashboard customization workflows.
"""
import logging
import json
from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

from apps.accounts.utils import get_user_role
from apps.platform_runtime.helpers import get_effective_site_settings
from apps.siteconfig.models_dashboard import (
    DashboardLayout,
    DashboardLayoutAudit,
    DashboardUserPreference,
)

logger = logging.getLogger(__name__)

# Roles that can use full drag-and-drop layout customization.
ALLOWED_CUSTOM_ROLES = {
    "ADMIN",
    "LEADERSHIP",
    "IT_ADMIN",
    "TEACHER",
}

# Roles that can use light customization (hide widgets only, no drag).
ALLOWED_LIGHT_CUSTOM_ROLES = {
    "PARENT",
}


def _school_for_user(user):
    if not user or not getattr(user, "is_authenticated", False):
        return None
    teacher_profile = getattr(user, "teacher_profile", None)
    if teacher_profile and getattr(teacher_profile, "school", None):
        return teacher_profile.school
    student_link = getattr(user, "guardian_links", None)
    if student_link is not None:
        link = student_link.select_related("student__school").first()
        if link and getattr(link.student, "school", None):
            return link.student.school
    return None


def _default_sidebar_collapsed(*, request=None, user=None) -> bool:
    school = getattr(request, "school", None) if request is not None else _school_for_user(user)
    site = get_effective_site_settings(request=request, school=school)
    return bool(getattr(site, "default_sidebar_collapsed", False))


def _can_customize(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    role = get_user_role(user)
    return bool(user.is_staff or user.is_superuser or role in ALLOWED_CUSTOM_ROLES)


def _can_light_customize(user) -> bool:
    """Light mode: hide/restore widgets only (no drag). Used for parent dashboard."""
    if not user or not user.is_authenticated:
        return False
    role = get_user_role(user)
    return bool(role in ALLOWED_LIGHT_CUSTOM_ROLES or _can_customize(user))


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
    hidden = settings.get("hidden_widget_ids") or []
    if not isinstance(hidden, list):
        hidden = []
    hidden_widget_ids = [str(x).strip() for x in hidden if str(x).strip()]

    pinned = settings.get("pinned_widgets") or []
    if not isinstance(pinned, list):
        pinned = []
    pinned_widgets = []
    for p in pinned:
        if isinstance(p, dict) and p.get("widget_id"):
            pages = p.get("pages") or []
            if isinstance(pages, list):
                pinned_widgets.append({"widget_id": str(p["widget_id"]), "pages": [str(x) for x in pages]})

    return {
        "show_sidebar": bool(settings.get("show_sidebar")),
        "sidebar_items": sidebar_items,
        "tile_variant": str(settings.get("tile_variant") or "default"),
        "custom_links": settings.get("custom_links") or [],
        "widget_meta": settings.get("widget_meta") or {},
        "hidden_widget_ids": hidden_widget_ids,
        "pinned_widgets": pinned_widgets,
    }


def _create_layout_from_legacy(user, page: str) -> DashboardLayout | None:
    if not user or not user.is_authenticated:
        return None

    try:
        preferences, _ = DashboardUserPreference.objects.get_or_create(
            user=user,
            defaults={"sidebar_collapsed": _default_sidebar_collapsed(user=user)},
        )
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
            "role": get_user_role(user),
            "layout": payload,
            "is_default": False,
        },
    )
    if created:
        preferences.dashboard_layout = {}
        preferences.save(update_fields=["dashboard_layout", "updated_at"])
    return layout_obj


def get_layout_for_page(user, page: str):
    """
    Return the effective DashboardLayout for (user, page).
    Resolution order: user-specific, then role default, then legacy migration.
    Used by load_dashboard_layout_settings and the dashboard layout API.
    """
    if not user or not user.is_authenticated:
        return None
    page = (page or "").strip().lower()
    if not page:
        return None
    layout_obj = DashboardLayout.objects.filter(user=user, page=page).first()
    if not layout_obj:
        role = get_user_role(user)
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


def effective_chart_types(user, page: str) -> dict:
    """
    Return widget_id -> chart_type for chart widgets.
    Merges user's widget_meta.chart_type override with DashboardWidget default.
    RBAC: respects _can_customize; uses layout for allowed users.
    """
    from apps.siteconfig.models_dashboard import DashboardWidget
    page = (page or "").strip().lower()
    chart_widgets = DashboardWidget.objects.filter(
        page=page, widget_type="chart", is_active=True
    )
    result = {}
    user_meta = {}
    if user and user.is_authenticated:
        layout_obj = get_layout_for_page(user, page)
        if layout_obj and isinstance(layout_obj.layout, dict):
            settings = layout_obj.layout.get("__settings__", {}) or {}
            user_meta = settings.get("widget_meta") or {}
    for w in chart_widgets:
        override = (user_meta.get(w.id) or {}).get("chart_type")
        default = (w.chart_type or "").strip()
        ct = (override or default or "").strip().lower()
        if ct:
            result[w.id] = ct
    return result


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
        
        preferences, _ = DashboardUserPreference.objects.get_or_create(
            user=request.user,
            defaults={"sidebar_collapsed": _default_sidebar_collapsed(request=request, user=request.user)},
        )
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
        
        preferences, _ = DashboardUserPreference.objects.get_or_create(
            user=request.user,
            defaults={"sidebar_collapsed": _default_sidebar_collapsed(request=request, user=request.user)},
        )
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

import json
import os
from django.db import DatabaseError, connection, transaction
from .models_support import (
    build_platform_default_site_settings,
    default_header_weather_config,
)
from .translations import TranslationManager, SUPPORTED_LANGUAGES
from .models_dashboard import DashboardUserPreference
from django.core.files.storage import default_storage
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse
from django.utils import translation
from django.utils.translation import gettext as _
from apps.accounts.models import User
from apps.finance.models import Notification
from apps.global_registries.models import RegionConfig
from apps.platform_runtime.helpers import get_platform_defaults
from apps.siteconfig.config_service import (
    get_effective_flags,
    get_effective_site_settings,
)
from .preview_state import ACT_AS_ROLE_SESSION_KEY
from .portal_sidebar_items import build_portal_sidebar_items
from apps.policies.policy_registry import get_effective_policy

OPTIONAL_CONTEXT_ERRORS = (
    AttributeError,
    DatabaseError,
    ImportError,
    NoReverseMatch,
    RuntimeError,
    TypeError,
    ValueError,
)
OPTIONAL_STORAGE_ERRORS = (AttributeError, OSError, RuntimeError, TypeError, ValueError)

_LEGACY_MISSING_PLATFORM_LOGO_FRAGMENTS = (
    "runmycampus-logo-mark.png",
    "runmycampus-logo-lockup.png",
    "runmycampus-icon.png",
)
_PLATFORM_LOGO_MARK_STATIC = "images/brand/runmycampus-logo-mark.svg"
_PLATFORM_FAVICON_STATIC = "images/runmycampus-icon-bell.svg"


def _resolve_public_brand_logo_url(url: str, *, default_static: str) -> str:
    """Remap env/DB URLs that still point at PNG assets removed from the tree."""
    candidate = (url or "").strip()
    if candidate and not any(
        fragment in candidate for fragment in _LEGACY_MISSING_PLATFORM_LOGO_FRAGMENTS
    ):
        return candidate
    return static(default_static)


def _safe_site_attr(site, name: str, default=None):
    """Phase B: slim tenant settings row — virtual keys use __getattr__ and may raise AttributeError."""
    try:
        return getattr(site, name)
    except AttributeError:
        return default


def _get_portal_sidebar_items(request, site):
    """Return portal sidebar items (optionally sorted by portal_sidebar_order)."""
    try:
        return build_portal_sidebar_items(request, site)
    except OPTIONAL_CONTEXT_ERRORS as e:
        from apps.platform_runtime.structured_logging import (
            log_exception_with_context,
            request_context_for_log,
        )

        ctx = request_context_for_log(request) if request else {}
        log_exception_with_context(
            "portal_sidebar_items_fallback",
            tenant_id=ctx.get("tenant_id"),
            school_id=ctx.get("school_id"),
            actor_id=ctx.get("actor_id"),
            route=ctx.get("route"),
            exc_info=False,
            extra={"error": str(e)[:200]},
        )
        return []


def _get_pinned_sidebar_items(request, all_items):
    """
    Return list of sidebar items that the user pinned (Quick access), and set of pinned ids.
    all_items: list of dicts with id, label, url, icon, section, badge.
    """
    if (
        not request
        or not getattr(request, "user", None)
        or not request.user.is_authenticated
        or not all_items
    ):
        return [], set()
    try:
        prefs = getattr(request.user, "dashboard_preferences", None)
        by_id = {str(item.get("id")): item for item in all_items if item.get("id")}
        prefs_created = False
        if not prefs:
            try:
                prefs, prefs_created = DashboardUserPreference.objects.get_or_create(
                    user=request.user
                )
            except DatabaseError:
                prefs = None

        raw_pinned_ids = (
            getattr(prefs, "pinned_sidebar_items", None) if prefs is not None else None
        )
        pinned_ids = list(raw_pinned_ids or [])
        # Seed defaults only for first-time preferences (or legacy null state), not when users intentionally unpin all.
        if not pinned_ids and (prefs_created or raw_pinned_ids is None):
            try:
                from apps.accounts.portal_roles import get_effective_portal_role

                role = (
                    get_effective_portal_role(request)
                    or getattr(request.user, "role", "")
                    or ""
                ).upper()
            except OPTIONAL_CONTEXT_ERRORS:
                role = (getattr(request.user, "role", "") or "").upper()
            default_pin_map = {
                "TEACHER": ["teacher_workflow", "preferences"],
                "PARENT": ["parent_workflow", "preferences"],
            }
            seeded_pins = [
                item_id
                for item_id in default_pin_map.get(role, [])
                if item_id in by_id and by_id[item_id].get("url")
            ]
            if seeded_pins:
                pinned_ids = seeded_pins
                if prefs is not None:
                    try:
                        prefs.pinned_sidebar_items = seeded_pins
                        prefs.save(update_fields=["pinned_sidebar_items", "updated_at"])
                    except (DatabaseError, TypeError, ValueError):
                        pass
        if not pinned_ids:
            return [], set()
        ordered = []
        for pid in pinned_ids:
            if pid in by_id and by_id[pid].get("url"):
                ordered.append(by_id[pid])
        return ordered, set(str(item.get("id")) for item in ordered)
    except OPTIONAL_CONTEXT_ERRORS:
        return [], set()


SESSION_KEY = "site_preview_settings"

BREADCRUMB_LABELS = {
    "admissions": "Admissions",
    "application-status": "Application Status",
    "student-portal": "Student Portal",
    "grades": "Grades",
    "parent": "Parent Portal",
    "portal": "Portal",
    "finance": "Finance",
    "payments": "Payments",
    "receipts": "Receipts",
    "payroll": "Payroll",
    "reports": "Reports",
    "siteconfig": "Site Settings",
    "customizer": "Studio",
    "preferences": "Preferences",
    "reports": "Reports",
    "reports/download": "Download",
    "analytics": "Analytics",
}


def _reset_db_state() -> None:
    """Reset a broken transaction after a handled DB error."""
    try:
        if connection.in_atomic_block:
            transaction.set_rollback(False)
        else:
            connection.rollback()
    except (DatabaseError, RuntimeError):
        pass


def _request_school(request):
    """
    Return tenant school only when middleware explicitly set it.

    Using request.__dict__ avoids Mock auto-attribute behavior in tests where
    getattr(request, "school", None) can yield a MagicMock.
    """
    data = getattr(request, "__dict__", {}) or {}
    return data.get("school")


def _build_breadcrumbs(request_path: str) -> list[dict[str, str]]:
    segments = [
        segment
        for segment in request_path.strip("/").split("/")
        if segment and segment not in {"static", "media", "favicon.ico"}
    ]

    breadcrumbs = [{"label": "Home", "url": "/"}]
    if not segments:
        return breadcrumbs

    prefix = ""
    for index, segment in enumerate(segments, start=1):
        prefix += f"/{segment}"
        label = BREADCRUMB_LABELS.get(
            segment, segment.replace("_", " ").replace("-", " ").title()
        )

        breadcrumbs.append(
            {
                "label": label,
                "url": prefix,
                "active": index == len(segments),
            }
        )

    return breadcrumbs


def _resolve_media_url(file_field, fallback: str | None = None) -> str:
    if not file_field:
        return static(fallback) if fallback else ""

    name = getattr(file_field, "name", "")
    if not name:
        return static(fallback) if fallback else ""

    try:
        if default_storage.exists(name):
            return file_field.url
    except OPTIONAL_STORAGE_ERRORS:
        pass

    return static(fallback) if fallback else ""


def _resolve_backend_feature_flags(request, site) -> dict:
    """Resolve backend feature flags through runtime first, then legacy site fallback."""
    try:
        flags = get_effective_flags(request)
        if isinstance(flags, dict):
            return flags
    except OPTIONAL_CONTEXT_ERRORS:
        pass
    if callable(getattr(site, "get_backend_feature_flags", None)):
        return site.get_backend_feature_flags()
    fallback_flags = getattr(site, "backend_feature_flags", None) or {}
    return dict(fallback_flags) if isinstance(fallback_flags, dict) else {}


def site_settings(request):
    """
    Provides SITE to all templates.
    If preview settings exist in session, use them (draft preview).
    Otherwise use DB singleton.
    """
    if connection.needs_rollback:
        _reset_db_state()
    try:
        site = get_effective_site_settings(request=request)
        if site is None:
            site = build_platform_default_site_settings()
    except DatabaseError:
        _reset_db_state()
        site = build_platform_default_site_settings()

    session = getattr(request, "session", None)
    preview_settings = session.get(SESSION_KEY) if session else None
    # §5.6 Before/after: studio_compare=current forces saved state (no session overlay) for side-by-side compare
    if request.GET.get("studio_compare") == "current":
        preview_settings = None
    preview_config = (
        site.get_preview_platform_config()
        if callable(getattr(site, "get_preview_platform_config", None))
        else {
            "preview_mode_enabled": getattr(site, "preview_mode_enabled", False),
            "preview_note": getattr(site, "preview_note", ""),
            "preview_toggle_enabled": getattr(site, "preview_toggle_enabled", True),
            "preview_toggle_label": getattr(
                site, "preview_toggle_label", "Toggle preview"
            ),
            "preview_banner_text": getattr(site, "preview_banner_text", ""),
        }
    )
    preview_mode_enabled = getattr(request, "preview_mode_enabled", False) or bool(
        preview_config.get("preview_mode_enabled", False)
    )
    preview_flag = bool(preview_settings) or preview_mode_enabled

    if preview_settings:
        for key, value in preview_settings.items():
            if (
                key
                in {
                    "admin_theme_pack",
                    "theme_pack",
                    "teacher_theme_pack",
                    "parent_theme_pack",
                }
                and value is not None
            ):
                id_attr = f"{key}_id"
                if hasattr(site, id_attr):
                    try:
                        setattr(site, id_attr, int(value))
                    except (TypeError, ValueError):
                        pass
            elif hasattr(site, key):
                setattr(site, key, value)

    act_as_role = session.get(ACT_AS_ROLE_SESSION_KEY) if session else None
    act_as_choices = [
        {"value": code, "label": label} for code, label in User.Role.choices
    ]
    setattr(site, "is_preview", preview_flag)

    breadcrumbs = _build_breadcrumbs(request.path)
    # Use theme pack backgrounds if set, else site settings
    logo_url = _resolve_media_url(site.get_theme_background("logo"), "images/logo.png")
    # v2 carried-forward (2026-05-12): companion dark-theme logo. RuntimeDefaults
    # `site_logo_dark_url` is the platform default; tenant override (BrandProfile
    # .logo_dark_url) is applied lower down once `school` is known.
    logo_dark_url = getattr(site, "site_logo_dark_url", "") or ""
    background_url = _resolve_media_url(site.get_theme_background("background_image"))

    try:
        portal_home_url = reverse("portal:home")
    except NoReverseMatch:
        portal_home_url = "/"

    # User preference override
    show_background_logo = True
    logo_opacity = site.get_theme_logo_opacity()
    high_contrast_mode = False
    reduced_motion = False
    theme_pref = "system"
    sidebar_collapsed = False
    user_visual_preset = "soft-glass"
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        try:
            if hasattr(user, "preference"):
                pref = user.preference
                show_background_logo = pref.show_background_logo
                if pref.background_logo_opacity is not None:
                    logo_opacity = pref.background_logo_opacity
                high_contrast_mode = getattr(pref, "high_contrast_mode", False)
                reduced_motion = getattr(pref, "reduced_motion", False)
        except DatabaseError:
            _reset_db_state()
            pass
        try:
            default_collapsed = getattr(site, "default_sidebar_collapsed", False)
            dashboard_pref, _created = DashboardUserPreference.objects.get_or_create(
                user=user,
                defaults={"sidebar_collapsed": default_collapsed},
            )
            theme_pref = (dashboard_pref.theme_preference or "system").lower()
            high_contrast_mode = high_contrast_mode or bool(
                getattr(dashboard_pref, "high_contrast", False)
            )
            reduced_motion = reduced_motion or bool(
                getattr(dashboard_pref, "reduced_motion", False)
            )
            sidebar_collapsed = bool(
                getattr(dashboard_pref, "sidebar_collapsed", False)
            )
            user_visual_preset = dashboard_pref.get_visual_preset(
                getattr(user, "role", None)
            )
        except DatabaseError:
            _reset_db_state()
            theme_pref = "system"
        except (AttributeError, TypeError, ValueError):
            # Keep context resilient if dashboard preference schema is mid-migration.
            user_visual_preset = "soft-glass"

    video_bg_url = _resolve_media_url(site.get_theme_background("video_background"))
    svg_bg_url = _resolve_media_url(site.get_theme_background("svg_background"))
    try:
        finance_request_url = reverse("requests:dashboard")
    except NoReverseMatch:
        finance_request_url = "/requests/"
    finance_request_alerts = 0
    notifications_unread_count = 0
    if user and getattr(user, "is_authenticated", False) and getattr(user, "pk", None):
        finance_request_alerts = Notification.objects.filter(
            recipient=user,
            title__icontains="finance access request",
            is_read=False,
        ).count()
        notifications_unread_count = Notification.objects.filter(
            recipient=user,
            is_read=False,
        ).count()
    feature_flags = _resolve_backend_feature_flags(request, site)
    admin_theme = site.get_admin_theme()
    use_site_primary_for_admin = bool(getattr(site, "admin_use_site_primary", False))
    admin_background_url = _resolve_media_url(
        admin_theme.background_image if admin_theme else None
    )
    admin_logo = _resolve_media_url(
        admin_theme.logo if admin_theme else None, "images/logo.png"
    )
    favicon_url = _resolve_media_url(getattr(site, "favicon", None), "favicon.ico")
    sidebar_icon_url = _resolve_media_url(getattr(site, "sidebar_icon", None))
    # Resolved admin theme: optionally force primary/accent from site-level colors.
    if use_site_primary_for_admin:
        admin_primary = (
            getattr(site, "primary_color", None)
            or (admin_theme.primary_color if admin_theme else None)
            or "#0d6efd"
        )
        admin_accent = (
            getattr(site, "accent_color", None)
            or (admin_theme.accent_color if admin_theme else None)
            or "#198754"
        )
    else:
        admin_primary = (
            admin_theme.primary_color
            if admin_theme
            else getattr(site, "primary_color", None)
        ) or "#0d6efd"
        admin_accent = (
            admin_theme.accent_color
            if admin_theme
            else getattr(site, "accent_color", None)
        ) or "#198754"
    admin_background = (
        getattr(admin_theme, "background_color", None) if admin_theme else None
    )
    admin_background = admin_background or "#1a1a1a"
    admin_success = getattr(site, "success_color", None) or "#22c55e"
    admin_warning = getattr(site, "warning_color", None) or "#fbbf24"
    admin_danger = getattr(site, "danger_color", None) or "#ef4444"
    # Superadmin-only: when in /admin/ on manager host, use platform branding (gold) so admin matches high-end login.
    path = (getattr(request, "path", "") or "").strip()
    if (
        path.startswith("/admin/")
        and getattr(request, "public_host_kind", None) == "manager"
    ):
        admin_primary = "#d4af37"
        admin_accent = "#0d6efd"
    # Backend console theme: pack overrides site when set (ThemePack.backend_console_theme)
    _pack_console = getattr(admin_theme, "backend_console_theme", None) or ""
    resolved_backend_console_theme = (
        _pack_console.strip() or getattr(site, "backend_console_theme", None) or "dark"
    )
    can_manage_settings = False
    if user and getattr(user, "is_authenticated", False) and getattr(user, "pk", None):
        can_manage_settings = bool(
            getattr(user, "is_superuser", False)
            or getattr(user, "has_feature_permission", lambda _code: False)(
                "settings.manage"
            )
        )

    is_backend_context = (
        request.path.startswith("/backend") or "/authentication/backend" in request.path
    )
    # Cache portal "hat" checks before building sidebar (so get_effective_portal_role can use them)
    effective_portal_role = None
    if user and getattr(user, "is_authenticated", False) and getattr(user, "pk", None):
        try:
            from apps.accounts.portal_roles import (
                has_teacher_hat,
                has_parent_hat,
                get_effective_portal_role,
            )

            request._portal_teacher_hat = has_teacher_hat(user)
            request._portal_parent_hat = has_parent_hat(user)
            effective_portal_role = get_effective_portal_role(request)
        except OPTIONAL_CONTEXT_ERRORS:
            request._portal_teacher_hat = False
            request._portal_parent_hat = False
    _get_theme = getattr(site, "get_portal_theme", None)
    site_theme = (
        _get_theme(user=user, effective_role=effective_portal_role)
        if callable(_get_theme)
        else None
    )
    # W3-5: Per-tenant theme pack — when school has theme_pack set, use it for portal theme
    school = getattr(request, "school", None)
    if school and getattr(school, "theme_pack_id", None):
        try:
            from apps.brand_experience.models import ThemePack

            school_pack = ThemePack.objects.filter(
                pk=school.theme_pack_id, is_active=True
            ).first()
            if school_pack:
                site_theme = school_pack
        except OPTIONAL_CONTEXT_ERRORS:
            pass
    weather_defaults = default_header_weather_config()
    ctx = {
        "SITE": site,
        "SITE_SETTINGS": site,
        "is_backend_context": is_backend_context,
        "SITE_THEME": site_theme,
        "SITE_ADMIN_THEME": admin_theme,
        "ADMIN_RESOLVED_PRIMARY": admin_primary,
        "ADMIN_RESOLVED_ACCENT": admin_accent,
        "ADMIN_RESOLVED_BACKGROUND": admin_background,
        "ADMIN_RESOLVED_SUCCESS": admin_success,
        "ADMIN_RESOLVED_WARNING": admin_warning,
        "ADMIN_RESOLVED_DANGER": admin_danger,
        "RESOLVED_BACKEND_CONSOLE_THEME": resolved_backend_console_theme,
        "SITE_ADMIN_BACKGROUND_URL": admin_background_url,
        "SITE_ADMIN_LOGO_URL": admin_logo,
        "SITE_FAVICON_URL": favicon_url,
        "SITE_SIDEBAR_ICON_URL": sidebar_icon_url,
        "LAYOUT_STYLE": getattr(site, "layout_style", "fluid") or "fluid",
        "SHOW_HEADER_SEARCH": getattr(site, "show_header_search", True),
        "SHOW_HEADER_NOTIFICATIONS": getattr(site, "show_header_notifications", True),
        "SHOW_HEADER_PROFILE_MENU": getattr(site, "show_header_profile_menu", True),
        # SHOW_HEADER_THEME_TOGGLE retired 2026-05-12 — theme switching now lives
        # inside user_dropdown.html (Light/Dark/System segmented control). The
        # standalone topbar themeToggle button was removed in the same pass.
        "SHOW_HEADER_CONTEXT_STRIP": bool(
            feature_flags.get("show_header_context_strip", True)
        ),
        "SHOW_HEADER_CONTEXT_DATETIME": bool(
            feature_flags.get("show_header_context_datetime", True)
        ),
        "SHOW_HEADER_CONTEXT_WEATHER": bool(
            feature_flags.get("show_header_context_weather", False)
        ),
        "SHOW_HEADER_CONTEXT_QUOTE": bool(
            feature_flags.get("show_header_context_quote", True)
        ),
        "HEADER_WEATHER_LATITUDE": feature_flags.get(
            "header_weather_latitude", weather_defaults["header_weather_latitude"]
        ),
        "HEADER_WEATHER_LONGITUDE": feature_flags.get(
            "header_weather_longitude", weather_defaults["header_weather_longitude"]
        ),
        "HEADER_WEATHER_TEMPERATURE_UNIT": str(
            feature_flags.get(
                "header_weather_temperature_unit",
                weather_defaults["header_weather_temperature_unit"],
            )
        ).lower(),
        "HEADER_WEATHER_LABEL": feature_flags.get(
            "header_weather_label", weather_defaults["header_weather_label"]
        ),
        "SITE_BRANDED_DOMAIN": getattr(site, "branded_domain", "") or "",
        "SITE_SECONDARY_FONT": getattr(site, "secondary_font", "") or "",
        "SITE_USE_SECONDARY_FONT_HEADINGS": getattr(
            site, "use_secondary_font_for_headings", False
        ),
        "SITE_BASE_FONT_SIZE": getattr(site, "base_font_size", None),
        "REPORT_DOWNLOADS_ENABLED": bool(
            _safe_site_attr(site, "report_downloads_enabled", True)
        ),
        "BREADCRUMBS": breadcrumbs,
        "SITE_LOGO_URL": logo_url,
        "SITE_LOGO_DARK_URL": logo_dark_url,
        "SITE_BACKGROUND_URL": background_url,
        "SITE_VIDEO_BG_URL": video_bg_url,
        "SITE_SVG_BG_URL": svg_bg_url,
        "SITE_LOGO_OPACITY": logo_opacity,
        "SHOW_BACKGROUND_LOGO": show_background_logo,
        "SITE_LOGO_BG_MODE": site.get_theme_logo_bg_mode(),
        "HIGH_CONTRAST_MODE": high_contrast_mode,
        "REDUCED_MOTION": reduced_motion,
        "USER_THEME_PREFERENCE": theme_pref,
        "USER_DASHBOARD_VISUAL_PRESET": user_visual_preset,
        "portal_home_url": portal_home_url,
        "PREVIEW_ACT_AS_ROLE": act_as_role,
        "PREVIEW_ACT_AS_CHOICES": act_as_choices,
        "PREVIEW_NOTE": str(preview_config.get("preview_note", "") or ""),
        "PREVIEW_MODE_ENABLED": preview_flag,
        "PREVIEW_TOGGLE_ENABLED": bool(
            preview_config.get("preview_toggle_enabled", True)
        ),
        "PREVIEW_TOGGLE_LABEL": str(
            preview_config.get("preview_toggle_label", "Toggle preview")
            or "Toggle preview"
        ),
        "PREVIEW_BANNER_TEXT": str(preview_config.get("preview_banner_text", "") or ""),
        "FINANCE_REQUEST_ALERT_COUNT": finance_request_alerts,
        "FINANCE_REQUEST_LINK": finance_request_url,
        "NOTIFICATIONS_UNREAD_COUNT": notifications_unread_count,
        "SIDEBAR_COLLAPSED": sidebar_collapsed,
        "CAN_MANAGE_SETTINGS": can_manage_settings,
        "PORTAL_SIDEBAR_ITEMS": _get_portal_sidebar_items(request, site),
    }
    try:
        ctx["PORTAL_DOCUMENT_LIBRARY_MANAGE_URL"] = reverse(
            "portal:document_library_manage"
        )
    except NoReverseMatch:
        ctx["PORTAL_DOCUMENT_LIBRARY_MANAGE_URL"] = None
    # Dual-role (Teacher + Parent): show role switcher when user has both hats (cache already set above)
    if user and getattr(user, "is_authenticated", False):
        try:
            from apps.accounts.portal_roles import get_effective_portal_role

            has_teacher = getattr(request, "_portal_teacher_hat", False)
            has_parent = getattr(request, "_portal_parent_hat", False)
            ctx["SHOW_ROLE_SWITCHER"] = has_teacher and has_parent
            ctx["EFFECTIVE_PORTAL_ROLE"] = (
                get_effective_portal_role(request)
                or (getattr(user, "role", "") or "").upper()
            )
            ctx["HAS_TEACHER_HAT"] = has_teacher
            ctx["HAS_PARENT_HAT"] = has_parent
        except OPTIONAL_CONTEXT_ERRORS:
            ctx["SHOW_ROLE_SWITCHER"] = False
            ctx["EFFECTIVE_PORTAL_ROLE"] = (getattr(user, "role", "") or "").upper()
            ctx["HAS_TEACHER_HAT"] = False
            ctx["HAS_PARENT_HAT"] = False
    else:
        ctx["SHOW_ROLE_SWITCHER"] = False
        ctx["EFFECTIVE_PORTAL_ROLE"] = ""
        ctx["HAS_TEACHER_HAT"] = False
        ctx["HAS_PARENT_HAT"] = False
    # Multi-tenant: when request.school is set, use school branding for logo and colors (Phase 2).
    school = _request_school(request)
    if school:
        try:
            from .branding import brand_css_vars, resolve_brand_profile

            tenant_brand = resolve_brand_profile(school=school, site=site)
        except OPTIONAL_CONTEXT_ERRORS:
            tenant_brand = {}
        if tenant_brand.get("logo_url"):
            ctx["SITE_LOGO_URL"] = tenant_brand.get("logo_url")
        if tenant_brand.get("logo_dark_url"):
            ctx["SITE_LOGO_DARK_URL"] = tenant_brand.get("logo_dark_url")
        if tenant_brand.get("favicon_url"):
            ctx["SITE_FAVICON_URL"] = tenant_brand.get("favicon_url")
        ctx["SITE_PRIMARY_COLOR"] = tenant_brand.get("primary_color") or "#0d6efd"
        ctx["SITE_ACCENT_COLOR"] = tenant_brand.get("accent_color") or "#198754"
        ctx["TENANT_WALLPAPER_URL"] = (
            tenant_brand.get("login_background_url")
            or getattr(school, "wallpaper_url", None)
            or ""
        )
        # Tenant-specific login placeholder e.g. "Riverfront Arts College" or "School Email"
        ctx["LOGIN_EMAIL_PLACEHOLDER"] = (
            getattr(school, "name", None) or ""
        ).strip() or _("School Email")
        # Phase A: useLocalSettings — merged timezone, locale, currency, date_format, grading_scale for templates
        try:
            from .tenant_config import use_local_settings

            ctx["TENANT_LOCALE"] = use_local_settings(request=request, school=school)
        except OPTIONAL_CONTEXT_ERRORS:
            ctx["TENANT_LOCALE"] = {}
        try:
            from .brand_registry import resolve_global_brand_context

            brand_ctx = resolve_global_brand_context(
                school=school,
                language_code=(ctx.get("TENANT_LOCALE") or {}).get("locale"),
            )
        except OPTIONAL_CONTEXT_ERRORS:
            brand_ctx = {}
        ctx["TENANT_BRAND_CONTEXT"] = brand_ctx
        ctx["TENANT_LABELS"] = (
            (ctx.get("TENANT_LOCALE") or {}).get("labels_map")
            or brand_ctx.get("labels_map")
            or {}
        )
        # World Engine: tenant branding_metadata → --primary, --accent (and optional --school-font) for <head> injection.
        ctx["TENANT_BRAND_PROFILE"] = tenant_brand
        ctx["TENANT_BRANDING_CSS_VARS"] = (
            brand_css_vars(tenant_brand) if tenant_brand else ""
        )
    else:
        ctx["SITE_PRIMARY_COLOR"] = None
        ctx["SITE_ACCENT_COLOR"] = None
        ctx["TENANT_WALLPAPER_URL"] = ""
        ctx["LOGIN_EMAIL_PLACEHOLDER"] = _("School Email")
        ctx["TENANT_LOCALE"] = {}
        ctx["TENANT_BRAND_CONTEXT"] = {}
        ctx["TENANT_LABELS"] = {}
        ctx["TENANT_BRAND_PROFILE"] = {}
        ctx["TENANT_BRANDING_CSS_VARS"] = ""
    # Plan §7: Tenant portal = Light Mode by default (195-country; enforce light, no tenant dark by default).
    ctx["TENANT_FORCE_LIGHT_THEME"] = bool(school)
    public_host_kind = getattr(request, "public_host_kind", None)
    public_brand_mode = (
        public_host_kind in {"base", "verify", "support", "manager"}
    ) and not school
    ctx["PUBLIC_BRAND_MODE"] = public_brand_mode
    path = (request.path or "").strip()
    ctx["CONTROL_PLANE_SHELL"] = public_host_kind == "manager"
    user = getattr(request, "user", None)
    is_authenticated = bool(user and getattr(user, "is_authenticated", False))
    ctx["SHOW_CORPORATE_MARKETING_FOOTER"] = (
        public_host_kind == "manager" and not school and not is_authenticated
    )
    ctx["MANAGER_PLATFORM_ADMIN_SHELL"] = False
    ctx["MANAGER_PLATFORM_ADMIN_NAV"] = {"quick_links": []}
    if ctx["CONTROL_PLANE_SHELL"]:
        try:
            from apps.schools.control_plane_nav import (
                build_control_plane_nav,
                build_primary_control_plane_nav,
            )

            ctx["CONTROL_PLANE_NAV"] = build_control_plane_nav(request)
            ctx["PRIMARY_CONTROL_PLANE_NAV"] = build_primary_control_plane_nav(request)
            # Phase 8: Pinned control plane items (Quick access)
            pinned_cp_ids = []
            try:
                prefs = (
                    DashboardUserPreference.objects.filter(user=request.user)
                    .only("control_plane_pinned_items")
                    .first()
                )
                if prefs and isinstance(prefs.control_plane_pinned_items, list):
                    pinned_cp_ids = [
                        str(x).strip()
                        for x in prefs.control_plane_pinned_items
                        if str(x).strip()
                    ]
            except (DatabaseError, ImportError, TypeError, ValueError):
                pass
            by_id = {}
            for grp in ctx["CONTROL_PLANE_NAV"]:
                for it in grp.get("items") or []:
                    iid = it.get("id")
                    if iid and it.get("url"):
                        by_id[iid] = it
            ctx["PINNED_CONTROL_PLANE_ITEMS"] = [
                by_id[pid] for pid in pinned_cp_ids if pid in by_id
            ]
            ctx["PINNED_CONTROL_PLANE_IDS"] = set(pinned_cp_ids)
            try:
                from apps.schools.control_plane_nav import (
                    build_manager_platform_admin_nav,
                    build_studio_focus_sidebar,
                    is_manager_platform_admin_path,
                    is_manager_studio_focus_path,
                )

                ctx["STUDIO_FOCUS_SHELL"] = is_manager_studio_focus_path(path)
                ctx["STUDIO_FOCUS_SIDEBAR"] = (
                    build_studio_focus_sidebar(request)
                    if ctx["STUDIO_FOCUS_SHELL"]
                    else []
                )
                ctx["MANAGER_PLATFORM_ADMIN_SHELL"] = is_manager_platform_admin_path(
                    path
                )
                ctx["MANAGER_PLATFORM_ADMIN_NAV"] = (
                    build_manager_platform_admin_nav(request)
                    if ctx["MANAGER_PLATFORM_ADMIN_SHELL"]
                    else {"quick_links": []}
                )
            except OPTIONAL_CONTEXT_ERRORS:
                ctx["STUDIO_FOCUS_SHELL"] = False
                ctx["STUDIO_FOCUS_SIDEBAR"] = []
                ctx["MANAGER_PLATFORM_ADMIN_SHELL"] = False
                ctx["MANAGER_PLATFORM_ADMIN_NAV"] = {"quick_links": []}
        except OPTIONAL_CONTEXT_ERRORS:
            ctx["CONTROL_PLANE_NAV"] = []
            ctx["PRIMARY_CONTROL_PLANE_NAV"] = []
            ctx["PINNED_CONTROL_PLANE_ITEMS"] = []
            ctx["PINNED_CONTROL_PLANE_IDS"] = set()
            ctx["STUDIO_FOCUS_SHELL"] = False
            ctx["STUDIO_FOCUS_SIDEBAR"] = []
            ctx["MANAGER_PLATFORM_ADMIN_SHELL"] = False
            ctx["MANAGER_PLATFORM_ADMIN_NAV"] = {"quick_links": []}
    else:
        ctx["CONTROL_PLANE_NAV"] = []
        ctx["PRIMARY_CONTROL_PLANE_NAV"] = []
        ctx["PINNED_CONTROL_PLANE_ITEMS"] = []
        ctx["PINNED_CONTROL_PLANE_IDS"] = set()
        ctx["STUDIO_FOCUS_SHELL"] = False
        ctx["STUDIO_FOCUS_SIDEBAR"] = []
        ctx["MANAGER_PLATFORM_ADMIN_SHELL"] = False
        ctx["MANAGER_PLATFORM_ADMIN_NAV"] = {"quick_links": []}
        try:
            from apps.accounts.permissions import tenant_operator_hub_eligible
            from apps.schools.control_plane_nav import build_tenant_operator_primary_nav

            if tenant_operator_hub_eligible(getattr(request, "user", None)):
                ctx["PRIMARY_CONTROL_PLANE_NAV"] = build_tenant_operator_primary_nav(
                    request
                )
        except OPTIONAL_CONTEXT_ERRORS:
            ctx["PRIMARY_CONTROL_PLANE_NAV"] = []
    # v2.65 Wave 1a (2026-05-15): platform-wide gate for the redundant
    # "RunMyCampus workspace / role" strip that rmc_os_page_header.html
    # renders. Pages whose canvas has its own h1 + page-context (Studio
    # shells, Marketplace governance, Ministry / accreditation stubs, App
    # Catalog Governance, Migration Center, Configuration Center) get the
    # flag turned on so the strip is suppressed. v2.64.1's B1 only handled
    # Studio Control via a block override; this URL-prefix list generalizes
    # it. Per-view code can opt in/out by setting page_provides_own_h1 in
    # its template context (this just provides the platform default).
    p = (request.path or "").strip()
    own_h1_prefixes = (
        "/studio/",                      # Studio shell renders own toolbar + h1 in shell_main_content.html
        "/super/marketplace-cms/",       # Marketplace governance has own h1
        "/super/marketplace/",           # marketplace governance alias
        "/super/wedge/",                 # Ministry / accreditation stubs
        "/super/marketplace-app-catalog/",
        "/super/migration/",             # Migration Cloud operator console
        "/portal/configure/",            # Tenant settings hub (Apple Settings IA)
        "/siteconfig/console/",          # Configuration Control Center
    )
    ctx.setdefault(
        "page_provides_own_h1",
        any(p.startswith(prefix) for prefix in own_h1_prefixes),
    )

    ctx["PUBLIC_BRAND_NAME"] = "RunMyCampus"
    ctx["PUBLIC_BRAND_DOMAIN"] = "runmycampus.com"
    ctx["PUBLIC_BRAND_TAGLINE"] = (
        ""  # Single-line brand only; no platform tagline anywhere
    )
    # Public brand palette: used by marketing/control-plane shells when PUBLIC_BRAND_MODE is true.
    # Priority: RuntimeDefaults (admin-configurable) -> env -> stable defaults.
    _primary = ""
    _accent = ""
    try:
        from apps.platform_runtime.models import RuntimeDefaults

        rd = RuntimeDefaults.get_singleton()
        if rd is not None:
            _primary = str(getattr(rd, "public_brand_primary_color", None) or "").strip()
            _accent = str(getattr(rd, "public_brand_accent_color", None) or "").strip()
            if not _primary or not _accent:
                payload = getattr(rd, "payload", None) or {}
                if isinstance(payload, dict):
                    if not _primary:
                        _primary = str(
                            payload.get("public_brand_primary_color") or ""
                        ).strip()
                    if not _accent:
                        _accent = str(
                            payload.get("public_brand_accent_color") or ""
                        ).strip()
    except OPTIONAL_CONTEXT_ERRORS:
        pass
    ctx["PUBLIC_BRAND_PRIMARY_COLOR"] = _primary or os.getenv(
        "PUBLIC_BRAND_PRIMARY_COLOR", "#002147"
    )
    ctx["PUBLIC_BRAND_ACCENT_COLOR"] = _accent or os.getenv(
        "PUBLIC_BRAND_ACCENT_COLOR", "#d4af37"
    )
    if public_brand_mode:
        ctx["SITE_LOGO_URL"] = ""
        ctx["SITE_LOGO_DARK_URL"] = ""
        ctx["SITE_BRANDED_DOMAIN"] = "runmycampus.com"
        ctx["TENANT_WALLPAPER_URL"] = ""
        ctx["SITE_PRIMARY_COLOR"] = None
        ctx["SITE_ACCENT_COLOR"] = None
        # Public-brand logo URLs follow the same 3-layer cascade as the colors
        # above: RuntimeDefaults (admin-configurable via Manager Config Center)
        # -> env override (deploy-time) -> in-repo platform default. The
        # brand-mark squircle is square; we feed it the icon (square mark)
        # rather than the wide horizontal logo, which would crop. The full
        # horizontal lockup is composed by the partial: squircle (icon) +
        # wordmark text rendered separately.
        _rd_logo = ""
        _rd_logo_dark = ""
        _rd_favicon = ""
        try:
            from apps.platform_runtime.models import RuntimeDefaults

            _rd = RuntimeDefaults.get_singleton()
            if _rd is not None:
                _rd_logo = str(getattr(_rd, "public_brand_logo_url", None) or "").strip()
                _rd_logo_dark = str(
                    getattr(_rd, "public_brand_logo_dark_url", None) or ""
                ).strip()
                _rd_favicon = str(
                    getattr(_rd, "public_brand_favicon_url", None) or ""
                ).strip()
                if not _rd_logo or not _rd_logo_dark or not _rd_favicon:
                    _rd_payload = getattr(_rd, "payload", None) or {}
                    if isinstance(_rd_payload, dict):
                        if not _rd_logo:
                            _rd_logo = str(
                                _rd_payload.get("public_brand_logo_url") or ""
                            ).strip()
                        if not _rd_logo_dark:
                            _rd_logo_dark = str(
                                _rd_payload.get("public_brand_logo_dark_url") or ""
                            ).strip()
                        if not _rd_favicon:
                            _rd_favicon = str(
                                _rd_payload.get("public_brand_favicon_url") or ""
                            ).strip()
        except OPTIONAL_CONTEXT_ERRORS:
            pass
        ctx["PUBLIC_BRAND_LOGO_LOCKUP_URL"] = static(_PLATFORM_LOGO_MARK_STATIC)
        ctx["PUBLIC_BRAND_LOGO_URL"] = _resolve_public_brand_logo_url(
            _rd_logo or os.getenv("PUBLIC_BRAND_LOGO_URL", "").strip(),
            default_static=_PLATFORM_LOGO_MARK_STATIC,
        )
        ctx["PUBLIC_BRAND_LOGO_DARK_URL"] = _resolve_public_brand_logo_url(
            _rd_logo_dark or os.getenv("PUBLIC_BRAND_LOGO_DARK_URL", "").strip(),
            default_static=_PLATFORM_LOGO_MARK_STATIC,
        )
        ctx["PUBLIC_BRAND_FAVICON_URL"] = _resolve_public_brand_logo_url(
            _rd_favicon or os.getenv("PUBLIC_BRAND_FAVICON_URL", "").strip(),
            default_static=_PLATFORM_FAVICON_STATIC,
        )
        ctx["SITE_FAVICON_URL"] = ctx["PUBLIC_BRAND_FAVICON_URL"]
    else:
        ctx["PUBLIC_BRAND_LOGO_URL"] = ""
        ctx["PUBLIC_BRAND_LOGO_DARK_URL"] = ""
        ctx["PUBLIC_BRAND_FAVICON_URL"] = ""
        ctx["PUBLIC_BRAND_LOGO_LOCKUP_URL"] = ""
    # Offline: global Feature Control must be on; in multi-tenant, school must have offline_mode via Policy Registry.
    if school:
        try:
            offline_enabled = get_effective_policy(
                school, user=getattr(request, "user", None), capability="offline_mode"
            ).get("enabled", False)
        except OPTIONAL_CONTEXT_ERRORS:
            offline_enabled = False
    else:
        offline_enabled = True
    offline_runtime_settings = (
        site.get_offline_runtime_settings()
        if callable(getattr(site, "get_offline_runtime_settings", None))
        else {"enable_offline_mode": bool(getattr(site, "enable_offline_mode", False))}
    )
    ctx["OFFLINE_ENABLED_FOR_CURRENT_SCHOOL"] = (
        bool(offline_runtime_settings.get("enable_offline_mode", False))
        and offline_enabled
    )
    flags_ctx = _resolve_backend_feature_flags(request, site)
    # Whether to show the connection status bar (offline pill) in the header.
    ctx["SHOW_OFFLINE_STATUS_BAR"] = ctx["OFFLINE_ENABLED_FOR_CURRENT_SCHOOL"] and bool(
        flags_ctx.get("show_offline_status_bar", True)
    )
    ctx["OFFLINE_SYNC_QUEUE_URL"] = None
    ctx["OFFLINE_CONFLICTS_URL"] = None
    ctx["OFFLINE_API_ENQUEUE_URL"] = None
    ctx["OFFLINE_API_PROCESS_URL"] = None
    if ctx.get("SHOW_OFFLINE_STATUS_BAR") and user and getattr(
        user, "is_authenticated", False
    ):
        try:
            ctx["OFFLINE_SYNC_QUEUE_URL"] = reverse("portal:offline_sync_queue")
            ctx["OFFLINE_CONFLICTS_URL"] = reverse("portal:offline_sync_conflicts")
            ctx["OFFLINE_API_ENQUEUE_URL"] = reverse("portal:api_offline_enqueue")
            ctx["OFFLINE_API_PROCESS_URL"] = reverse("portal:api_offline_process")
        except NoReverseMatch:
            pass
    # Super Admin / Schools: global toggle to show or hide /super/ and Schools link.
    ctx["SUPER_ADMIN_UI_ENABLED"] = bool(flags_ctx.get("enable_super_admin_ui", True))
    portal_items = ctx["PORTAL_SIDEBAR_ITEMS"]
    pinned_list, pinned_ids = _get_pinned_sidebar_items(request, portal_items)
    ctx["PINNED_SIDEBAR_ITEMS"] = pinned_list
    ctx["PINNED_SIDEBAR_IDS"] = pinned_ids
    return ctx


def region_settings(request):
    """
    Provides region-specific settings and utilities to all templates.
    Phase 1.2.4: Internationalization & Multi-Region Support.
    Multi-tenant: when request.school is set, region/grading/language come from school.default_region and School.settings.
    """
    from types import SimpleNamespace
    from django.conf import settings
    from apps.siteconfig.currency import get_currency_symbol

    school = _request_school(request)
    grading_scale = None
    default_language = None
    policy = get_effective_policy(school) if school else {}
    try:
        # Policy-first when school is set: no direct region read for grading/language (Section 24.2).
        if school and school.default_region_id:
            region = school.default_region
            grading_scale = (policy.get("grading") or {}).get(
                "grading_scale"
            ) or "default"
            default_language = policy.get("default_language") or "en"
        else:
            _session = getattr(request, "session", None)
            region_code = (
                _session.get("region_code", settings.REGION_CODE)
                if _session
                else settings.REGION_CODE
            )
            _user = getattr(request, "user", None)
            if _user and getattr(_user, "is_authenticated", False):
                try:
                    pref = getattr(_user, "preferences", None)
                    if pref and getattr(pref, "preferred_region", ""):
                        region_code = pref.preferred_region
                except (AttributeError, DatabaseError, TypeError, ValueError):
                    pass
            region = RegionConfig.objects.get(code=region_code)
            grading_scale = getattr(region, "grading_scale", "default")
            default_language = getattr(region, "default_language", "en")
    except RegionConfig.DoesNotExist:
        # Fallback to the platform-neutral default region.
        region = RegionConfig.get_default()
        grading_scale = getattr(region, "grading_scale", "default")
        default_language = getattr(region, "default_language", "en")
    except DatabaseError:
        _reset_db_state()
        try:
            region = RegionConfig.get_default()
            grading_scale = getattr(region, "grading_scale", "default")
            default_language = getattr(region, "default_language", "en")
        except (AttributeError, DatabaseError, TypeError, ValueError):
            _pd = get_platform_defaults(use_db=False)
            region = SimpleNamespace(
                code=_pd["region_code"],
                name="Default",
                default_currency=_pd["currency"],
                date_format="YYYY-MM-DD",
                timezone=_pd["timezone"],
                default_language="en",
                grading_scale=_pd["grading_scale"],
                decimal_separator=".",
                thousands_separator=",",
                is_rtl=False,
            )
            grading_scale = _pd["grading_scale"]
            default_language = "en"
    if school and not (school.default_region_id):
        grading_scale = (policy.get("grading") or {}).get(
            "grading_scale"
        ) or grading_scale
        default_language = policy.get("default_language") or default_language
    if grading_scale is None:
        grading_scale = getattr(region, "grading_scale", "default")
    if default_language is None:
        default_language = getattr(region, "default_language", "en")

    tenant_locale = {}
    if school:
        try:
            from .tenant_config import get_tenant_locale

            tenant_locale = get_tenant_locale(school=school)
        except OPTIONAL_CONTEXT_ERRORS:
            tenant_locale = {}

    effective_currency = (
        (tenant_locale or {}).get("currency")
        or getattr(region, "default_currency", None)
        or get_platform_defaults(use_db=False)["currency"]
    )
    currency_symbol = get_currency_symbol(effective_currency)
    effective_date_format = (tenant_locale or {}).get("date_format") or getattr(
        region, "date_format", "YYYY-MM-DD"
    )
    effective_language = (tenant_locale or {}).get("locale") or default_language
    effective_grading_scale = (tenant_locale or {}).get(
        "grading_scale"
    ) or grading_scale

    is_rtl = (
        bool(policy.get("rtl", False)) if school else getattr(region, "is_rtl", False)
    )
    if (tenant_locale or {}).get("is_rtl") is True:
        is_rtl = True
    base_ctx = {
        "region": region,
        "region_code": getattr(region, "code", None)
        or get_platform_defaults(use_db=False)["region_code"],
        "region_name": getattr(region, "name", "Default"),
        "currency_symbol": currency_symbol,
        "date_format": effective_date_format,
        "timezone": getattr(region, "timezone", "UTC"),
        "default_language": effective_language,
        "grading_scale": effective_grading_scale,
        "decimal_separator": getattr(region, "decimal_separator", "."),
        "thousands_separator": getattr(region, "thousands_separator", ","),
        "enable_multi_region": getattr(settings, "ENABLE_MULTI_REGION", False),
        "is_rtl": is_rtl,
    }
    try:
        from apps.siteconfig.regional_ui import augment_region_shell_context

        base_ctx.update(augment_region_shell_context(base_ctx, request))
    except OPTIONAL_CONTEXT_ERRORS:
        base_ctx.setdefault("rmc_locale", effective_language or "en")
        base_ctx.setdefault("rmc_text_direction", "rtl" if is_rtl else "ltr")
        base_ctx.setdefault(
            "rmc_regional_ui",
            {"locale": base_ctx["rmc_locale"], "direction": base_ctx["rmc_text_direction"]},
        )
    return base_ctx


def language_context(request):
    """
    Provide language-related context for templates.
    Supports region-based auto-selection and manual override.
    """
    # Determine current language
    current_language = translation.get_language()

    # Check for manual language preference
    if "language" in request.GET:
        requested_language = request.GET.get("language")
        if requested_language in SUPPORTED_LANGUAGES:
            current_language = requested_language
            translation.activate(requested_language)
    elif "django_language" in request.COOKIES:
        # Load from cookie
        cookie_language = request.COOKIES.get("django_language")
        if cookie_language in SUPPORTED_LANGUAGES:
            current_language = cookie_language
    else:
        # Prefer persisted user language, then region-based default
        _user = getattr(request, "user", None)
        if _user and getattr(_user, "is_authenticated", False):
            try:
                pref = getattr(_user, "preferences", None)
                if pref and getattr(pref, "preferred_language", ""):
                    lang = pref.preferred_language
                    if lang in SUPPORTED_LANGUAGES:
                        current_language = lang
            except (AttributeError, DatabaseError, TypeError, ValueError):
                pass
        if current_language == translation.get_language():
            # Multi-tenant: prefer school default language from Policy Registry when request.school is set
            school = _request_school(request)
            if school:
                policy = get_effective_policy(school)
                lang_override = policy.get("default_language")
                if lang_override and lang_override in SUPPORTED_LANGUAGES:
                    current_language = lang_override
                elif school.default_region_id:
                    region = school.default_region
                    default_language = getattr(region, "default_language", None)
                    if default_language and default_language in SUPPORTED_LANGUAGES:
                        current_language = default_language
            else:
                # Not set from preference: try region-based auto-detection
                try:
                    region = RegionConfig.get_default()
                    if _user and getattr(_user, "is_authenticated", False):
                        try:
                            pref = getattr(_user, "preferences", None)
                            if pref and getattr(pref, "preferred_region", ""):
                                region = RegionConfig.objects.get(
                                    code=pref.preferred_region
                                )
                            else:
                                region = RegionConfig.objects.get(code=region.code)
                        except (
                            RegionConfig.DoesNotExist,
                            AttributeError,
                            DatabaseError,
                            TypeError,
                            ValueError,
                        ):
                            pass
                    default_language = getattr(region, "default_language", None) or "en"
                    if default_language in SUPPORTED_LANGUAGES:
                        current_language = default_language
                except DatabaseError:
                    _reset_db_state()
                except (AttributeError, TypeError, ValueError):
                    pass

    # Get available languages
    available_languages = [(code, name) for code, name in SUPPORTED_LANGUAGES.items()]
    current_language_name = SUPPORTED_LANGUAGES.get(current_language, "English")

    return {
        "current_language": current_language,
        "current_language_name": current_language_name,
        "available_languages": available_languages,
        "supported_languages": SUPPORTED_LANGUAGES,
        "translate": lambda text: TranslationManager.get_text(text, current_language),
    }


def ai_copilot_settings(request):
    """
    Context processor for AI Copilot settings.
    Provides frontend-safe AI visibility flags and RBAC permissions to templates.

    Ensures AI copilot respects role-based access control:
    - ADMIN/LEADERSHIP: Full system access (analytics, finance, compliance)
    - TEACHER: Class and grade data access
    - PARENT: Child-specific data access
    - Other: General navigation only
    """
    # Get user role
    _user = getattr(request, "user", None)
    user_role = "USER"
    if _user and getattr(_user, "is_authenticated", False):
        user_role = (getattr(_user, "role", "USER") or "").upper()

    admin_roles = {
        "ADMIN",  # role-string-allow: ai-copilot-rbac-role-set-against-user.role
        "LEADERSHIP",
        "PRINCIPAL",
        "VICE_PRINCIPAL",
        "DEAN",
        "IT_ADMIN",
        "SUPERADMIN",
    }
    is_admin_like = False
    if _user and getattr(_user, "is_authenticated", False):
        is_admin_like = (
            getattr(_user, "is_superuser", False)
            or getattr(_user, "is_staff", False)
            or user_role in admin_roles
        )
        if not is_admin_like:
            try:
                from apps.schools.control_plane import user_has_control_plane_access

                is_admin_like = user_has_control_plane_access(_user)
            except ImportError:
                pass

    # Determine AI permissions based on role
    ai_permissions = {
        "can_access_ai": bool(_user and getattr(_user, "is_authenticated", False)),
        "can_analyze_data": False,
        "can_view_financial": False,
        "can_view_compliance": False,
        "can_access_grades": False,
        "can_access_roster": False,
        "scope": "general",
    }

    if is_admin_like:
        ai_permissions.update(
            {
                "can_analyze_data": True,
                "can_view_financial": True,
                "can_view_compliance": True,
                "can_access_grades": True,
                "can_access_roster": True,
                "scope": "admin",
            }
        )
    elif user_role == "BURSAR":
        ai_permissions.update(
            {
                "can_analyze_data": True,
                "can_view_financial": True,
                "scope": "finance",
            }
        )
    elif user_role == "TEACHER":  # role-string-allow: ai-copilot-rbac-compare-against-user.role
        ai_permissions.update(
            {
                "can_access_grades": True,
                "can_access_roster": True,
                "scope": "teacher",
            }
        )
    elif user_role == "PARENT":  # role-string-allow: ai-copilot-rbac-compare-against-user.role
        ai_permissions.update(
            {
                "can_access_grades": True,  # Only their child's
                "can_view_financial": True,  # Only their child's fees
                "scope": "parent",
            }
        )
    ai_backend_enabled = False
    ai_provider_name = ""
    try:
        from apps.portal.ai_provider import get_ai_provider_status

        status = get_ai_provider_status()
        ai_backend_enabled = bool(status.get("has_live_provider")) or bool(
            status.get("rules_fallback_enabled")
        )
        for provider in status.get("preference", []):
            provider_cfg = (
                status.get(provider, {})
                if isinstance(status.get(provider), dict)
                else {}
            )
            if provider == "rules" and status.get("rules_fallback_enabled"):
                ai_provider_name = "rules"
                break
            if provider_cfg.get("configured"):
                ai_provider_name = provider
                break
    except (AttributeError, ImportError, TypeError, ValueError):
        ai_backend_enabled = False
        ai_provider_name = ""

    return {
        "AI_BACKEND_ENABLED": ai_backend_enabled,
        "AI_PROVIDER_NAME": ai_provider_name,
        "AI_PERMISSIONS": json.dumps(ai_permissions),
        "USER_ROLE": user_role,
    }


def lexicon_context(request):
    """Wave A — G1: emit the tenant's terminology overrides as a JSON
    payload for ``<meta name="rmc-lexicon">`` (see
    ``templates/partials/rmc_lexicon_meta.html``) and a server-side
    ``lexicon`` dict for direct template use.

    Falls back to an empty payload (and an empty dict) when no school is
    resolved on the request (anonymous marketing visits, system tasks).
    Errors are swallowed — terminology is decorative, not load-bearing.
    """
    school = getattr(request, "school", None) if request is not None else None
    payload_json = ""
    full: dict[str, dict[str, str]] = {}
    try:
        from apps.siteconfig.terminology_service import (
            lexicon_payload,
            resolve_all_terms,
        )

        compact = lexicon_payload(school)
        if compact:
            payload_json = json.dumps(compact, separators=(",", ":"))
        full = resolve_all_terms(school)
    except (AttributeError, DatabaseError, ImportError, RuntimeError, TypeError, ValueError):
        payload_json = ""
        full = {}
    return {
        "rmc_lexicon_meta": payload_json,
        "lexicon": full,
    }

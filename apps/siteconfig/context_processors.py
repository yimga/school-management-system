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
from .portal_sidebar_items import build_portal_sidebar_baseline, build_portal_sidebar_items
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
    """Return portal sidebar items (optionally sorted by portal_sidebar_order).

    When the full builder raises OR yields nothing — the classic under-provisioned
    new-tenant symptom — fall back to a resilient, role + permission gated BASELINE
    (real, known-good nav) instead of ``[]``. Returning ``[]`` made the template drop
    to a hardcoded, ungated fallback nav; the baseline keeps the permission-gated
    config-driven branch alive for authenticated users.
    """
    items = None
    try:
        items = build_portal_sidebar_items(request, site)
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
    if items:
        return items
    try:
        return build_portal_sidebar_baseline(request, site)
    except OPTIONAL_CONTEXT_ERRORS:
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
                prefs = DashboardUserPreference.objects.filter(
                    user=request.user
                ).first()
            except DatabaseError:
                prefs = None
            # Treat an absent row as first-time so default pins seed for DISPLAY,
            # but do NOT create it here. A write in this read-path context
            # processor deadlocks LiveServerTestCase + sqlite (the test holds an
            # open transaction while the live-server thread's write waits on the
            # row lock -> 120s request timeout) and hangs fresh-tenant requests
            # on lock contention. The row is created when the user actually saves
            # a preference.
            prefs_created = prefs is None

        raw_pinned_ids = (
            getattr(prefs, "pinned_sidebar_items", None) if prefs is not None else None
        )
        pinned_ids = list(raw_pinned_ids or [])
        # Seed defaults only for first-time preferences (or legacy null state), not when users intentionally unpin all.
        if not pinned_ids and (prefs_created or raw_pinned_ids is None):
            try:
                from apps.accounts.portal_roles import get_nav_portal_role

                role = (
                    get_nav_portal_role(request)
                    or getattr(request.user, "role", "")
                    or ""
                ).upper()
            except OPTIONAL_CONTEXT_ERRORS:
                role = (getattr(request.user, "role", "") or "").upper()
            default_pin_map = {
                "TEACHER": ["teacher_workflow", "preferences"],
                "PARENT": ["parent_workflow", "preferences"],
                "STUDENT": ["student_workflow", "preferences"],
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


def _resolve_cockpit_surface(request, ctx, public_host_kind, path):
    """Map the current request to a cockpit surface (drives skin + brand pill).

    Deterministic: manager host → manager/studio; tenant host → by path prefix,
    then by user role for the generic portal landing. Surfaces are defined in
    apps/siteconfig/cockpit_config.py; admins override the per-surface skin there.
    """
    p = (path or "").split("?", 1)[0]
    if public_host_kind == "manager":
        return "studio" if ctx.get("STUDIO_FOCUS_SHELL") else "manager"
    if p.startswith("/studio"):
        return "studio"
    if p.startswith("/teacher"):
        return "teacher"
    if p.startswith("/parent"):
        return "parent"
    if p.startswith("/student"):
        return "student"
    if p.startswith("/backend") or p.startswith("/admin"):
        return "backend"
    role = str(getattr(getattr(request, "user", None), "role", "") or "").lower()
    if "teacher" in role:
        return "teacher"
    if "parent" in role or "guardian" in role:
        return "parent"
    if "student" in role:
        return "student"
    if "admin" in role or "proprietor" in role:
        return "backend"
    return "portal"


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
            # get-only (no create): a write in this read-path context processor
            # deadlocks LiveServerTestCase + sqlite and hangs fresh-tenant
            # requests on lock contention. Fall back to an unsaved instance
            # carrying the defaults; the row is persisted when the user saves a
            # preference.
            dashboard_pref = DashboardUserPreference.objects.filter(
                user=user
            ).first()
            if dashboard_pref is None:
                dashboard_pref = DashboardUserPreference(
                    user=user, sidebar_collapsed=default_collapsed
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
        # finance is a TENANT app. This SHARED context processor runs on every
        # request, including hosts whose search_path has no finance_notification
        # table (manager / public host, or a tenant page rendered before the
        # schema is provisioned). Guard like apps.accounts.context_processors:
        # reset the (possibly aborted) connection state and fall back to 0
        # instead of 500-ing the page.
        try:
            # tenant-isolation-allow: recipient-scoped-current-user-owns-notification
            finance_request_alerts = Notification.objects.filter(
                recipient=user,
                title__icontains="finance access request",
                is_read=False,
            ).count()
            # tenant-isolation-allow: recipient-scoped-current-user-owns-notification
            notifications_unread_count = Notification.objects.filter(
                recipient=user,
                is_read=False,
            ).count()
        except DatabaseError:
            _reset_db_state()
            finance_request_alerts = 0
            notifications_unread_count = 0
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
    # Cache portal "hat" checks before building sidebar (nav role uses cached hats)
    effective_portal_role = None
    if user and getattr(user, "is_authenticated", False) and getattr(user, "pk", None):
        try:
            from apps.accounts.portal_roles import (
                has_teacher_hat,
                has_parent_hat,
                get_nav_portal_role,
            )

            request._portal_teacher_hat = has_teacher_hat(user)
            request._portal_parent_hat = has_parent_hat(user)
            effective_portal_role = get_nav_portal_role(request)
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
            feature_flags.get("show_header_context_weather", True)
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
        "HEADER_WEATHER_TIMEZONE": str(
            feature_flags.get(
                "header_weather_timezone",
                weather_defaults["header_weather_timezone"],
            )
            or "UTC"
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
    # Copilot rail "Pending / Due" quickstats — previously dead template bindings.
    # The helper is cached per (user, school) and fully failure-isolated, so this
    # never raises and runs its COUNT queries at most once a minute per user.
    try:
        from apps.siteconfig.copilot_quickstats import build_copilot_quickstats

        ctx.update(build_copilot_quickstats(request))
    except Exception:  # noqa: BLE001 — quickstats are decorative; never 500 the page
        ctx.setdefault("copilot_pending_approvals_count", 0)
        ctx.setdefault("copilot_due_today_count", 0)
    try:
        ctx["PORTAL_DOCUMENT_LIBRARY_MANAGE_URL"] = reverse(
            "portal:document_library_manage"
        )
    except NoReverseMatch:
        ctx["PORTAL_DOCUMENT_LIBRARY_MANAGE_URL"] = None
    # Dual-role (Teacher + Parent): show role switcher when user has both hats (cache already set above)
    if user and getattr(user, "is_authenticated", False):
        try:
            from apps.accounts.portal_roles import get_nav_portal_role

            has_teacher = getattr(request, "_portal_teacher_hat", False)
            has_parent = getattr(request, "_portal_parent_hat", False)
            ctx["SHOW_ROLE_SWITCHER"] = has_teacher and has_parent
            ctx["EFFECTIVE_PORTAL_ROLE"] = get_nav_portal_role(request) or (
                (getattr(user, "role", "") or "").upper()
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
        try:
            from apps.siteconfig.brand_guard_runtime import guard_brand_dict

            _tp = (theme_pref or "system").strip().lower()
            _effective_surface = (
                "dark" if _tp == "dark" else "light"
            )  # system → light at SSR; client resolves OS
            tenant_brand, _brand_adjusted = guard_brand_dict(
                tenant_brand, effective_surface=_effective_surface
            )
            ctx["BRAND_AAA_ADJUSTED"] = _brand_adjusted
        except ImportError:
            ctx["BRAND_AAA_ADJUSTED"] = False
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
    ctx["rmc_backend_extends"] = (
        "backend_base_manager.html"
        if public_host_kind == "manager"
        else "backend_base_tenant.html"
    )
    user = getattr(request, "user", None)
    is_authenticated = bool(user and getattr(user, "is_authenticated", False))
    # Compact operator gateway footer on manager host login via base.html (never full marketing bundle).
    ctx["SHOW_CORPORATE_MARKETING_FOOTER"] = (
        public_host_kind == "manager" and not school and not is_authenticated
    )
    # Manager control-plane shell: compact operator footer (rmc_operator_footer_compact), not marketing mega-footer.
    ctx["SHOW_MANAGER_CORPORATE_FOOTER"] = public_host_kind == "manager"
    ctx["MANAGER_PLATFORM_ADMIN_SHELL"] = False
    ctx["MANAGER_PLATFORM_ADMIN_NAV"] = {"quick_links": [], "guided_links": [], "groups": []}
    ctx["MANAGER_UNIFIED_SIDEBAR_GROUPS"] = []
    ctx["MANAGER_COMPLETE_SIDEBAR_NAV"] = []
    if ctx["CONTROL_PLANE_SHELL"]:
        try:
            from apps.schools.control_plane_nav import (
                build_control_plane_nav,
                build_manager_platform_admin_primary_nav,
                build_primary_control_plane_nav,
                is_manager_platform_admin_path,
            )
            from apps.schools.manager_nav_convergence import (
                build_manager_complete_sidebar_groups,
                build_manager_unified_sidebar_groups,
            )

            ctx["MANAGER_UNIFIED_SIDEBAR_GROUPS"] = build_manager_unified_sidebar_groups(
                request
            )
            ctx["MANAGER_COMPLETE_SIDEBAR_NAV"] = build_manager_complete_sidebar_groups(
                request
            )
            ctx["CONTROL_PLANE_NAV"] = build_control_plane_nav(request)
            if is_manager_platform_admin_path(path):
                ctx["PRIMARY_CONTROL_PLANE_NAV"] = (
                    build_manager_platform_admin_primary_nav(request)
                )
            else:
                ctx["PRIMARY_CONTROL_PLANE_NAV"] = build_primary_control_plane_nav(
                    request
                )
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
            for grp in ctx["MANAGER_COMPLETE_SIDEBAR_NAV"]:
                for it in grp.get("items") or []:
                    iid = it.get("id")
                    if iid and it.get("url"):
                        by_id[iid] = it
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
                    else {"quick_links": [], "guided_links": [], "groups": []}
                )
                if ctx["MANAGER_PLATFORM_ADMIN_SHELL"]:
                    try:
                        from config.admin import platform_admin_site
                        from apps.siteconfig.platform_admin_catalog import (
                            build_platform_admin_catalog,
                        )

                        _app_list = platform_admin_site.get_app_list(request)
                        ctx["admin_catalog"] = build_platform_admin_catalog(_app_list)
                    except OPTIONAL_CONTEXT_ERRORS:
                        ctx["admin_catalog"] = None
            except OPTIONAL_CONTEXT_ERRORS:
                ctx["STUDIO_FOCUS_SHELL"] = False
                ctx["STUDIO_FOCUS_SIDEBAR"] = []
                ctx["MANAGER_PLATFORM_ADMIN_SHELL"] = False
                ctx["MANAGER_PLATFORM_ADMIN_NAV"] = {
                    "quick_links": [],
                    "guided_links": [],
                    "groups": [],
                }
                ctx["MANAGER_UNIFIED_SIDEBAR_GROUPS"] = []
                ctx["MANAGER_COMPLETE_SIDEBAR_NAV"] = []
        except OPTIONAL_CONTEXT_ERRORS:
            ctx["CONTROL_PLANE_NAV"] = []
            ctx["PRIMARY_CONTROL_PLANE_NAV"] = []
            ctx["PINNED_CONTROL_PLANE_ITEMS"] = []
            ctx["PINNED_CONTROL_PLANE_IDS"] = set()
            ctx["STUDIO_FOCUS_SHELL"] = False
            ctx["STUDIO_FOCUS_SIDEBAR"] = []
            ctx["MANAGER_PLATFORM_ADMIN_SHELL"] = False
            ctx["MANAGER_PLATFORM_ADMIN_NAV"] = {
                "quick_links": [],
                "guided_links": [],
                "groups": [],
            }
            ctx["MANAGER_UNIFIED_SIDEBAR_GROUPS"] = []
            ctx["MANAGER_COMPLETE_SIDEBAR_NAV"] = []
    else:
        ctx["CONTROL_PLANE_NAV"] = []
        ctx["PRIMARY_CONTROL_PLANE_NAV"] = []
        ctx["PINNED_CONTROL_PLANE_ITEMS"] = []
        ctx["PINNED_CONTROL_PLANE_IDS"] = set()
        ctx["STUDIO_FOCUS_SHELL"] = False
        ctx["STUDIO_FOCUS_SIDEBAR"] = []
        ctx["MANAGER_PLATFORM_ADMIN_SHELL"] = False
        ctx["MANAGER_PLATFORM_ADMIN_NAV"] = {
            "quick_links": [],
            "guided_links": [],
            "groups": [],
        }
        ctx["MANAGER_UNIFIED_SIDEBAR_GROUPS"] = []
        ctx["MANAGER_COMPLETE_SIDEBAR_NAV"] = []
        try:
            from apps.accounts.permissions import tenant_operator_hub_eligible
            from apps.schools.control_plane_nav import build_tenant_operator_primary_nav

            if tenant_operator_hub_eligible(getattr(request, "user", None)):
                ctx["PRIMARY_CONTROL_PLANE_NAV"] = build_tenant_operator_primary_nav(
                    request
                )
        except OPTIONAL_CONTEXT_ERRORS:
            ctx["PRIMARY_CONTROL_PLANE_NAV"] = []
    # ------------------------------------------------------------------
    # Cockpit shell blueprint (v8 200x app-shell) — fully config-driven.
    # Resolves the per-surface skin, header composition, page-header actions and
    # primary-nav glyph overrides from the brand_experience cascade. SOT lives in
    # apps/siteconfig/cockpit_config.py; admins change any knob there. Nothing in
    # the shell templates is hardcoded — they all read ``cockpit.*``.
    # ------------------------------------------------------------------
    # Namespaced as ``cockpit_shell`` — the existing ``cockpit`` object
    # (apps/siteconfig/cockpit_context.py: brand tagline + pulse + workspace)
    # is left untouched; this adds the per-surface skin + composition + actions.
    try:
        from apps.siteconfig.cockpit_config import build_cockpit_blueprint

        cockpit_surface = _resolve_cockpit_surface(
            request, ctx, public_host_kind, path
        )
        cockpit_shell = build_cockpit_blueprint(site, surface=cockpit_surface)
    except OPTIONAL_CONTEXT_ERRORS:
        cockpit_shell = None
    ctx["cockpit_shell"] = cockpit_shell
    if cockpit_shell:
        nav = ctx.get("PRIMARY_CONTROL_PLANE_NAV") or []
        if nav:
            hidden = set(cockpit_shell.get("nav_hidden_ids") or [])
            glyphs = cockpit_shell.get("nav_glyphs") or {}
            use_glyphs = cockpit_shell.get("nav_use_glyphs", True)
            filtered = []
            for item in nav:
                if item.get("id") in hidden:
                    continue
                if use_glyphs:
                    glyph = glyphs.get(item.get("id"))
                    if glyph:
                        item["glyph"] = glyph
                else:
                    # Clear glyph so the template falls back to the Bootstrap icon.
                    item["glyph"] = ""
                filtered.append(item)
            ctx["PRIMARY_CONTROL_PLANE_NAV"] = filtered
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
        "/super/",                       # Control plane pages declare canvas h1/hero (suppress redundant strip)
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
    ctx["platform_palette"] = {
        "primary": ctx["PUBLIC_BRAND_PRIMARY_COLOR"],
        "accent": ctx["PUBLIC_BRAND_ACCENT_COLOR"],
    }
    ctx["CONTROL_PLANE_BRAND_CSS_VARS"] = ""
    if ctx.get("CONTROL_PLANE_SHELL"):
        try:
            from apps.brand_experience.control_plane_brand_vars import (
                control_plane_brand_css_vars,
            )

            ctx["CONTROL_PLANE_BRAND_CSS_VARS"] = control_plane_brand_css_vars(
                primary_color=ctx["PUBLIC_BRAND_PRIMARY_COLOR"],
                accent_color=ctx["PUBLIC_BRAND_ACCENT_COLOR"],
            )
        except OPTIONAL_CONTEXT_ERRORS:
            ctx["CONTROL_PLANE_BRAND_CSS_VARS"] = ""
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
    from django.conf import settings as dj_settings

    ctx["RMC_DEPLOYMENT_PROFILE"] = (
        getattr(dj_settings, "RMC_DEPLOYMENT_PROFILE", None) or "online"
    ).strip().lower()
    # Edge/hub: school ops + rules KB work without cloud AI; copilot needs hub Ollama only.
    ctx["RMC_AI_NEEDS_NETWORK"] = ctx["RMC_DEPLOYMENT_PROFILE"] not in ("edge",)
    flags_ctx = _resolve_backend_feature_flags(request, site)
    school_for_offline_cfg = getattr(request, "school", None)
    if school_for_offline_cfg is not None:
        from apps.schools.offline_delivery_settings import build_client_offline_config

        ctx["OFFLINE_DELIVERY_CLIENT"] = build_client_offline_config(
            school_for_offline_cfg,
            deployment_profile=ctx["RMC_DEPLOYMENT_PROFILE"],
            feature_flags=flags_ctx,
        )
    else:
        ctx["OFFLINE_DELIVERY_CLIENT"] = {}
    # Whether to show the connection status bar (offline pill) in the header.
    ctx["SHOW_OFFLINE_STATUS_BAR"] = ctx["OFFLINE_ENABLED_FOR_CURRENT_SCHOOL"] and bool(
        flags_ctx.get("show_offline_status_bar", True)
    )
    ctx["OFFLINE_SYNC_QUEUE_URL"] = None
    ctx["OFFLINE_CONFLICTS_URL"] = None
    ctx["OFFLINE_API_ENQUEUE_URL"] = None
    ctx["OFFLINE_API_PROCESS_URL"] = None
    ctx["OFFLINE_TOKEN_MINT_URL"] = None
    ctx["OFFLINE_PERMISSION_SNAPSHOT_URL"] = None
    ctx["OFFLINE_DELTA_URL"] = None
    if ctx.get("SHOW_OFFLINE_STATUS_BAR") and user and getattr(
        user, "is_authenticated", False
    ):
        try:
            ctx["OFFLINE_SYNC_QUEUE_URL"] = reverse("portal:offline_sync_queue")
            ctx["OFFLINE_CONFLICTS_URL"] = reverse("portal:offline_sync_conflicts")
            ctx["OFFLINE_API_ENQUEUE_URL"] = reverse("portal:api_offline_enqueue")
            ctx["OFFLINE_API_PROCESS_URL"] = reverse("portal:api_offline_process")
            ctx["OFFLINE_TOKEN_MINT_URL"] = reverse("api:devices-offline-token")
            ctx["OFFLINE_PERMISSION_SNAPSHOT_URL"] = reverse(
                "api:offline-permission-snapshot",
            )
            ctx["OFFLINE_DELTA_URL"] = reverse("api:offline-delta")
        except NoReverseMatch:
            pass
    ctx["FINANCE_GLOCAL"] = {}
    if school_for_offline_cfg is not None:
        path = (getattr(request, "path", "") or "").lower()
        app_name = ""
        match = getattr(request, "resolver_match", None)
        if match is not None:
            app_name = (getattr(match, "app_name", "") or "").lower()
        on_finance = app_name == "finance" or "/finance/" in path
        if on_finance:
            try:
                from apps.siteconfig.country_localization_service import resolve_for_request

                pack = resolve_for_request(request) or {}
                ctx["FINANCE_GLOCAL"] = {
                    "country_code": pack.get("country_code") or "",
                    "language_code": pack.get("language_code") or "",
                    "currency_code": pack.get("currency_code")
                    or pack.get("default_currency")
                    or "",
                    "terminology": pack.get("terminology") or {},
                    "calendar_system": pack.get("calendar_system") or {},
                }
            except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
                ctx["FINANCE_GLOCAL"] = {}
    # Super Admin / Schools: global toggle to show or hide /super/ and Schools link.
    ctx["SUPER_ADMIN_UI_ENABLED"] = bool(flags_ctx.get("enable_super_admin_ui", True))
    portal_items = ctx["PORTAL_SIDEBAR_ITEMS"]
    pinned_list, pinned_ids = _get_pinned_sidebar_items(request, portal_items)
    ctx["PINNED_SIDEBAR_ITEMS"] = pinned_list
    ctx["PINNED_SIDEBAR_IDS"] = pinned_ids
    school_for_chrome = getattr(request, "school", None)
    host_kind = getattr(request, "public_host_kind", None) or ""
    if school_for_chrome and host_kind != "manager":
        try:
            from apps.siteconfig.portal_chrome import (
                resolve_dashboard_pack_for_request,
                resolve_dashboard_template_for_request,
                resolve_portal_chrome,
            )

            ctx.update(
                resolve_portal_chrome(
                    site_theme=ctx.get("SITE_THEME"),
                    dashboard_pack=resolve_dashboard_pack_for_request(request),
                    dashboard_template=resolve_dashboard_template_for_request(request),
                )
            )
        except OPTIONAL_CONTEXT_ERRORS:
            ctx.setdefault("PORTAL_HEADER_VARIANT", "statement")
            ctx.setdefault("PORTAL_FOOTER_PARTIAL", "components/footer.html")
    else:
        ctx.setdefault("PORTAL_HEADER_VARIANT", "statement")
        if host_kind == "manager":
            ctx.setdefault(
                "PORTAL_FOOTER_PARTIAL",
                "partials/rmc_operator_footer_compact.html",
            )
        else:
            ctx.setdefault("PORTAL_FOOTER_PARTIAL", "components/footer.html")
    return ctx


def region_settings(request):
    """
    Provides region-specific settings and utilities to all templates.
    Phase 1.2.4: Internationalization & Multi-Region Support.
    Multi-tenant: when request.school is set, region/grading/language come from school.default_region and School.settings.
    """
    from types import SimpleNamespace
    from django.conf import settings
    from django.utils import translation
    from apps.siteconfig.currency import get_currency_symbol
    from apps.siteconfig.translations import SUPPORTED_LANGUAGES

    if "language" in request.GET:
        requested = (request.GET.get("language") or "").strip()
        if requested in SUPPORTED_LANGUAGES:
            translation.activate(requested)
    elif "django_language" in request.COOKIES:
        cookie_lang = request.COOKIES.get("django_language")
        if cookie_lang in SUPPORTED_LANGUAGES:
            translation.activate(cookie_lang)

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
    except (RegionConfig.DoesNotExist, DatabaseError) as _region_exc:
        # No RegionConfig row (fresh tenant), or the DB is momentarily
        # unavailable (sqlite lock contention during the CI gate's portal crawl).
        # Do NOT call RegionConfig.get_default() here: it does a get_or_create
        # (a WRITE), and this context processor runs on EVERY request. On a fresh
        # tenant or under sqlite lock contention that write blocks for the whole
        # DB busy-timeout, hanging the request to a Gateway Timeout (and earlier
        # 500ing when the lock raised immediately on /portal/student/onboarding/).
        # The region here is only needed for display (grading scale / language /
        # currency), so degrade to in-memory platform defaults — no DB write.
        # Materializing the GLOBAL RegionConfig row is a seed/migration concern,
        # not a per-request one.
        if isinstance(_region_exc, DatabaseError):
            _reset_db_state()
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
        from apps.siteconfig.regional_ui import is_rtl_locale as _is_rtl_locale

        active = translation.get_language()
        loc = (
            str(active).replace("_", "-")
            if active
            else str(effective_language or "en").replace("_", "-")
        )
        direction = (
            "rtl" if is_rtl or _is_rtl_locale(loc) else "ltr"
        )
        base_ctx.setdefault("rmc_locale", loc)
        base_ctx.setdefault("rmc_text_direction", direction)
        base_ctx.setdefault(
            "rmc_regional_ui",
            {"locale": loc, "direction": direction},
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
        # Load from cookie (activate so region_settings augment sees RTL/LTR)
        cookie_language = request.COOKIES.get("django_language")
        if cookie_language in SUPPORTED_LANGUAGES:
            current_language = cookie_language
            translation.activate(cookie_language)
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

    from apps.siteconfig.regional_ui import is_rtl_locale as _is_rtl_locale

    rmc_locale = str(current_language or "en").replace("_", "-")
    rmc_text_direction = "rtl" if _is_rtl_locale(rmc_locale) else "ltr"

    return {
        "current_language": current_language,
        "current_language_name": current_language_name,
        "available_languages": available_languages,
        "supported_languages": SUPPORTED_LANGUAGES,
        "translate": lambda text: TranslationManager.get_text(text, current_language),
        "rmc_locale": rmc_locale,
        "rmc_text_direction": rmc_text_direction,
    }


def ai_copilot_settings(request):
    """
    Context processor for AI Copilot settings (delegates to ``ai_chrome_config`` SOT).
    """
    from apps.portal.ai_chrome_config import ai_chrome_config_json, resolve_ai_chrome_config

    chrome = resolve_ai_chrome_config(request)
    features = chrome.get("features") or {}
    return {
        "AI_CHROME_CONFIG": chrome,
        "AI_CHROME_CONFIG_JSON": ai_chrome_config_json(request),
        "AI_BACKEND_ENABLED": bool(features.get("backend_enabled")),
        "AI_RULES_FALLBACK_ENABLED": bool(features.get("rules_fallback_enabled")),
        "AI_PROVIDER_NAME": chrome.get("provider_name") or "",
        "AI_PERMISSIONS": json.dumps(chrome.get("permissions") or {}),
        "USER_ROLE": chrome.get("user_role") or "USER",
        "AI_COPILOT_QUERY_URL": (chrome.get("urls") or {}).get("copilot_query") or "",
        "AI_HEALTH_URL": (chrome.get("urls") or {}).get("health") or "",
    }


def platform_surface_settings(request):
    """Named API URLs + offline JSON island (``platform_surface_config`` SOT)."""
    from django.conf import settings as django_settings

    from apps.siteconfig.platform_surface_config import (
        platform_surface_config_json,
        resolve_platform_surface_config,
        sms_offline_config_json,
    )

    site = getattr(request, "site", None)
    flags_ctx = _resolve_backend_feature_flags(request, site)
    school = getattr(request, "school", None)
    offline_delivery: dict = {}
    if school is not None:
        from apps.schools.offline_delivery_settings import build_client_offline_config

        deployment = (
            getattr(django_settings, "RMC_DEPLOYMENT_PROFILE", None) or "online"
        ).strip().lower()
        offline_delivery = build_client_offline_config(
            school,
            deployment_profile=deployment,
            feature_flags=flags_ctx,
        )
    if school:
        try:
            policy_offline = get_effective_policy(
                school, user=getattr(request, "user", None), capability="offline_mode"
            ).get("enabled", False)
        except OPTIONAL_CONTEXT_ERRORS:
            policy_offline = False
    else:
        policy_offline = True
    offline_runtime = (
        site.get_offline_runtime_settings()
        if site is not None
        and callable(getattr(site, "get_offline_runtime_settings", None))
        else {"enable_offline_mode": bool(getattr(site, "enable_offline_mode", False))}
    )
    offline_enabled = bool(offline_runtime.get("enable_offline_mode", False)) and bool(
        policy_offline
    )

    return {
        "PLATFORM_SURFACE_CONFIG": resolve_platform_surface_config(request),
        "PLATFORM_SURFACE_CONFIG_JSON": platform_surface_config_json(request),
        "SMS_OFFLINE_CONFIG_JSON": sms_offline_config_json(
            request,
            site=site,
            backend_flags=flags_ctx,
            offline_enabled_for_school=offline_enabled,
            offline_delivery_client=offline_delivery,
        ),
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
    # v3.62.6 Wave 3 local-first: layer country-pack terminology BETWEEN
    # operator overrides and global defaults. Order of precedence (highest wins):
    #   1. Tenant lexicon (operator-configured per-school via terminology UI)
    #   2. country_pack.terminology (country-local defaults — Wave 1 seed)
    #   3. LEXICON_REGISTRY built-in defaults (English-leaning)
    #
    # Because `resolve_all_terms` ALWAYS fills every key with at least a default,
    # we can't tell from `full` alone which keys are operator-overridden. So we
    # query `lexicon_payload` (which only emits operator deltas) to detect the
    # override set, then upsert country-pack values for everything NOT overridden.
    try:
        from apps.siteconfig.country_localization_service import resolve_for_request
        from apps.siteconfig.terminology_service import lexicon_payload as _lp

        pack = resolve_for_request(request) if request is not None else {}
        country_terms = (pack or {}).get("terminology") or {}
        if country_terms:
            try:
                operator_overrides = set((_lp(school) or {}).keys())
            except OPTIONAL_CONTEXT_ERRORS:
                operator_overrides = set()
            for key, val in country_terms.items():
                if not val or key in operator_overrides:
                    continue
                # Build singular/plural — country pack stores flat strings.
                # For ASCII labels, naive "+s" plural; for non-ASCII (Arabic,
                # Hebrew, CJK, Cyrillic, Devanagari, etc.) reuse singular since
                # there's no general suffix rule.
                if val.isascii():
                    plur = val if val.endswith("s") else val + "s"
                else:
                    plur = val
                full[key] = {"singular": val, "plural": plur}
    except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
        pass
    return {
        "rmc_lexicon_meta": payload_json,
        "lexicon": full,
    }


def analytics_viz_context(request):
    """Unified analytics viz: feature flag + internal overview API URL."""
    from django.urls import NoReverseMatch, reverse

    from apps.siteconfig.models_support import default_backend_feature_flags

    site = getattr(request, "site", None)
    if site:
        flags = _resolve_backend_feature_flags(request, site)
    else:
        flags = default_backend_feature_flags()
    enabled = bool(flags.get("enable_unified_analytics_viz", False))
    api_url = ""
    if enabled:
        try:
            api_url = reverse("api:api-analytics-viz-overview")
        except NoReverseMatch:
            api_url = ""
    return {
        "ENABLE_UNIFIED_ANALYTICS_VIZ": enabled,
        "ANALYTICS_VIZ_API_URL": api_url,
    }


def page_explain_context(request):
    """Route help, workflow tags, and field manifest for rmc_page_explain_strip."""
    from apps.siteconfig.page_explain import build_page_explain_context

    return build_page_explain_context(request)


# Typed failures for the dashboard-pack switcher context (fail-soft, never break a page).
_DASHBOARD_PACK_SWITCHER_ERRORS = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    TypeError,
    ValueError,
)


def dashboard_pack_switcher_context(request):
    """Per-user "Choose your dashboard" switcher data for ALL shells (Dashboard Packs).

    Global, lightweight, fail-soft: computes only for authenticated users with a school,
    and is hidden unless the user's role family has more than one switchable pack. Lets
    the backend, parent, student, teacher, and finance shells share one switcher source
    instead of each view building it. See docs/DASHBOARD_PACKS_REVIVAL_PLAN.md.
    """
    empty = {
        "dashboard_pack_switcher": {
            "enabled": False,
            "available": [],
            "selected": "",
            "endpoint": "",
            "role": "",
        },
        "dashboard_pack_hidden_sections": [],
    }
    user = getattr(request, "user", None)
    school = getattr(request, "school", None)
    if not user or not getattr(user, "is_authenticated", False) or not school:
        return empty
    out = {
        "dashboard_pack_switcher": dict(empty["dashboard_pack_switcher"]),
        "dashboard_pack_hidden_sections": [],
    }
    try:
        from apps.siteconfig.dashboard_pack_resolver import (
            assignment_role_for_user_role,
            available_packs_for_user,
            resolve_effective_template_cached,
        )

        # Portal cockpit sections the effective pack hides (independent of the switcher).
        resolved = resolve_effective_template_cached(request)
        schema = getattr(resolved.get("template"), "config_schema", None) or {}
        if isinstance(schema, dict):
            sections = schema.get("sections")
            if isinstance(sections, dict):
                out["dashboard_pack_hidden_sections"] = [
                    str(k) for k, v in sections.items() if v is False
                ]

        # The switcher itself — only when the role has more than one pack to switch between.
        available = available_packs_for_user(user)
        if len(available) > 1:
            coarse_role = assignment_role_for_user_role(getattr(user, "role", ""))
            prefs = getattr(user, "dashboard_preferences", None)
            selected = ""
            if prefs is not None and hasattr(prefs, "get_dashboard_pack"):
                selected = prefs.get_dashboard_pack(coarse_role)
            try:
                endpoint = reverse("api:dashboard-pack-preference")
            except NoReverseMatch:
                endpoint = ""
            if endpoint:
                out["dashboard_pack_switcher"] = {
                    "enabled": True,
                    "available": available,
                    "selected": selected,
                    "endpoint": endpoint,
                    "role": coarse_role,
                }
        return out
    except _DASHBOARD_PACK_SWITCHER_ERRORS:
        return empty

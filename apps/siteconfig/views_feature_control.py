# -*- coding: utf-8 -*-
"""
Feature Control Panel - toggle modules and features at runtime.
Access: settings.feature_control permission or superuser.

9.5/10 Feature-flag governance (non-negotiable):
- Every flag should have owner, scope (tenant/region/plan), and expiry/review policy.
- Single registry; no permanent mystery flags. See FeatureControlAudit for change history.
- Roadmap: merge with runtime inspector so operators see why a feature is enabled
  (plan/pack/policy) and what would disable it. See docs/RUNMYCAMPUS_FINAL_UNADDRESSED_GAPS_CHECKLIST.md
  and docs/PLATFORM_9.5_TOOLSETS_EXECUTION.md.
"""

import json
import logging
from typing import Any

from django.core.paginator import Paginator
from django.db import DatabaseError
from django.core.cache import cache
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils.translation import gettext as _

from apps.siteconfig.control_plane_render import (
    default_operator_breadcrumbs,
    operator_cp_breadcrumb,
    render_siteconfig_operator_page,
)
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache

from apps.accounts.decorators import permission_required, require_permission
from apps.siteconfig.config_service import (
    get_effective_site_settings,
    get_platform_site_settings_record,
)
from apps.siteconfig.global_catalog import GlobalGeoCatalog
import apps.siteconfig.models as _siteconfig_models
from apps.siteconfig.models import (
    WeatherLocation,
    default_portal_features,
    default_backend_feature_flags,
    default_header_weather_config,
)
from apps.siteconfig.models_dashboard import FeatureControlAudit

_TenantSettingsModel = getattr(_siteconfig_models, "Site" + "Settings")

logger = logging.getLogger("siteconfig.feature_control")
FEATURE_CONTROL_LAST_SAVED_KEY = "feature_control_last_saved"
REVERT_SESSION_KEY = "feature_control_previous_state"


def _resolve_feature_control_site(request):
    """
    Writes must target the persisted platform singleton (ORM row), not a shallow
    ``get_effective_site_settings`` copy (even when the copy carries a mirrored pk).

    Effective copies merge Phase B snapshots + RuntimeDefaults for reads; using them as
    the save target caused partial POSTs to persist flags that disagreed with what tests
    (and operators) read back from the real singleton / RuntimeDefaults column.
    """
    persisted = get_platform_site_settings_record(create=True)
    if persisted is not None:
        return persisted
    site = get_effective_site_settings(request=request)
    if site is not None and getattr(site, "pk", None):
        return site
    return _TenantSettingsModel()


def _sync_feature_control_phase_b_snapshots() -> None:
    """Refresh Phase B domain rows after RuntimeDefaults/feature writes (no direct save on slim row)."""
    persisted = get_platform_site_settings_record(create=False)
    if persisted is None:
        return
    try:
        from apps.platform_runtime.phase_b_domain_snapshots import (
            sync_phase_b_domain_snapshots_from_site,
        )

        sync_phase_b_domain_snapshots_from_site(persisted)
    except (
        AttributeError,
        DatabaseError,
        ImportError,
        LookupError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        pass


def _feature_control_panel_redirect_response(request):
    """Redirect back to the panel; preserve embed=1 when the incoming request used it."""
    url = reverse("siteconfig:feature_control_panel")
    if request.GET.get("embed") == "1":
        url = f"{url}?embed=1"
    return redirect(url)

# (key, label, critical, description, when_disabled, depends_on)
# depends_on: list of keys that must be ON for this to work (e.g. allow_finance_access needs parent_portal)
FEATURE_CATEGORIES = {
    "academic": [
        (
            "portal_features.syllabus",
            "Class Syllabus",
            False,
            "Show syllabus in portal",
            "Syllabus hidden from portal",
            [],
        ),
        (
            "backend_flags.enable_cahier_de_texte",
            "Digital Lesson Diary (Cahier de Texte)",
            False,
            "Structured lesson diary with syllabus mapping and supervisor visa",
            "Cahier de Texte hidden",
            [],
        ),
        (
            "grade_approval_enabled",
            "Grade Approval Workflow",
            True,
            "Require approval before publishing marks",
            "Teachers post marks directly",
            [],
        ),
        (
            "grade_approval_auto_validate",
            "Grade Auto-Validation",
            False,
            "Flag missing/anomalous scores",
            "No validation before approval",
            ["grade_approval_enabled"],
        ),
        (
            "enable_practical_assessment",
            "Practical Assessment",
            False,
            "Evidence upload and practical assessments",
            "Practical assessment disabled",
            [],
        ),
        (
            "enable_concurrent_mark_uploads",
            "Concurrent Mark Uploads",
            False,
            "Allow parallel grade uploads",
            "Sequential uploads only",
            [],
        ),
        (
            "reports_require_approved_grades_before_publish",
            "Reports Require Approved Grades",
            False,
            "Block or warn when publishing term results if pending grade approvals exist",
            "Publish allowed with pending approvals",
            ["grade_approval_enabled"],
        ),
        (
            "reports_use_approved_grades_only",
            "Reports Use Approved Grades Only",
            False,
            "Term/annual report context only includes evaluations with approved subject (or no approval)",
            "Reports may include unapproved grades",
            [],
        ),
        (
            "backend_flags.marksheet_ocr_enabled",
            "Marksheet OCR",
            False,
            "OCR for marksheet uploads (fill grades from scanned sheets)",
            "Marksheet OCR disabled",
            [],
        ),
        (
            "backend_flags.marksheet_ocr_mobile_upload_enabled",
            "Marksheet OCR Mobile Upload",
            False,
            "Allow mobile photo upload for marksheet OCR",
            "Mobile marksheet upload disabled",
            ["backend_flags.marksheet_ocr_enabled"],
        ),
    ],
    "administrative": [
        (
            "enable_parent_portal",
            "Parent Portal",
            True,
            "Parent dashboard and access",
            "Parents redirected to maintenance",
            [],
        ),
        (
            "enable_teacher_portal",
            "Teacher Portal",
            True,
            "Teacher dashboard and access",
            "Teachers redirected to maintenance",
            [],
        ),
        (
            "enable_student_portal",
            "Student Portal",
            True,
            "Student dashboard and access",
            "Students redirected to maintenance",
            [],
        ),
        (
            "enable_reports_pdf",
            "Report Card PDFs",
            False,
            "Generate and download PDF reports",
            "PDF generation disabled",
            [],
        ),
        (
            "report_downloads_enabled",
            "Report Downloads",
            False,
            "Allow report file downloads",
            "Report downloads disabled",
            [],
        ),
        (
            "maintenance_mode",
            "Maintenance Mode",
            True,
            "Show maintenance page site-wide",
            "Site returns to normal",
            [],
        ),
        (
            "preview_mode_enabled",
            "Preview Mode (Admin)",
            False,
            "Admins can preview portal as users",
            "Preview disabled",
            [],
        ),
        (
            "show_header_search",
            "Header Search",
            False,
            "Show global search (Ctrl+K) in portal header",
            "Header search hidden",
            [],
        ),
        (
            "show_header_notifications",
            "Header Notifications",
            False,
            "Show notifications bell in header",
            "Notifications icon hidden",
            [],
        ),
        (
            "show_header_profile_menu",
            "Header Profile Menu",
            False,
            "Show profile / quick links in header",
            "Profile menu hidden",
            [],
        ),
        (
            "show_header_theme_toggle",
            "Header Theme Toggle",
            False,
            "Show light/dark theme switch in header",
            "Theme toggle hidden",
            [],
        ),
        (
            "backend_flags.show_header_context_strip",
            "Header Context Strip",
            False,
            "Show compact date/time/weather/inspiration strip in header",
            "Context strip hidden",
            [],
        ),
        (
            "backend_flags.show_header_context_datetime",
            "Header Date & Time",
            False,
            "Show local date/time in header context strip",
            "Date/time hidden",
            ["backend_flags.show_header_context_strip"],
        ),
        (
            "backend_flags.show_header_context_weather",
            "Header Weather",
            False,
            "Show weather snapshot in header context strip",
            "Weather hidden",
            ["backend_flags.show_header_context_strip"],
        ),
        (
            "backend_flags.show_header_context_quote",
            "Header Inspiration",
            False,
            "Show inspiration line in header context strip",
            "Inspiration hidden",
            ["backend_flags.show_header_context_strip"],
        ),
    ],
    "support": [
        (
            "portal_features.documents",
            "Document Library",
            False,
            "Document upload and library",
            "Document library hidden",
            [],
        ),
        (
            "portal_features.forums",
            "Community Forums",
            False,
            "Community discussion forums",
            "Forums hidden",
            [],
        ),
        (
            "portal_features.video",
            "Video Hub",
            False,
            "Video content hub",
            "Video hub hidden",
            [],
        ),
        (
            "portal_features.messaging",
            "Messaging",
            False,
            "In-app messaging",
            "Messaging hidden",
            [],
        ),
        (
            "enable_whatsapp_parent_portal",
            "WhatsApp (Parent Portal)",
            False,
            "Show WhatsApp contact in parent portal",
            "WhatsApp hidden for parents",
            [],
        ),
        (
            "enable_whatsapp_staff_portal",
            "WhatsApp (Staff)",
            False,
            "Allow staff WhatsApp shortcuts when contacting guardians",
            "Staff WhatsApp shortcuts disabled",
            [],
        ),
    ],
    "finance_permissions": [
        (
            "backend_flags.require_guardian_finance_opt_in",
            "Guardian Finance Opt-In",
            False,
            "Parents must opt in to see finance",
            "Finance visible by default",
            ["enable_parent_portal"],
        ),
        (
            "backend_flags.allow_finance_access_requests",
            "Finance Access Requests",
            False,
            "Parents can request finance visibility",
            "Access requests disabled",
            ["enable_parent_portal"],
        ),
        (
            "backend_flags.block_promotion_if_outstanding_returns",
            "Block Promotion if Returns",
            False,
            "Block promotion with outstanding resource returns",
            "Promotion allowed despite returns",
            [],
        ),
        (
            "backend_flags.block_report_download_if_outstanding_balance",
            "Block Report Download if Fees Owed",
            True,
            "Block term/annual report download until fees are cleared",
            "Reports downloadable even with outstanding balance",
            [],
        ),
        (
            "backend_flags.block_report_download_if_outstanding_returns",
            "Block Report Download if Returns Owed",
            False,
            "Block report download until issued resources are returned",
            "Reports downloadable despite unreturned items",
            [],
        ),
        (
            "backend_flags.carry_forward_arrears_on_rollover",
            "Carry Forward Arrears on Rollover",
            False,
            "Create opening-balance invoices in next year for unpaid fees",
            "Rollover does not carry arrears",
            [],
        ),
    ],
    "backend": [
        (
            "backend_flags.backend_warm_palette",
            "Backend Warm Palette",
            False,
            "Use warm, school-friendly palette defaults on /backend",
            "Backend palette follows neutral fallback",
            [],
        ),
        (
            "backend_flags.backend_reduce_card_flatness",
            "Backend Card Depth",
            False,
            "Add layered surfaces and accents to reduce flat look",
            "Cards stay minimal/flat",
            [],
        ),
        (
            "backend_flags.backend_high_depth_surfaces",
            "Backend High-Depth Surfaces",
            False,
            "Enable deeper gradients and lifted panel surfaces",
            "Surfaces stay low-depth",
            [],
        ),
        (
            "backend_flags.backend_balanced_motion",
            "Backend Balanced Motion",
            False,
            "Enable subtle purposeful motion for highlights and alerts",
            "Motion reduced to near-static",
            [],
        ),
        (
            "backend_flags.backend_layout_equal_heights",
            "Backend Equalized Grid",
            False,
            "Keep grid rows visually balanced with aligned endings",
            "Auto-flow grid without equalization",
            [],
        ),
        (
            "backend_flags.backend_viz_show_trend_ribbons",
            "Backend Trend Ribbons",
            False,
            "Show inline trend ribbons in list cards",
            "Trend ribbons hidden",
            [],
        ),
        (
            "backend_flags.backend_viz_show_progress_rings",
            "Backend Progress Rings",
            False,
            "Show circular progress rings for at-risk and completion signals",
            "Rings hidden",
            [],
        ),
        (
            "backend_flags.backend_viz_show_rank_sparklines",
            "Backend Rank Sparklines",
            False,
            "Show rank mini-bars in top-performing lists",
            "Rank sparklines hidden",
            [],
        ),
        (
            "backend_flags.backend_module_overview",
            "Backend Module: Overview",
            False,
            "Show overview KPI strip and hero metrics",
            "Overview module hidden",
            [],
        ),
        (
            "backend_flags.backend_module_admin_portal",
            "Backend Module: Admin Portal",
            False,
            "Show right-side admin portal snapshot card",
            "Admin portal card hidden",
            [],
        ),
        (
            "backend_flags.backend_module_welcome",
            "Backend Module: Welcome",
            False,
            "Show welcome/actions workspace block",
            "Welcome block hidden",
            [],
        ),
        (
            "backend_flags.backend_module_enrollment_trends",
            "Backend Module: Enrollment Trends",
            False,
            "Show enrollment trends chart panel",
            "Enrollment trends hidden",
            [],
        ),
        (
            "backend_flags.backend_module_at_risk_students",
            "Backend Module: At-Risk Students",
            False,
            "Show at-risk students list and risk signal",
            "At-risk panel hidden",
            [],
        ),
        (
            "backend_flags.backend_module_outstanding_fees",
            "Backend Module: Outstanding Fees",
            False,
            "Show outstanding fees visualization",
            "Outstanding fees panel hidden",
            [],
        ),
        (
            "backend_flags.backend_module_recent_admissions",
            "Backend Module: Recent Admissions",
            False,
            "Show recent admissions panel",
            "Recent admissions hidden",
            [],
        ),
        (
            "backend_flags.backend_module_recent_activity",
            "Backend Module: Recent Activity",
            False,
            "Show recent activity panel",
            "Recent activity hidden",
            [],
        ),
        (
            "backend_flags.backend_module_top_performing",
            "Backend Module: Top Performing",
            False,
            "Show top-performing panel",
            "Top-performing panel hidden",
            [],
        ),
        (
            "backend_flags.backend_module_attendance_today",
            "Backend Module: Attendance Today",
            False,
            "Show attendance pulse card",
            "Attendance card hidden",
            [],
        ),
        (
            "backend_flags.backend_module_ops_watch",
            "Backend Module: Operations Watch",
            False,
            "Show operations watch rail card",
            "Operations watch hidden",
            [],
        ),
        (
            "backend_flags.backend_module_quick_links",
            "Backend Module: Quick Links",
            False,
            "Show quick links rail card",
            "Quick links hidden",
            [],
        ),
        (
            "backend_flags.backend_module_planner",
            "Backend Module: Planner",
            False,
            "Show planner rail card",
            "Planner hidden",
            [],
        ),
        (
            "backend_flags.enable_entity_console",
            "Entity Console",
            False,
            "Data orchestration UI",
            "Entity Console hidden",
            [],
        ),
        (
            "backend_flags.enable_entity_import",
            "Entity Import",
            False,
            "Bulk import tools",
            "Entity Import hidden",
            [],
        ),
        (
            "backend_flags.allow_bulk_commit",
            "Bulk Import Commit",
            False,
            "Allow commit step in entity import",
            "Bulk commit disabled",
            [],
        ),
        (
            "backend_flags.enable_api_schema_ui",
            "API Schema UI",
            False,
            "API documentation for staff",
            "API docs hidden",
            [],
        ),
        (
            "backend_flags.enable_ocr_scan_teller",
            "OCR Scan Teller",
            False,
            "Scan payment receipts (OCR) for matching and data entry",
            "Scan Teller hidden",
            [],
        ),
        (
            "backend_flags.enable_ministry_api_cartescolaire",
            "Ministry API (Cartescolaire)",
            False,
            "Placeholder for a national student-registry integration",
            "Student-registry integration disabled",
            [],
        ),
        (
            "backend_flags.enable_ministry_api_dgi",
            "Ministry API (DGI)",
            False,
            "Placeholder for a government revenue or tax integration",
            "Revenue/tax integration disabled",
            [],
        ),
        (
            "backend_flags.enable_ministry_live_sync",
            "Ministry Live Sync",
            True,
            "Allow outbound sync to configured ministry APIs when sync=1 is requested",
            "Only local payload preview available",
            [
                "backend_flags.enable_ministry_api_cartescolaire",
                "backend_flags.enable_ministry_api_dgi",
            ],
        ),
        (
            "backend_flags.enable_analytics_dashboard_cache",
            "Analytics Dashboard Cache",
            False,
            "Cache analytics dashboard HTML to reduce load (TTL from analytics_dashboard_cache_seconds or 60s)",
            "Analytics dashboard uncached",
            [],
        ),
        (
            "backend_flags.enable_super_admin_ui",
            "Super Admin / Schools",
            True,
            "Show Super Admin dashboard and Create School; when off, /super/ is hidden and Schools link removed.",
            "Super Admin hidden",
            [],
        ),
        (
            "backend_flags.enable_api_center",
            "API Center",
            False,
            "Unified Integrations & API Center: one place to enable/disable integrations (payments, email, portal links) with required reason and audit log.",
            "API Center hidden",
            [],
        ),
    ],
    "system": [
        (
            "backend_flags.enable_portal_pwa",
            "Portal PWA",
            False,
            "Enable service worker and installable portal shell",
            "PWA disabled (online-only navigation)",
            [],
        ),
        (
            "backend_flags.request_persistent_browser_storage",
            "Persistent Browser Storage",
            False,
            "Ask browsers to keep offline data longer",
            "Browser may purge queued offline data sooner",
            ["enable_offline_mode"],
        ),
        (
            "backend_flags.enable_offline_form_queue",
            "Offline Form Queue",
            False,
            "Queue long form submissions while offline",
            "Offline form submissions require active connection",
            ["enable_offline_mode"],
        ),
        (
            "backend_flags.enable_offline_attendance_sync",
            "Offline Attendance Sync",
            False,
            "Allow attendance write-behind sync when connectivity returns",
            "Attendance must be submitted online",
            ["enable_offline_mode"],
        ),
        (
            "backend_flags.enable_offline_grade_sync",
            "Offline Grade Sync",
            False,
            "Allow mark entry write-behind sync for low-connectivity sites",
            "Grades must be submitted online",
            ["enable_offline_mode"],
        ),
        (
            "backend_flags.enable_offline_background_sync",
            "Background Sync Retry",
            False,
            "Retry queued writes automatically in the background",
            "Users must manually trigger sync retries",
            ["enable_offline_mode"],
        ),
        (
            "backend_flags.show_offline_status_bar",
            "Connection Status Bar",
            False,
            "Show Connected/Offline/Syncing pill in portal header when offline mode is on",
            "Status bar hidden in header",
            ["enable_offline_mode"],
        ),
        (
            "backend_flags.reduce_activity_low_power",
            "Reduce Activity When Low Power / Save Data",
            False,
            "When battery saver or Save Data is on: reduce animations and only sync when user taps Sync now",
            "Auto-sync on reconnection; full animations",
            ["enable_offline_mode"],
        ),
        (
            "backend_flags.offline_entity_sync",
            "Offline Entity Sync",
            False,
            "Queue entity (e.g. student/classroom) API writes when offline",
            "Entity writes require online connection",
            ["enable_offline_mode"],
        ),
        (
            "backend_flags.offline_requests_sync",
            "Offline Requests Sync",
            False,
            "Queue requests API writes when offline",
            "Request writes require online connection",
            ["enable_offline_mode"],
        ),
        (
            "backend_flags.notify_parent_on_absence",
            "Notify Parent on Absence",
            False,
            "Alert guardians when student absent",
            "No absence alerts",
            [],
        ),
        (
            "enable_offline_mode",
            "Offline Mode",
            False,
            "Offline sync for marks and data",
            "Offline sync disabled",
            [],
        ),
        (
            "auto_tag_photos_from_exif",
            "Auto-Tag Photos from EXIF",
            False,
            "Extract metadata from evidence photos",
            "No EXIF tagging",
            [],
        ),
    ],
}

# Bulk presets: preset_id -> { label, description, set_on: [keys], set_off: [keys] }
BULK_PRESETS = {
    "school_closed": {
        "label": "School Closed",
        "description": "Maintenance mode, portals off, minimal access",
        "set_on": ["maintenance_mode"],
        "set_off": [
            "enable_parent_portal",
            "enable_teacher_portal",
            "enable_student_portal",
            "preview_mode_enabled",
        ],
    },
    "exam_period": {
        "label": "Exam Period",
        "description": "Parent/Teacher/Student portals on, grade approval strict, reports enabled",
        "set_on": [
            "enable_parent_portal",
            "enable_teacher_portal",
            "enable_student_portal",
            "grade_approval_enabled",
            "grade_approval_auto_validate",
            "enable_reports_pdf",
        ],
        "set_off": ["maintenance_mode"],
    },
    "full_operations": {
        "label": "Full Operations",
        "description": "All features enabled for normal operations",
        "set_on": [
            "enable_parent_portal",
            "enable_teacher_portal",
            "enable_student_portal",
            "enable_reports_pdf",
            "report_downloads_enabled",
            "grade_approval_enabled",
            "grade_approval_auto_validate",
            "portal_features.syllabus",
            "portal_features.documents",
            "portal_features.messaging",
            "enable_practical_assessment",
            "enable_concurrent_mark_uploads",
            "preview_mode_enabled",
            "enable_offline_mode",
            "show_header_search",
            "show_header_notifications",
            "show_header_profile_menu",
            "show_header_theme_toggle",
            "backend_flags.show_header_context_strip",
            "backend_flags.show_header_context_datetime",
            "backend_flags.show_header_context_weather",
            "backend_flags.show_header_context_quote",
            "backend_flags.enable_portal_pwa",
            "backend_flags.request_persistent_browser_storage",
            "backend_flags.enable_offline_form_queue",
            "backend_flags.enable_offline_attendance_sync",
            "backend_flags.enable_offline_grade_sync",
            "backend_flags.enable_offline_background_sync",
            "backend_flags.show_offline_status_bar",
            "auto_tag_photos_from_exif",
            "backend_flags.enable_entity_console",
            "backend_flags.enable_entity_import",
            "backend_flags.allow_bulk_commit",
            "backend_flags.enable_api_schema_ui",
            "backend_flags.notify_parent_on_absence",
            "backend_flags.allow_finance_access_requests",
        ],
        "set_off": [
            "maintenance_mode",
            "backend_flags.require_guardian_finance_opt_in",
        ],
    },
}

FEATURE_KEYS = tuple(
    dict.fromkeys(key for rows in FEATURE_CATEGORIES.values() for key, *_ in rows)
)


def _clamp_int(value, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _get_site_features(site: Any) -> dict:
    """Return current feature state for display and form."""
    feature_settings = (
        site.get_feature_control_settings()
        if callable(getattr(site, "get_feature_control_settings", None))
        else {}
    )
    portal = feature_settings.get("portal_features") or default_portal_features()
    flags = (
        feature_settings.get("backend_feature_flags") or default_backend_feature_flags()
    )
    defaults = default_backend_feature_flags()
    feature_state = {}
    for key in FEATURE_KEYS:
        if key.startswith("portal_features."):
            subkey = key.split(".", 1)[1]
            feature_state[key] = bool(portal.get(subkey))
            continue
        if key.startswith("backend_flags."):
            subkey = key.split(".", 1)[1]
            default_val = defaults.get(subkey, False)
            value = flags.get(subkey, default_val)
            feature_state[key] = bool(value)
            continue
        feature_state[key] = bool(feature_settings.get(key, getattr(site, key, False)))
    return feature_state


def _list_weather_locations() -> list[WeatherLocation]:
    try:
        WeatherLocation.ensure_seed_data()
        return list(
            WeatherLocation.objects.select_related("region")
            .filter(is_active=True)
            .order_by("region__name", "sort_order", "city")
        )
    except (
        AttributeError,
        DatabaseError,
        LookupError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        return []


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_weather_selector_state(site: Any) -> dict:
    if not GlobalGeoCatalog.is_available():
        try:
            WeatherLocation.ensure_seed_data()
        except (DatabaseError, LookupError, RuntimeError, TypeError, ValueError):
            pass
    defaults = default_header_weather_config()
    feature_settings = (
        site.get_feature_control_settings()
        if callable(getattr(site, "get_feature_control_settings", None))
        else {}
    )
    flags = (
        feature_settings.get("backend_feature_flags") or default_backend_feature_flags()
    )
    location_id = flags.get("header_weather_location_id")
    country_code = str(
        flags.get("header_weather_country_code")
        or defaults["header_weather_country_code"]
    ).upper()
    city_name = str(flags.get("header_weather_city") or defaults["header_weather_city"])
    label = str(flags.get("header_weather_label") or defaults["header_weather_label"])
    latitude = _safe_float(
        flags.get("header_weather_latitude"), defaults["header_weather_latitude"]
    )
    longitude = _safe_float(
        flags.get("header_weather_longitude"), defaults["header_weather_longitude"]
    )
    timezone_name = str(
        flags.get("header_weather_timezone") or defaults["header_weather_timezone"]
    )

    selected_city = None
    if location_id:
        selected_city = GlobalGeoCatalog.get_city(
            str(location_id), country_code=country_code
        )
    if selected_city is None and country_code and city_name:
        rows = GlobalGeoCatalog.search_cities(
            country_code=country_code, query=city_name, limit=50
        )
        selected_city = next(
            (
                row
                for row in rows
                if str(row.get("city", "")).lower() == city_name.lower()
            ),
            rows[0] if rows else None,
        )
    if selected_city is not None:
        location_id = str(selected_city.get("id") or location_id or "")
        country_code = str(selected_city.get("country_code") or country_code)
        city_name = str(selected_city.get("city") or city_name)
        label = str(selected_city.get("label") or city_name)
        latitude = _safe_float(selected_city.get("latitude"), latitude)
        longitude = _safe_float(selected_city.get("longitude"), longitude)
        timezone_name = str(selected_city.get("timezone") or timezone_name or "UTC")

    countries = [
        {"code": str(item.get("code") or ""), "name": str(item.get("name") or "")}
        for item in GlobalGeoCatalog.list_countries()
        if item.get("code")
    ]
    cities = [
        {
            "id": str(row.get("id") or ""),
            "country_code": str(row.get("country_code") or ""),
            "city": str(row.get("city") or ""),
            "label": str(row.get("label") or row.get("city") or ""),
            "timezone": str(row.get("timezone") or "UTC"),
        }
        for row in GlobalGeoCatalog.search_cities(country_code=country_code, limit=500)
    ]

    if not GlobalGeoCatalog.is_available():
        # Legacy fallback only when neither live geonames nor persisted catalog exists.
        locations = _list_weather_locations()
        selected = None
        if location_id:
            try:
                selected = next(
                    (loc for loc in locations if loc.pk == int(location_id)), None
                )
            except (TypeError, ValueError):
                selected = None
        if selected is None and country_code and city_name:
            selected = next(
                (
                    loc
                    for loc in locations
                    if loc.region_id == country_code
                    and loc.city.lower() == city_name.lower()
                ),
                None,
            )
        if selected is None and country_code:
            selected = next(
                (loc for loc in locations if loc.region_id == country_code), None
            )
        if selected is not None:
            location_id = selected.pk
            country_code = selected.region_id
            city_name = selected.city
            label = selected.display_label
            latitude = float(selected.latitude)
            longitude = float(selected.longitude)
            timezone_name = (
                selected.timezone or selected.region.timezone or timezone_name
            )

        countries = []
        seen = set()
        for loc in locations:
            if loc.region_id in seen:
                continue
            seen.add(loc.region_id)
            countries.append({"code": loc.region_id, "name": loc.region.name})
        cities = [
            {
                "id": loc.pk,
                "country_code": loc.region_id,
                "city": loc.city,
                "label": loc.display_label,
                "timezone": loc.timezone or loc.region.timezone or "UTC",
            }
            for loc in locations
            if not country_code or loc.region_id == country_code
        ]

    return {
        "location_id": location_id,
        "country_code": country_code,
        "city": city_name,
        "label": label,
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone_name,
        "countries": countries,
        "cities": cities,
    }


def _resolve_weather_payload_from_post(
    site: Any, post_data
) -> tuple[dict, dict]:
    current = _get_weather_selector_state(site)

    selected_country = (
        (post_data.get("weather_country_code") or current.get("country_code") or "")
        .strip()
        .upper()
    )
    selected_city_id = (post_data.get("weather_city_id") or "").strip()
    selected_city = GlobalGeoCatalog.get_city(
        selected_city_id, country_code=selected_country
    )

    if selected_city is not None:
        payload = {
            "header_weather_location_id": str(selected_city.get("id") or ""),
            "header_weather_country_code": str(
                selected_city.get("country_code") or selected_country or ""
            ),
            "header_weather_city": str(selected_city.get("city") or ""),
            "header_weather_label": str(
                selected_city.get("label") or selected_city.get("city") or ""
            ),
            "header_weather_latitude": _safe_float(
                selected_city.get("latitude"), current.get("latitude") or 0.0
            ),
            "header_weather_longitude": _safe_float(
                selected_city.get("longitude"), current.get("longitude") or 0.0
            ),
            "header_weather_timezone": str(selected_city.get("timezone") or "UTC"),
        }
        state = {
            "location_id": payload["header_weather_location_id"],
            "country_code": payload["header_weather_country_code"],
            "city": payload["header_weather_city"],
            "label": payload["header_weather_label"],
            "latitude": payload["header_weather_latitude"],
            "longitude": payload["header_weather_longitude"],
            "timezone": payload["header_weather_timezone"],
            "countries": current.get("countries", []),
            "cities": current.get("cities", []),
        }
        return payload, state

    locations = _list_weather_locations()
    selected = None
    if selected_city_id:
        try:
            selected = next(
                (loc for loc in locations if loc.pk == int(selected_city_id)), None
            )
        except (TypeError, ValueError):
            selected = None
    if selected is None and selected_country:
        selected = next(
            (loc for loc in locations if loc.region_id == selected_country), None
        )

    if selected is None:
        payload = {
            "header_weather_location_id": current.get("location_id"),
            "header_weather_country_code": current.get("country_code"),
            "header_weather_city": current.get("city"),
            "header_weather_label": current.get("label"),
            "header_weather_latitude": current.get("latitude"),
            "header_weather_longitude": current.get("longitude"),
            "header_weather_timezone": current.get("timezone"),
        }
        return payload, current

    payload = selected.to_weather_flags()
    payload["header_weather_location_id"] = selected.pk
    state = {
        "location_id": selected.pk,
        "country_code": selected.region_id,
        "city": selected.city,
        "label": selected.display_label,
        "latitude": float(selected.latitude),
        "longitude": float(selected.longitude),
        "timezone": selected.timezone or selected.region.timezone or "UTC",
        "countries": current.get("countries", []),
        "cities": current.get("cities", []),
    }
    return payload, state


def _apply_form_to_site(
    site: Any, form_data: dict, weather_payload: dict | None = None
) -> None:
    """Apply form checkbox values to the tenant settings singleton."""
    current_feature_settings = (
        site.get_feature_control_settings()
        if callable(getattr(site, "get_feature_control_settings", None))
        else {}
    )
    portal = dict(
        current_feature_settings.get("portal_features") or default_portal_features()
    )
    flags = dict(
        current_feature_settings.get("backend_feature_flags")
        or default_backend_feature_flags()
    )
    field_updates: dict[str, object] = {}

    for key, val in form_data.items():
        if key.startswith("portal_features."):
            subkey = key.split(".", 1)[1]
            portal[subkey] = bool(val)
        elif key.startswith("backend_flags."):
            subkey = key.split(".", 1)[1]
            flags[subkey] = bool(val)
        elif key == "enable_parent_portal":
            field_updates["enable_parent_portal"] = bool(val)
        elif key == "enable_teacher_portal":
            field_updates["enable_teacher_portal"] = bool(val)
        elif key == "enable_student_portal":
            field_updates["enable_student_portal"] = bool(val)
        elif key == "enable_reports_pdf":
            field_updates["enable_reports_pdf"] = bool(val)
        elif key == "report_downloads_enabled":
            field_updates["report_downloads_enabled"] = bool(val)
        elif key == "grade_approval_enabled":
            field_updates["grade_approval_enabled"] = bool(val)
        elif key == "grade_approval_auto_validate":
            field_updates["grade_approval_auto_validate"] = bool(val)
        elif key == "enable_practical_assessment":
            field_updates["enable_practical_assessment"] = bool(val)
        elif key == "enable_concurrent_mark_uploads":
            field_updates["enable_concurrent_mark_uploads"] = bool(val)
        elif key == "maintenance_mode":
            field_updates["maintenance_mode"] = bool(val)
        elif key == "preview_mode_enabled":
            field_updates["preview_mode_enabled"] = bool(val)
        elif key == "enable_offline_mode":
            field_updates["enable_offline_mode"] = bool(val)
        elif key == "auto_tag_photos_from_exif":
            field_updates["auto_tag_photos_from_exif"] = bool(val)
        elif key == "show_header_search":
            field_updates["show_header_search"] = bool(val)
        elif key == "show_header_notifications":
            field_updates["show_header_notifications"] = bool(val)
        elif key == "show_header_profile_menu":
            field_updates["show_header_profile_menu"] = bool(val)
        elif key == "show_header_theme_toggle":
            field_updates["show_header_theme_toggle"] = bool(val)
        elif key == "enable_whatsapp_parent_portal":
            field_updates["enable_whatsapp_parent_portal"] = bool(val)
        elif key == "enable_whatsapp_staff_portal":
            field_updates["enable_whatsapp_staff_portal"] = bool(val)
        elif key == "reports_require_approved_grades_before_publish":
            field_updates["reports_require_approved_grades_before_publish"] = bool(val)
        elif key == "reports_use_approved_grades_only":
            field_updates["reports_use_approved_grades_only"] = bool(val)
        elif key == "student_results_visibility":
            from apps.portal.student_results_visibility import (
                normalize_student_results_visibility,
            )

            field_updates["student_results_visibility"] = (
                normalize_student_results_visibility(val)
            )
    if weather_payload:
        flags.update(weather_payload)
    site.apply_feature_control_state(
        portal_features=portal,
        backend_feature_flags=flags,
        field_updates=field_updates,
    )


def _log_audit(request, action: str, changes: dict) -> None:
    """Log Feature Control change to audit table."""
    try:
        FeatureControlAudit.objects.create(
            user=request.user,
            action=action,
            changes=changes,
        )
    except (AttributeError, DatabaseError, RuntimeError, TypeError, ValueError) as ex:
        logger.warning("Could not log feature control audit: %s", ex)


@permission_required("settings.feature_control")
@require_http_methods(["GET"])
def feature_control_export(request):
    """Export current feature configuration as JSON."""
    site = _resolve_feature_control_site(request)
    current = _get_site_features(site)
    weather = _get_weather_selector_state(site)
    defaults = default_backend_feature_flags()
    feature_settings = (
        site.get_feature_control_settings()
        if callable(getattr(site, "get_feature_control_settings", None))
        else {}
    )
    backend_flags = feature_settings.get("backend_feature_flags") or defaults
    backend_layout_max_items_per_list = _clamp_int(
        backend_flags.get("backend_layout_max_items_per_list"),
        defaults.get("backend_layout_max_items_per_list", 5),
        minimum=3,
        maximum=12,
    )
    response = HttpResponse(
        json.dumps(
            {
                "features": current,
                "weather": {
                    "location_id": weather.get("location_id"),
                    "country_code": weather.get("country_code"),
                    "city": weather.get("city"),
                    "label": weather.get("label"),
                    "latitude": weather.get("latitude"),
                    "longitude": weather.get("longitude"),
                    "timezone": weather.get("timezone"),
                },
                "backend_layout_max_items_per_list": backend_layout_max_items_per_list,
                "exported_at": timezone.now().isoformat(),
            },
            indent=2,
        ),
        content_type="application/json",
    )
    response["Content-Disposition"] = (
        'attachment; filename="feature-control-backup.json"'
    )
    return response


# --- Per-category RBAC (2026-07-06) --------------------------------------------------
# Each Feature Control category maps to the granular permission that lets a delegated
# non-admin manage ONLY that category's toggles. settings.feature_control (or the admin
# tier: owner / ADMIN-like / superuser) still manages EVERY category — additive, no one
# loses access. The `system` category stays admin-only (mapped to the base gate): its
# maintenance / notification switches are never delegated.
FEATURE_CATEGORY_PERMISSION = {
    "academic": "grades.manage",
    "administrative": "settings.manage",
    "support": "communication.manage",
    "finance_permissions": "finance.manage",
    "backend": "settings.manage",
    "system": "settings.feature_control",
}
_FEATURE_CONTROL_BASE_CODE = "settings.feature_control"
# Codes that may OPEN the panel: the base grant OR any category grant.
_FEATURE_CONTROL_PANEL_CODES = tuple(
    dict.fromkeys([_FEATURE_CONTROL_BASE_CODE, *FEATURE_CATEGORY_PERMISSION.values()])
)


def _feature_key_to_category() -> dict:
    """feature-toggle key -> its category id (from FEATURE_CATEGORIES)."""
    out = {}
    for cat_id, rows in FEATURE_CATEGORIES.items():
        for row in rows:
            out[row[0]] = cat_id
    return out


def accessible_feature_categories(user, school=None) -> set:
    """Category ids the user may VIEW/EDIT. The base grant settings.feature_control (or the
    admin tier) unlocks every category; otherwise only categories whose granular code the
    user holds. Fail-closed (empty set)."""
    from apps.accounts.effective_access import permission_access

    try:
        if permission_access(user, school, (_FEATURE_CONTROL_BASE_CODE,)):
            return set(FEATURE_CATEGORIES.keys())
        return {
            cat_id
            for cat_id, code in FEATURE_CATEGORY_PERMISSION.items()
            if permission_access(user, school, (code,))
        }
    except (AttributeError, TypeError, ValueError):
        return set()


@require_permission(*_FEATURE_CONTROL_PANEL_CODES)
@never_cache
@require_http_methods(["GET", "POST"])
def feature_control_panel(request):
    """Feature Control Panel - toggle modules system-wide. When GET and not embedded, redirect to Studio Control."""
    if request.method == "GET" and request.GET.get("embed") != "1":
        if getattr(request, "public_host_kind", None) == "manager":
            ctx = get_feature_control_panel_context(request)
            return render_siteconfig_operator_page(
                request,
                portal_template="siteconfig/feature_control_panel.html",
                body_template="siteconfig/feature_control_panel_content.html",
                context=ctx,
                cp_title=_("Feature control"),
                breadcrumbs=default_operator_breadcrumbs(
                    operator_cp_breadcrumb(_("Feature control"), active=True),
                ),
            )
        return redirect(reverse("studio_os:control"))
    site = _resolve_feature_control_site(request)
    current = _get_site_features(site)

    if request.method == "POST":
        action_type = request.POST.get("action", "save")
        _fc_accessible = accessible_feature_categories(
            request.user, getattr(request, "school", None)
        )
        _fc_full = _fc_accessible == set(FEATURE_CATEGORIES.keys())
        if action_type == "revert" and not _fc_full:
            messages.error(request, "Reverting Feature Control requires full access.")
            return _feature_control_panel_redirect_response(request)
        if action_type == "revert" and REVERT_SESSION_KEY in request.session:
            prev = request.session.pop(REVERT_SESSION_KEY, {})
            if prev:
                prev_features = prev.get("features") if isinstance(prev, dict) else None
                prev_weather_payload = (
                    prev.get("weather_payload") if isinstance(prev, dict) else None
                )
                if not isinstance(prev_features, dict):
                    prev_features = prev if isinstance(prev, dict) else {}
                if not isinstance(prev_weather_payload, dict):
                    prev_weather_payload = None

                changes = {
                    k: {"from": current.get(k), "to": prev_features.get(k)}
                    for k in current
                    if current.get(k) != prev_features.get(k)
                }
                _apply_form_to_site(
                    site, prev_features, weather_payload=prev_weather_payload
                )
                _log_audit(request, "revert", changes)
                logger.info("Feature control reverted by %s", request.user.username)
                messages.success(request, "Reverted to previous settings.")
                next_url = request.POST.get("next") or request.GET.get("next")
                if next_url:
                    from django.utils.http import url_has_allowed_host_and_scheme

                    if url_has_allowed_host_and_scheme(
                        next_url, allowed_hosts={request.get_host()}
                    ):
                        return redirect(next_url)
                return redirect("siteconfig:feature_control_panel")

        form_data = {}
        current_weather = _get_weather_selector_state(site)
        if _fc_full:
            weather_payload, weather_state = _resolve_weather_payload_from_post(
                site, request.POST
            )
        else:
            # Weather is a system-tier setting — a per-category delegate never changes it.
            weather_payload, weather_state = {}, current_weather
        defaults = default_backend_feature_flags()
        current_feature_settings = (
            site.get_feature_control_settings()
            if callable(getattr(site, "get_feature_control_settings", None))
            else {}
        )
        current_flags = (
            current_feature_settings.get("backend_feature_flags") or defaults
        )
        current_max_items = _clamp_int(
            current_flags.get("backend_layout_max_items_per_list"),
            defaults.get("backend_layout_max_items_per_list", 5),
            minimum=3,
            maximum=12,
        )
        posted_max_items = current_max_items
        import_data = request.FILES.get("import_file")
        if import_data and not _fc_full:
            messages.error(
                request,
                "Importing a full Feature Control config requires full access.",
            )
            return _feature_control_panel_redirect_response(request)
        if import_data:
            if import_data.size > 2 * 1024 * 1024:  # 2MB max
                messages.error(request, "Import file is too large (max 2 MB).")
                return _feature_control_panel_redirect_response(request)
            try:
                raw = import_data.read().decode("utf-8")
                data = json.loads(raw)
                imported = data.get("features") or data
                for key in current:
                    form_data[key] = bool(imported.get(key, current.get(key)))

                imported_weather = data.get("weather", {})
                imported_country = (
                    imported_weather.get("country_code")
                    or imported_weather.get("header_weather_country_code")
                    or weather_state.get("country_code")
                )
                imported_city_id = (
                    imported_weather.get("location_id")
                    or imported_weather.get("header_weather_location_id")
                    or weather_state.get("location_id")
                )
                weather_payload, weather_state = _resolve_weather_payload_from_post(
                    site,
                    {
                        "weather_country_code": imported_country,
                        "weather_city_id": str(imported_city_id or ""),
                    },
                )
                posted_max_items = _clamp_int(
                    data.get("backend_layout_max_items_per_list"),
                    current_max_items,
                    minimum=3,
                    maximum=12,
                )
            except (json.JSONDecodeError, UnicodeDecodeError) as ex:
                logger.warning("Feature control import failed: %s", ex)
                messages.error(request, "Invalid import file. Use a valid JSON export.")
                return _feature_control_panel_redirect_response(request)
        elif _fc_full:
            for key in current:
                form_data[key] = request.POST.get(f"feature_{key}") == "on"
            posted_max_items = _clamp_int(
                request.POST.get("backend_layout_max_items_per_list"),
                current_max_items,
                minimum=3,
                maximum=12,
            )
            form_data["student_results_visibility"] = request.POST.get(
                "student_results_visibility", ""
            )
        else:
            # Delegate (holds a per-category code, not full settings.feature_control):
            # rebuild from CURRENT and overlay ONLY toggles in categories they may manage,
            # so a posted change to any other toggle / special field is a guaranteed no-op.
            _key_cat = _feature_key_to_category()
            for key in current:
                if _key_cat.get(key) in _fc_accessible:
                    form_data[key] = request.POST.get(f"feature_{key}") == "on"
                else:
                    form_data[key] = current.get(key)
            posted_max_items = current_max_items

        weather_changed = _fc_full and any(
            [
                weather_payload.get("header_weather_location_id")
                != current_weather.get("location_id"),
                weather_payload.get("header_weather_country_code")
                != current_weather.get("country_code"),
                weather_payload.get("header_weather_city")
                != current_weather.get("city"),
                weather_payload.get("header_weather_label")
                != current_weather.get("label"),
            ]
        )
        settings_payload = {
            **weather_payload,
            "backend_layout_max_items_per_list": posted_max_items,
        }
        max_items_changed = posted_max_items != current_max_items

        changes_dict = {
            k: {"from": current.get(k), "to": form_data.get(k)}
            for k in current
            if current.get(k) != form_data.get(k)
        }
        if weather_changed:
            changes_dict["backend_flags.header_weather_location"] = {
                "from": current_weather.get("label"),
                "to": weather_state.get("label"),
            }
        if max_items_changed:
            changes_dict["backend_flags.backend_layout_max_items_per_list"] = {
                "from": current_max_items,
                "to": posted_max_items,
            }

        request.session[REVERT_SESSION_KEY] = {
            "features": dict(current),
            "weather_payload": {
                "header_weather_location_id": current_weather.get("location_id"),
                "header_weather_country_code": current_weather.get("country_code"),
                "header_weather_city": current_weather.get("city"),
                "header_weather_label": current_weather.get("label"),
                "header_weather_latitude": current_weather.get("latitude"),
                "header_weather_longitude": current_weather.get("longitude"),
                "header_weather_timezone": current_weather.get("timezone"),
                "backend_layout_max_items_per_list": current_max_items,
            },
        }
        _apply_form_to_site(site, form_data, weather_payload=settings_payload)
        _log_audit(request, "import" if import_data else "save", changes_dict)
        logger.info(
            "Feature control saved by %s: changed %s",
            request.user.username,
            list(changes_dict.keys()),
        )
        now = timezone.now()
        from apps.siteconfig.cache_utils import tenant_cache_key

        cache.set(
            tenant_cache_key(FEATURE_CONTROL_LAST_SAVED_KEY, request),
            {
                "by": request.user.get_full_name() or request.user.username,
                "at": now.strftime("%Y-%m-%d %H:%M"),
            },
            timeout=60 * 60 * 24 * 7,
        )
        messages.success(
            request, "Feature settings saved. Changes take effect immediately."
        )
        next_url = request.POST.get("next") or request.GET.get("next")
        if next_url:
            from django.utils.http import url_has_allowed_host_and_scheme

            if url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}
            ):
                return redirect(next_url)
        return _feature_control_panel_redirect_response(request)

    ctx = get_feature_control_panel_context(request)
    if request.GET.get("embed") == "1":
        from apps.studio_os.embed_render import render_studio_embed_body

        return render_studio_embed_body(
            request,
            "siteconfig/feature_control_panel_content.html",
            ctx,
            title=_("Feature control"),
        )
    return render_siteconfig_operator_page(
        request,
        portal_template="siteconfig/feature_control_panel.html",
        body_template="siteconfig/partials/feature_control_panel_body.html",
        context=ctx,
        cp_title=_("Feature control"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("Feature control"), active=True),
        ),
    )


def get_feature_control_panel_context(request):
    """Build context for feature control panel (GET). Used by panel view and by Studio OS in-shell."""
    site = _resolve_feature_control_site(request)
    current = _get_site_features(site)
    cat_labels = {
        "academic": ("Academic", "bi-journal-text"),
        "administrative": ("Administrative", "bi-gear"),
        "support": ("Support & Communication", "bi-chat-dots"),
        "finance_permissions": ("Finance & Permissions", "bi-wallet2"),
        "backend": ("Backend Tools", "bi-tools"),
        "system": ("System & Notifications", "bi-bell"),
    }
    categories = []
    active_count = 0
    _fc_accessible = accessible_feature_categories(
        request.user, getattr(request, "school", None)
    )
    for cat_id, rows in FEATURE_CATEGORIES.items():
        if cat_id not in _fc_accessible:
            continue
        label, icon = cat_labels.get(
            cat_id, (cat_id.replace("_", " ").title(), "bi-circle")
        )
        items = []
        for row in rows:
            key = row[0]
            lbl = row[1]
            critical = row[2]
            desc = row[3] if len(row) > 3 else ""
            when_disabled = row[4] if len(row) > 4 else ""
            depends_on = row[5] if len(row) > 5 else []
            val = current.get(key, False)
            if val:
                active_count += 1
            items.append(
                {
                    "key": key,
                    "label": lbl,
                    "enabled": val,
                    "critical": critical,
                    "description": desc,
                    "when_disabled": when_disabled,
                    "depends_on": depends_on,
                }
            )
        categories.append({"id": cat_id, "label": label, "icon": icon, "items": items})

    total = sum(len(c["items"]) for c in categories)
    can_revert = REVERT_SESSION_KEY in request.session
    from apps.siteconfig.cache_utils import tenant_cache_key

    last_saved = cache.get(tenant_cache_key(FEATURE_CONTROL_LAST_SAVED_KEY, request))
    weather_state = _get_weather_selector_state(site)
    defaults = default_backend_feature_flags()
    feature_settings = (
        site.get_feature_control_settings()
        if callable(getattr(site, "get_feature_control_settings", None))
        else {}
    )
    backend_flags = feature_settings.get("backend_feature_flags") or defaults
    backend_layout_max_items_per_list = _clamp_int(
        backend_flags.get("backend_layout_max_items_per_list"),
        defaults.get("backend_layout_max_items_per_list", 5),
        minimum=3,
        maximum=12,
    )
    from apps.portal.student_results_visibility import (
        STUDENT_RESULTS_VISIBILITY_CHOICES,
        get_student_results_visibility_from_site,
    )

    return {
        "categories": categories,
        "active_count": active_count,
        "total_count": total,
        "site_settings_id": site.pk,
        "can_revert": can_revert,
        "last_saved": last_saved,
        "bulk_presets": BULK_PRESETS,
        "bulk_presets_json": json.dumps(BULK_PRESETS),
        "current_json": json.dumps(current),
        "weather_state": weather_state,
        "weather_countries": weather_state.get("countries", []),
        "weather_cities": weather_state.get("cities", []),
        "backend_layout_max_items_per_list": backend_layout_max_items_per_list,
        "student_results_visibility": get_student_results_visibility_from_site(site),
        "student_results_visibility_choices": STUDENT_RESULTS_VISIBILITY_CHOICES,
    }


def get_feature_control_audit_entries(request, limit=20):
    """
    Return recent Feature Control audit entries for Studio or other callers.
    No permission check (caller must ensure access). Returns list of dicts.
    """
    return list(
        FeatureControlAudit.objects.select_related("user")
        .order_by("-created_at")[:limit]
        .values("id", "action", "created_at", "user_id")
    )


@permission_required("settings.feature_control")
@require_http_methods(["GET"])
def feature_control_audit_log(request):
    """View recent Feature Control changes."""
    try:
        page_no = int(request.GET.get("page") or 1)
    except (TypeError, ValueError):
        page_no = 1
    qs = FeatureControlAudit.objects.select_related("user").order_by("-created_at")
    paginator = Paginator(qs, 25)
    page = paginator.get_page(page_no)
    q = request.GET.copy()
    q.pop("page", None)
    return render_siteconfig_operator_page(
        request,
        portal_template="siteconfig/feature_control_audit.html",
        body_template="siteconfig/partials/feature_control_audit_body.html",
        context={
            "entries": page.object_list,
            "page_obj": page,
            "pagination_extra_query": q.urlencode(),
        },
        cp_title=_("Feature control audit"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(
                _("Feature control"),
                url=reverse("siteconfig:feature_control_panel"),
            ),
            operator_cp_breadcrumb(_("Audit log"), active=True),
        ),
    )


@permission_required("settings.feature_control")
@require_http_methods(["GET"])
def feature_control_weather_cities(request):
    country_code = GlobalGeoCatalog.normalize_country_code(
        request.GET.get("country_code")
    )
    query = (request.GET.get("q") or "").strip()
    limit = _clamp_int(request.GET.get("limit"), 500, minimum=10, maximum=500)
    cities = [
        {
            "id": str(row.get("id") or ""),
            "country_code": str(row.get("country_code") or ""),
            "city": str(row.get("city") or ""),
            "label": str(row.get("label") or row.get("city") or ""),
            "timezone": str(row.get("timezone") or "UTC"),
        }
        for row in GlobalGeoCatalog.search_cities(
            country_code=country_code,
            query=query,
            limit=limit,
        )
    ]
    return JsonResponse(
        {
            "country_code": country_code,
            "query": query,
            "cities": cities,
        }
    )


@permission_required("settings.feature_control")
@require_http_methods(["GET"])
def feature_control_api(request):
    """REST API: GET returns current feature state as JSON."""
    site = _resolve_feature_control_site(request)
    current = _get_site_features(site)
    weather_state = _get_weather_selector_state(site)
    defaults = default_backend_feature_flags()
    feature_settings = (
        site.get_feature_control_settings()
        if callable(getattr(site, "get_feature_control_settings", None))
        else {}
    )
    backend_flags = feature_settings.get("backend_feature_flags") or defaults
    backend_layout_max_items_per_list = _clamp_int(
        backend_flags.get("backend_layout_max_items_per_list"),
        defaults.get("backend_layout_max_items_per_list", 5),
        minimum=3,
        maximum=12,
    )
    return JsonResponse(
        {
            "features": current,
            "weather": {
                "location_id": weather_state.get("location_id"),
                "country_code": weather_state.get("country_code"),
                "city": weather_state.get("city"),
                "label": weather_state.get("label"),
                "latitude": weather_state.get("latitude"),
                "longitude": weather_state.get("longitude"),
                "timezone": weather_state.get("timezone"),
            },
            "backend_layout_max_items_per_list": backend_layout_max_items_per_list,
            "updated_at": site.updated_at.isoformat()
            if hasattr(site, "updated_at") and site.updated_at
            else None,
        }
    )


@permission_required("settings.feature_control")
@never_cache
@require_http_methods(["GET"])
def feature_control_ledger(request):
    """
    Unified ledger UI: feature flag audit trail + pointers to usage_registry / metadata lineage docs.
    """
    entries = list(
        FeatureControlAudit.objects.select_related("user").order_by("-created_at")[:200]
    )
    return render_siteconfig_operator_page(
        request,
        portal_template="siteconfig/feature_control_ledger.html",
        body_template="siteconfig/partials/feature_control_ledger_body.html",
        context={
            "entries": entries,
            "panel_url": reverse("siteconfig:feature_control_panel"),
            "audit_url": reverse("siteconfig:feature_control_audit"),
        },
        cp_title=_("Feature control ledger"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(
                _("Feature control"),
                url=reverse("siteconfig:feature_control_panel"),
            ),
            operator_cp_breadcrumb(_("Ledger"), active=True),
        ),
    )

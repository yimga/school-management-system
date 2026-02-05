# -*- coding: utf-8 -*-
"""
Feature Control Panel - toggle modules and features at runtime.
Access: settings.feature_control permission or superuser.
"""
import json
import logging

from django.core.cache import cache
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache

from apps.accounts.decorators import permission_required
from apps.siteconfig.models import (
    SiteSettings,
    default_portal_features,
    default_backend_feature_flags,
)
from apps.siteconfig.models_dashboard import FeatureControlAudit

logger = logging.getLogger("siteconfig.feature_control")
FEATURE_CONTROL_LAST_SAVED_KEY = "feature_control_last_saved"
REVERT_SESSION_KEY = "feature_control_previous_state"

# (key, label, critical, description, when_disabled, depends_on)
# depends_on: list of keys that must be ON for this to work (e.g. allow_finance_access needs parent_portal)
FEATURE_CATEGORIES = {
    "academic": [
        ("portal_features.syllabus", "Class Syllabus", False, "Show syllabus in portal", "Syllabus hidden from portal", []),
        ("grade_approval_enabled", "Grade Approval Workflow", True, "Require approval before publishing marks", "Teachers post marks directly", []),
        ("grade_approval_auto_validate", "Grade Auto-Validation", False, "Flag missing/anomalous scores", "No validation before approval", ["grade_approval_enabled"]),
        ("enable_practical_assessment", "Practical Assessment", False, "Evidence upload and practical assessments", "Practical assessment disabled", []),
        ("enable_concurrent_mark_uploads", "Concurrent Mark Uploads", False, "Allow parallel grade uploads", "Sequential uploads only", []),
    ],
    "administrative": [
        ("enable_parent_portal", "Parent Portal", True, "Parent dashboard and access", "Parents redirected to maintenance", []),
        ("enable_teacher_portal", "Teacher Portal", True, "Teacher dashboard and access", "Teachers redirected to maintenance", []),
        ("enable_reports_pdf", "Report Card PDFs", False, "Generate and download PDF reports", "PDF generation disabled", []),
        ("report_downloads_enabled", "Report Downloads", False, "Allow report file downloads", "Report downloads disabled", []),
        ("maintenance_mode", "Maintenance Mode", True, "Show maintenance page site-wide", "Site returns to normal", []),
        ("preview_mode_enabled", "Preview Mode (Admin)", False, "Admins can preview portal as users", "Preview disabled", []),
    ],
    "support": [
        ("portal_features.documents", "Document Library", False, "Document upload and library", "Document library hidden", []),
        ("portal_features.forums", "Community Forums", False, "Community discussion forums", "Forums hidden", []),
        ("portal_features.video", "Video Hub", False, "Video content hub", "Video hub hidden", []),
        ("portal_features.messaging", "Messaging", False, "In-app messaging", "Messaging hidden", []),
    ],
    "finance_permissions": [
        ("backend_flags.require_guardian_finance_opt_in", "Guardian Finance Opt-In", False, "Parents must opt in to see finance", "Finance visible by default", ["enable_parent_portal"]),
        ("backend_flags.allow_finance_access_requests", "Finance Access Requests", False, "Parents can request finance visibility", "Access requests disabled", ["enable_parent_portal"]),
        ("backend_flags.block_promotion_if_outstanding_returns", "Block Promotion if Returns", False, "Block promotion with outstanding resource returns", "Promotion allowed despite returns", []),
        ("backend_flags.block_report_download_if_outstanding_balance", "Block Report Download if Fees Owed", True, "Block term/annual report download until fees are cleared", "Reports downloadable even with outstanding balance", []),
        ("backend_flags.block_report_download_if_outstanding_returns", "Block Report Download if Returns Owed", False, "Block report download until issued resources are returned", "Reports downloadable despite unreturned items", []),
        ("backend_flags.carry_forward_arrears_on_rollover", "Carry Forward Arrears on Rollover", False, "Create opening-balance invoices in next year for unpaid fees", "Rollover does not carry arrears", []),
    ],
    "backend": [
        ("backend_flags.enable_entity_console", "Entity Console", False, "Data orchestration UI", "Entity Console hidden", []),
        ("backend_flags.enable_entity_import", "Entity Import", False, "Bulk import tools", "Entity Import hidden", []),
        ("backend_flags.allow_bulk_commit", "Bulk Import Commit", False, "Allow commit step in entity import", "Bulk commit disabled", []),
        ("backend_flags.enable_api_schema_ui", "API Schema UI", False, "API documentation for staff", "API docs hidden", []),
    ],
    "system": [
        ("backend_flags.notify_parent_on_absence", "Notify Parent on Absence", False, "Alert guardians when student absent", "No absence alerts", []),
        ("enable_offline_mode", "Offline Mode", False, "Offline sync for marks and data", "Offline sync disabled", []),
        ("auto_tag_photos_from_exif", "Auto-Tag Photos from EXIF", False, "Extract metadata from evidence photos", "No EXIF tagging", []),
    ],
}

# Bulk presets: preset_id -> { label, description, set_on: [keys], set_off: [keys] }
BULK_PRESETS = {
    "school_closed": {
        "label": "School Closed",
        "description": "Maintenance mode, portals off, minimal access",
        "set_on": ["maintenance_mode"],
        "set_off": ["enable_parent_portal", "enable_teacher_portal", "preview_mode_enabled"],
    },
    "exam_period": {
        "label": "Exam Period",
        "description": "Parent/Teacher portals on, grade approval strict, reports enabled",
        "set_on": ["enable_parent_portal", "enable_teacher_portal", "grade_approval_enabled", "grade_approval_auto_validate", "enable_reports_pdf"],
        "set_off": ["maintenance_mode"],
    },
    "full_operations": {
        "label": "Full Operations",
        "description": "All features enabled for normal operations",
        "set_on": [
            "enable_parent_portal", "enable_teacher_portal", "enable_reports_pdf", "report_downloads_enabled",
            "grade_approval_enabled", "grade_approval_auto_validate", "portal_features.syllabus",
            "portal_features.documents", "portal_features.messaging", "enable_practical_assessment",
            "enable_concurrent_mark_uploads", "preview_mode_enabled", "enable_offline_mode",
            "auto_tag_photos_from_exif", "backend_flags.enable_entity_console", "backend_flags.enable_entity_import",
            "backend_flags.allow_bulk_commit", "backend_flags.enable_api_schema_ui",
            "backend_flags.notify_parent_on_absence", "backend_flags.allow_finance_access_requests",
        ],
        "set_off": ["maintenance_mode", "backend_flags.require_guardian_finance_opt_in"],
    },
}


def _get_site_features(site: SiteSettings) -> dict:
    """Return current feature state for display and form."""
    portal = site.portal_features or default_portal_features()
    flags = site.backend_feature_flags or default_backend_feature_flags()
    return {
        "enable_parent_portal": site.enable_parent_portal,
        "enable_teacher_portal": site.enable_teacher_portal,
        "enable_reports_pdf": site.enable_reports_pdf,
        "report_downloads_enabled": site.report_downloads_enabled,
        "portal_features.documents": bool(portal.get("documents")),
        "portal_features.forums": bool(portal.get("forums")),
        "portal_features.video": bool(portal.get("video")),
        "portal_features.messaging": bool(portal.get("messaging")),
        "portal_features.syllabus": bool(portal.get("syllabus")),
        "grade_approval_enabled": site.grade_approval_enabled,
        "grade_approval_auto_validate": site.grade_approval_auto_validate,
        "enable_practical_assessment": site.enable_practical_assessment,
        "enable_concurrent_mark_uploads": site.enable_concurrent_mark_uploads,
        "maintenance_mode": site.maintenance_mode,
        "preview_mode_enabled": site.preview_mode_enabled,
        "enable_offline_mode": site.enable_offline_mode,
        "auto_tag_photos_from_exif": site.auto_tag_photos_from_exif,
        "backend_flags.enable_entity_console": bool(flags.get("enable_entity_console")),
        "backend_flags.enable_entity_import": bool(flags.get("enable_entity_import")),
        "backend_flags.enable_api_schema_ui": bool(flags.get("enable_api_schema_ui")),
        "backend_flags.allow_bulk_commit": bool(flags.get("allow_bulk_commit", True)),
        "backend_flags.require_guardian_finance_opt_in": bool(flags.get("require_guardian_finance_opt_in")),
        "backend_flags.allow_finance_access_requests": bool(flags.get("allow_finance_access_requests", True)),
        "backend_flags.notify_parent_on_absence": bool(flags.get("notify_parent_on_absence", True)),
        "backend_flags.block_promotion_if_outstanding_returns": bool(flags.get("block_promotion_if_outstanding_returns")),
        "backend_flags.block_report_download_if_outstanding_balance": bool(flags.get("block_report_download_if_outstanding_balance", True)),
        "backend_flags.block_report_download_if_outstanding_returns": bool(flags.get("block_report_download_if_outstanding_returns")),
        "backend_flags.carry_forward_arrears_on_rollover": bool(flags.get("carry_forward_arrears_on_rollover", True)),
    }


def _apply_form_to_site(site: SiteSettings, form_data: dict) -> None:
    """Apply form checkbox values to SiteSettings."""
    portal = dict(site.portal_features or default_portal_features())
    flags = dict(site.backend_feature_flags or default_backend_feature_flags())

    for key, val in form_data.items():
        if key.startswith("portal_features."):
            subkey = key.split(".", 1)[1]
            portal[subkey] = bool(val)
        elif key.startswith("backend_flags."):
            subkey = key.split(".", 1)[1]
            flags[subkey] = bool(val)
        elif key == "enable_parent_portal":
            site.enable_parent_portal = bool(val)
        elif key == "enable_teacher_portal":
            site.enable_teacher_portal = bool(val)
        elif key == "enable_reports_pdf":
            site.enable_reports_pdf = bool(val)
        elif key == "report_downloads_enabled":
            site.report_downloads_enabled = bool(val)
        elif key == "grade_approval_enabled":
            site.grade_approval_enabled = bool(val)
        elif key == "grade_approval_auto_validate":
            site.grade_approval_auto_validate = bool(val)
        elif key == "enable_practical_assessment":
            site.enable_practical_assessment = bool(val)
        elif key == "enable_concurrent_mark_uploads":
            site.enable_concurrent_mark_uploads = bool(val)
        elif key == "maintenance_mode":
            site.maintenance_mode = bool(val)
        elif key == "preview_mode_enabled":
            site.preview_mode_enabled = bool(val)
        elif key == "enable_offline_mode":
            site.enable_offline_mode = bool(val)
        elif key == "auto_tag_photos_from_exif":
            site.auto_tag_photos_from_exif = bool(val)
    site.portal_features = portal
    site.backend_feature_flags = flags
    site.save(update_fields=[
        "enable_parent_portal", "enable_teacher_portal",
        "enable_reports_pdf", "report_downloads_enabled",
        "grade_approval_enabled", "grade_approval_auto_validate",
        "enable_practical_assessment", "enable_concurrent_mark_uploads",
        "maintenance_mode", "preview_mode_enabled",
        "enable_offline_mode", "auto_tag_photos_from_exif",
        "portal_features", "backend_feature_flags", "updated_at",
    ])


def _log_audit(request, action: str, changes: dict) -> None:
    """Log Feature Control change to audit table."""
    try:
        FeatureControlAudit.objects.create(
            user=request.user,
            action=action,
            changes=changes,
        )
    except Exception as ex:
        logger.warning("Could not log feature control audit: %s", ex)


@permission_required("settings.feature_control")
@require_http_methods(["GET"])
def feature_control_export(request):
    """Export current feature configuration as JSON."""
    site = SiteSettings.get_solo()
    current = _get_site_features(site)
    response = HttpResponse(
        json.dumps({"features": current, "exported_at": timezone.now().isoformat()}, indent=2),
        content_type="application/json",
    )
    response["Content-Disposition"] = 'attachment; filename="feature-control-backup.json"'
    return response


@permission_required("settings.feature_control")
@never_cache
@require_http_methods(["GET", "POST"])
def feature_control_panel(request):
    """Feature Control Panel - toggle modules system-wide."""
    site = SiteSettings.get_solo()
    current = _get_site_features(site)

    if request.method == "POST":
        action_type = request.POST.get("action", "save")
        if action_type == "revert" and REVERT_SESSION_KEY in request.session:
            prev = request.session.pop(REVERT_SESSION_KEY, {})
            if prev:
                changes = {k: {"from": current.get(k), "to": prev.get(k)} for k in current if current.get(k) != prev.get(k)}
                _apply_form_to_site(site, prev)
                _log_audit(request, "revert", changes)
                logger.info("Feature control reverted by %s", request.user.username)
                messages.success(request, "Reverted to previous settings.")
                return redirect("siteconfig:feature_control_panel")

        form_data = {}
        import_data = request.FILES.get("import_file")
        if import_data:
            try:
                raw = import_data.read().decode("utf-8")
                data = json.loads(raw)
                imported = data.get("features") or data
                for key in current:
                    form_data[key] = bool(imported.get(key, current.get(key)))
            except (json.JSONDecodeError, UnicodeDecodeError) as ex:
                logger.warning("Feature control import failed: %s", ex)
                messages.error(request, "Invalid import file. Use a valid JSON export.")
                return redirect("siteconfig:feature_control_panel")
        else:
            for key in current:
                form_data[key] = request.POST.get(f"feature_{key}") == "on"
        changes_dict = {k: {"from": current.get(k), "to": form_data.get(k)} for k in current if current.get(k) != form_data.get(k)}
        request.session[REVERT_SESSION_KEY] = dict(current)
        _apply_form_to_site(site, form_data)
        _log_audit(request, "import" if import_data else "save", changes_dict)
        logger.info("Feature control saved by %s: changed %s", request.user.username, list(changes_dict.keys()))
        now = timezone.now()
        cache.set(FEATURE_CONTROL_LAST_SAVED_KEY, {
            "by": request.user.get_full_name() or request.user.username,
            "at": now.strftime("%Y-%m-%d %H:%M"),
        }, timeout=60 * 60 * 24 * 7)
        messages.success(request, "Feature settings saved. Changes take effect immediately.")
        return redirect("siteconfig:feature_control_panel")

    # Build rows for template
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
    key_to_meta = {}
    for cat_id, rows in FEATURE_CATEGORIES.items():
        label, icon = cat_labels.get(cat_id, (cat_id.replace("_", " ").title(), "bi-circle"))
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
            items.append({
                "key": key,
                "label": lbl,
                "enabled": val,
                "critical": critical,
                "description": desc,
                "when_disabled": when_disabled,
                "depends_on": depends_on,
            })
        categories.append({"id": cat_id, "label": label, "icon": icon, "items": items})

    total = sum(len(c["items"]) for c in categories)
    can_revert = REVERT_SESSION_KEY in request.session
    last_saved = cache.get(FEATURE_CONTROL_LAST_SAVED_KEY)
    return render(request, "siteconfig/feature_control_panel.html", {
        "categories": categories,
        "active_count": active_count,
        "total_count": total,
        "site_settings_id": site.pk,
        "can_revert": can_revert,
        "last_saved": last_saved,
        "bulk_presets": BULK_PRESETS,
        "bulk_presets_json": json.dumps(BULK_PRESETS),
        "current_json": json.dumps(current),
    })


@permission_required("settings.feature_control")
@require_http_methods(["GET"])
def feature_control_audit_log(request):
    """View recent Feature Control changes."""
    entries = FeatureControlAudit.objects.select_related("user").order_by("-created_at")[:50]
    return render(request, "siteconfig/feature_control_audit.html", {"entries": entries})


@permission_required("settings.feature_control")
@require_http_methods(["GET"])
def feature_control_api(request):
    """REST API: GET returns current feature state as JSON."""
    site = SiteSettings.get_solo()
    current = _get_site_features(site)
    return JsonResponse({
        "features": current,
        "updated_at": site.updated_at.isoformat() if hasattr(site, "updated_at") and site.updated_at else None,
    })

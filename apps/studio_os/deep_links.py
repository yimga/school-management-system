"""
Resolve Studio / shell links when some URL namespaces exist only on tenant or only on manager.
STUDIO_APPROVAL_HUB_TENANT_BASE_URL — tenant origin for siteconfig/* from manager.
MANAGER_PLATFORM_BASE_URL — manager origin for super/* from tenant.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.urls import NoReverseMatch, reverse

# Paths are suffixes; siteconfig gets tenant base when set, else same-origin relative.
_PATHS: dict[str, str] = {
    "siteconfig:theme_colors": "/siteconfig/theme-colors/",
    "siteconfig:guided_onboarding": "/siteconfig/guided-onboarding/",
    "siteconfig:feature_control_panel": "/siteconfig/feature-control/",
    "siteconfig:reportcard_builder": "/siteconfig/reports/builder/",
    "siteconfig:workflow_flow_gallery": "/siteconfig/workflow-gallery/",
    "siteconfig:feature_control_audit": "/siteconfig/feature-control/audit/",
    "siteconfig:get_blueprints": "/siteconfig/get-blueprints/",
    "siteconfig:school_theme_settings": "/siteconfig/school-theme/",
    "siteconfig:brand_import_from_url": "/siteconfig/theme-colors/import-from-url/",
    "siteconfig:preview_from_form": "/siteconfig/preview-from-form/",
    "accounts:backend_dashboard": "/authentication/backend/",
    "accounts:rbac": "/authentication/rbac/",
    "portal:document_library_manage": "/portal/backend/documents/",
    "portal:parent_dashboard": "/portal/parent/",
    "communication:group_list": "/communication/groups/",
    "communication:announcement_create": "/communication/announcements/create/",
    "evals:grade_approval_list": "/evals/grade-approvals/",
    "requests:dashboard": "/requests/",
    "portal:staff_contact_request_list": "/portal/staff/contact-requests/",
    "reports:publish_term_results": "/reports/publish/",
    "accounts:advancement_donor_list": "/authentication/backend/advancement/donors/",
    "accounts:ops_hub": "/authentication/backend/ops/",
    "accounts:ops_substitutes": "/authentication/backend/ops/substitutes/",
    "accounts:ops_visitor_log": "/authentication/backend/ops/visitors/",
    "accounts:ops_facilities": "/authentication/backend/ops/facilities/",
    "accounts:ops_pos": "/authentication/backend/ops/pos/",
    "siteconfig:installed_packages_rollback": "/siteconfig/installed-packages/",
    "portal:teacher_bulk_capture_hub": "/portal/teacher/bulk-capture/",
    "accounts:tenant_activity_log": "/authentication/backend/activity-log/",
    "accounts:district_lms_interop": "/authentication/backend/district-lms-interop/",
    "automation:outcomes_console": "/automation/outcomes/",
    "metadata:metadata_lineage_graph": "/api/internal/metadata/lineage/graph/",
    "metadata:metadata_governance": "/api/internal/metadata/governance/",
    "apicenter:dashboard": "/api-center/",
    "marketing_landing": "/marketing/",
    "super:analytics_overview": "/super/analytics/",
    "super:dashboard": "/super/",
    "super:create_school_wizard": "/super/create/",
    "super:runtime_inspector": "/super/runtime-inspector/",
    "super:policy_diff": "/super/policy-diff/",
    "super:billing_dashboard": "/super/billing/",
    "admin:packages_experiencepack_changelist": "/admin/packages/experiencepack/",
    "studio_os:shell": "/studio/",
    "studio_os:approval_hub": "/studio/hubs/approvals/",
    "studio_os:workflow_center": "/studio/hubs/workflow/",
    "studio_os:import_hub": "/studio/hubs/import/",
    "studio_os:launch": "/studio/launch/",
    "studio_os:launch_select_plan": "/studio/launch/select-plan/",
    "studio_os:experience": "/studio/experience/",
    "studio_os:experience_recommendations": "/studio/experience/recommendations/",
    "studio_os:experience_compare": "/studio/experience/compare/",
    "studio_os:experience_theme_tokens": "/studio/experience/theme-tokens/",
    "studio_os:experience_portal_shell_layouts": "/studio/experience/portal-shell-layouts/",
    "studio_os:experience_dashboard_visual_packs": "/studio/experience/dashboard-visual-packs/",
    "studio_os:experience_school_website_blocks": "/studio/experience/school-website-blocks/",
    "studio_os:experience_communication_style_packs": "/studio/experience/communication-style-packs/",
    "studio_os:experience_packs": "/studio/experience/experience-packs/",
    "studio_os:automation": "/studio/automation/",
    "studio_os:automation_conflict_detection": "/studio/automation/conflict-detection/",
    "studio_os:automation_staged_activation": "/studio/automation/staged-activation/",
    "studio_os:automation_replay_rollback": "/studio/automation/replay-rollback/",
    "studio_os:automation_visual_builder": "/studio/automation/visual-builder/",
    "studio_os:automation_natural_language_workflow": "/studio/automation/natural-language-workflow/",
    "studio_os:automation_simulation_engine": "/studio/automation/simulation-engine/",
    "studio_os:automation_dependency_graph": "/studio/automation/dependency-graph/",
    "studio_os:automation_workflow_health": "/studio/automation/workflow-health/",
    "studio_os:output": "/studio/output/",
    "studio_os:output_dependency_graph": "/studio/output/dependency-graph/",
    "studio_os:output_branding_inheritance": "/studio/output/branding-inheritance/",
    "studio_os:output_policy_registry": "/studio/output/policy-registry/",
    "studio_os:control": "/studio/control/",
    "studio_os:system_config_console": "/studio/control/system-config/",
    "studio_os:control_impact": "/studio/control/impact/",
    "studio_os:ai_cleanup": "/studio/control/ai-cleanup/",
    "studio_os:preview": "/studio/preview/",
    "studio_os:publish": "/studio/publish/",
    "studio_os:rollback": "/studio/rollback/",
}


def _tenant_base() -> str:
    return (
        getattr(settings, "STUDIO_APPROVAL_HUB_TENANT_BASE_URL", None) or ""
    ).strip().rstrip("/")


def _manager_base() -> str:
    return (
        getattr(settings, "MANAGER_PLATFORM_BASE_URL", None) or ""
    ).strip().rstrip("/")


def studio_resolve_url(
    viewname: str, *, args: Any = None, kwargs: Any = None
) -> str:
    """
    Prefer reverse(); then path rules. siteconfig:* uses tenant base when set.
    super:* / admin:* / marketing_landing use manager base when set.
    Other paths are returned relative (same origin).
    """
    args = args or ()
    kwargs = kwargs or {}
    try:
        return reverse(viewname, args=args, kwargs=kwargs)
    except NoReverseMatch:
        pass
    path = _PATHS.get(viewname)
    if not path:
        return ""
    if viewname.startswith("siteconfig:"):
        tb = _tenant_base()
        if tb:
            return f"{tb}{path}"
        return ""
    if viewname.startswith("super:") or viewname.startswith("admin:"):
        mb = _manager_base()
        return f"{mb}{path}" if mb else path
    if viewname.startswith(
        (
            "portal:",
            "accounts:",
            "communication:",
            "automation:",
            "metadata:",
            "apicenter:",
            "evals:",
            "reports:",
            "requests:",
        )
    ):
        tb = _tenant_base()
        return f"{tb}{path}" if tb else path
    return path


def resolve_studio_href(viewname: str, *, embed: bool = False) -> str | None:
    """URL for Studio rails; None if unresolvable. Optional ?embed=1."""
    u = studio_resolve_url(viewname)
    if not u:
        return None
    if embed:
        return f"{u}{'&' if '?' in u else '?'}embed=1"
    return u


def studio_legacy_urls_map() -> dict[str, str]:
    """Legacy shell keys with best-effort URLs."""
    out: dict[str, str] = {}
    pairs = [
        ("customizer", "studio_os:experience"),
        ("theme_colors", "siteconfig:theme_colors"),
        ("feature_control", "siteconfig:feature_control_panel"),
        ("report_library", "studio_os:output"),
        ("workflow_hub", "studio_os:automation"),
        ("guided_onboarding", "siteconfig:guided_onboarding"),
        ("document_library", "portal:document_library_manage"),
        ("reportcard_builder", "siteconfig:reportcard_builder"),
        ("workflow_flow_gallery", "siteconfig:workflow_flow_gallery"),
        ("backend_dashboard", "accounts:backend_dashboard"),
        ("approval_hub", "studio_os:approval_hub"),
        ("workflow_center", "studio_os:workflow_center"),
        ("import_hub", "studio_os:import_hub"),
        ("rbac", "accounts:rbac"),
        ("communication_groups", "communication:group_list"),
        ("announcement_create", "communication:announcement_create"),
    ]
    for key, viewname in pairs:
        u = studio_resolve_url(viewname)
        if u:
            out[key] = u
    return out

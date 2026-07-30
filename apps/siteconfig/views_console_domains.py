"""
Console UX per domain (B3). One entry point listing seven bounded domains with guided links.
Outcomes not jargon: Standardize grading, Configure branding, Assign dashboards, etc.
Each console supports search, preview, diff, audit, rollback where relevant (9.5/10 excellence).
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpRequest, HttpResponse
from django.utils.translation import gettext as _

from apps.siteconfig.control_plane_render import (
    operator_cp_breadcrumb,
    render_siteconfig_operator_page,
)
from django.urls import NoReverseMatch, reverse

from apps.siteconfig.control_outcome_center import (
    PUBLISH_STAGING_HINT,
    WHY_ENABLED_SUMMARY,
    build_ccc_staging_publish_links_for_request,
    build_operator_control_model_for_request,
    build_outcome_groups_for_request,
    get_ccc_source_legend_display_labels,
)

logger = logging.getLogger(__name__)


def _is_manager_scope(request: HttpRequest | None) -> bool:
    if request is None:
        return False
    kind = getattr(request, "public_host_kind", None)
    urlconf = getattr(request, "urlconf", None)
    return (
        (kind == "manager" or urlconf == "config.manager_urls")
        and getattr(request, "school", None) is None
    )


def _is_operator_url_name(name: str | None) -> bool:
    return bool(name and name.startswith(("super:", "admin:")))

# Per-domain actions for 9.5/10: search, preview, diff (compare before apply), audit (change history), rollback (revert where relevant).
# Use None to hide; reverse() name or path string. Operator-safe: outcomes not jargon.
CONSOLE_ACTIONS = {
    "brand_experience": {
        "search": "studio_os:experience",
        "preview": "siteconfig:preview_from_form",
        "diff": "studio_os:experience",
        "audit": None,
        "rollback": None,
    },
    "runtime_blueprints": {
        "search": "siteconfig:dashboard_hub",
        "preview": "studio_os:automation",
        "diff": "siteconfig:dashboard_hub",
        "audit": None,
        "rollback": None,
    },
    "policies_rules": {
        "search": "siteconfig:feature_control_panel",
        "preview": "siteconfig:feature_control_audit",
        "diff": "siteconfig:feature_control_panel",
        "audit": "siteconfig:feature_control_audit",
        "rollback": None,
    },
    "plans_entitlements": {
        "search": "siteconfig:module_market",
        "preview": None,
        "diff": None,
        "audit": None,
        "rollback": None,
    },
    "global_registries": {
        "search": "siteconfig:grading_settings",
        "preview": None,
        "diff": None,
        "audit": None,
        "rollback": None,
    },
    "integrations_marketplace": {
        "search": "siteconfig:module_market",
        "preview": "siteconfig:marketplace_sandbox_embed",
        "diff": None,
        "audit": None,
        "rollback": None,
    },
    "metadata_catalog": {
        "search": "siteconfig:metadata_dynamic_fields_operator",
        "preview": "metadata:metadata_lineage_graph",
        "diff": "siteconfig:entity_catalog_overview",
        "audit": "siteconfig:config_mutation_audit_evidence",
        "rollback": None,
    },
}

# Seven domains (plan B1) with outcome-first labels and target views.
CONSOLE_DOMAINS = [
    {
        "code": "brand_experience",
        "name": "Brand & experience",
        "outcome": "Configure branding and themes",
        "links": [
            ("Theme & colors", "siteconfig:theme_colors"),
            ("Studio", "studio_os:shell"),
            ("School theme", "siteconfig:school_theme_settings"),
            ("Brand import from URL", "siteconfig:brand_import_from_url"),
        ],
    },
    {
        "code": "runtime_blueprints",
        "name": "Runtime & blueprints",
        "outcome": "Blueprints, dashboards, workflows",
        "links": [
            ("Effective runtime & tenant settings", "siteconfig:tenant_runtime_configuration_hub"),
            ("School group hierarchy", "siteconfig:school_group_hierarchy"),
            ("Dashboard hub", "siteconfig:dashboard_hub"),
            ("Automation Studio", "studio_os:automation"),
            ("Output Studio", "studio_os:output"),
            ("Dashboard configuration", "siteconfig:dashboard_configuration_hub"),
            ("Report builder", "siteconfig:reportcard_builder"),
        ],
    },
    {
        "code": "policies_rules",
        "name": "Policies & rules",
        "outcome": "Feature toggles and approval rules",
        "links": [
            ("Feature control", "siteconfig:feature_control_panel"),
            ("Feature audit", "siteconfig:feature_control_audit"),
        ],
    },
    {
        "code": "plans_entitlements",
        "name": "Plans & entitlements",
        "outcome": "Plans, add-ons, waivers",
        "links": [
            ("Request waiver", "siteconfig:request_waiver"),
            ("Modules", "siteconfig:module_market"),
        ],
    },
    {
        "code": "global_registries",
        "name": "Global registries",
        "outcome": "Region, grading, calendar",
        "links": [
            ("Grading settings", "siteconfig:grading_settings"),
            (
                "Grading scale bands (tenant DB)",
                "siteconfig:grading_scale_bands",
            ),
            ("Curriculum templates (reference)", "siteconfig:curriculum_templates"),
            ("Region validation", "siteconfig:region_validation"),
            ("Region comparison", "siteconfig:region_comparison"),
            ("Region grading matrix", "siteconfig:region_grading_scales"),
        ],
    },
    {
        "code": "integrations_marketplace",
        "name": "Integrations & marketplace",
        "outcome": "Integrations and app marketplace",
        "links": [
            ("App catalog", "tenant_app_catalog"),
            ("App sandbox", "siteconfig:marketplace_sandbox_embed"),
        ],
    },
    {
        "code": "metadata_catalog",
        "name": "Metadata catalog",
        "outcome": "Entity/field catalog and lineage",
        "links": [
            ("Metadata & lineage hub", "siteconfig:metadata_operator_hub"),
            ("Dynamic fields (EAV operator)", "siteconfig:metadata_dynamic_fields_operator"),
            ("Config mutation audit (evidence)", "siteconfig:config_mutation_audit_evidence"),
            ("Entity catalog (overview)", "siteconfig:entity_catalog_overview"),
            ("Full metadata catalog (platform)", "super:metadata_catalog"),
            ("Admin: entity rows (CRUD)", "admin:metadata_entitycatalogentry_changelist"),
            ("Admin: config mutation audit", "admin:metadata_configmutationauditlog_changelist"),
            ("Admin: dynamic field definitions/values (CRUD)", "admin:metadata_dynamicfielddefinition_changelist"),
        ],
    },
]


def _safe_reverse(name: str, request=None):
    """Resolve URL by name; support admin: namespace. Returns None on NoReverseMatch and logs at debug."""
    if _is_operator_url_name(name) and not _is_manager_scope(request):
        return None
    try:
        if name.startswith("admin:"):
            return reverse(name)
        return reverse(name)
    except NoReverseMatch as e:
        logger.debug("Console domain URL name %r failed to resolve: %s", name, e)
        return None


def _build_console_domains_context(request: HttpRequest) -> list[dict[str, Any]]:
    """Build a fresh list of domain dicts with resolved URLs (no mutation of CONSOLE_DOMAINS)."""
    domains = []
    for d in CONSOLE_DOMAINS:
        resolved_links = []
        for label, name in d["links"]:
            if _is_operator_url_name(name) and not _is_manager_scope(request):
                continue
            try:
                url = reverse(name)
                resolved_links.append({"label": label, "url": url})
            except NoReverseMatch as e:
                logger.debug(
                    "Console domain %s link %r (%r) failed to resolve: %s",
                    d["code"],
                    label,
                    name,
                    e,
                )
                resolved_links.append({"label": label, "url": "#"})
        actions = CONSOLE_ACTIONS.get(d["code"], {})
        domains.append(
            {
                "code": d["code"],
                "name": d["name"],
                "outcome": d["outcome"],
                "resolved_links": resolved_links,
                "search_url": _safe_reverse(actions.get("search"), request)
                if actions.get("search")
                else None,
                "preview_url": _safe_reverse(actions.get("preview"), request)
                if actions.get("preview")
                else None,
                "diff_url": _safe_reverse(actions.get("diff"), request)
                if actions.get("diff")
                else None,
                "audit_url": _safe_reverse(actions.get("audit"), request)
                if actions.get("audit")
                else None,
                "rollback_url": _safe_reverse(actions.get("rollback"), request)
                if actions.get("rollback")
                else None,
            }
        )
    return domains


def _build_platform_config_context(request: HttpRequest) -> list[dict[str, Any]]:
    """Platform config cards for manager: site settings, regions, plans, feature toggles, AI. Only used on manager."""
    if not _is_manager_scope(request):
        return []
    cards = []
    entries = [
        (
            "operator_hub",
            "Platform operator hub",
            "Super-first operations plus every platform admin changelist in one place.",
            "super:platform_operator_hub",
            "bi-grid-3x3-gap",
            None,
        ),
        (
            "site_settings",
            "Site settings",
            "Platform-level site name, theme, and defaults.",
            "super:site_settings_list",
            "bi-gear",
            None,
        ),
        (
            "regions",
            "Regions & grading",
            "Region config and grading scale catalog.",
            None,
            "bi-globe",
            [
                ("Regions", "super:regions_list"),
                ("Grading", "super:grading_list"),
            ],
        ),
        (
            "plans",
            "Plans & add-ons",
            "Billing plans and add-on catalog.",
            "super:plans_list",
            "bi-currency-dollar",
            None,
        ),
        (
            "feature_toggles",
            "Feature toggles",
            "Platform feature flag definitions and state.",
            "super:feature_toggles_list",
            "bi-toggle-on",
            None,
        ),
        (
            "ai_models",
            "AI / model registry",
            "AI model registry and regional config.",
            "super:ai_model_hub",
            "bi-cpu",
            None,
        ),
    ]
    for code, name, outcome, single_url, icon, links in entries:
        resolved = []
        if single_url:
            try:
                resolved.append({"label": "Open", "url": reverse(single_url)})
            except NoReverseMatch:
                pass
        elif links:
            for label, url_name in links:
                try:
                    resolved.append({"label": label, "url": reverse(url_name)})
                except NoReverseMatch:
                    pass
        if resolved:
            cards.append(
                {
                    "code": code,
                    "name": name,
                    "outcome": outcome,
                    "icon": icon,
                    "links": resolved,
                }
            )
    return cards


def _build_operational_links_context(request: HttpRequest) -> list[dict[str, str]]:
    """Operational quick links for manager: schools, incidents, billing, migration."""
    if not _is_manager_scope(request):
        return []
    out = []
    for label, url_name in [
        ("Platform operator hub", "super:platform_operator_hub"),
        ("Schools list", "super:schools_list"),
        ("Incidents", "super:incidents_list"),
        ("Billing", "super:billing_dashboard"),
        ("Billing accounts", "super:billing_accounts_list"),
        ("Migration", "super:migration_cloud"),
        ("Migration runs", "super:migration_runs_list"),
        ("Pulse", "super:pulse"),
    ]:
        try:
            out.append({"label": label, "url": reverse(url_name)})
        except NoReverseMatch:
            pass
    return out


def _build_operational_hubs_context(request: HttpRequest) -> list[dict[str, Any]]:
    """Operational hubs merged into Configuration Control Center: Studio OS entry plus Workflow, Approvals, Import, Documents, Reports, RBAC, Feature control, Communications. Single integrated list."""
    hubs = []
    for label, url_name, icon in [
        ("Studio OS", "studio_os:shell", "bi-window-stack"),
        ("Workflow center", "studio_os:workflow_center", "bi-diagram-3"),
        ("Approval hub", "studio_os:approval_hub", "bi-clipboard-check"),
        ("Import & bulk", "studio_os:import_hub", "bi-upload"),
        ("Document library", "portal:document_library_manage", "bi-folder2-open"),
        ("Report library", "studio_os:output", "bi-journal-text"),
        ("RBAC & permissions", "accounts:rbac", "bi-shield-lock"),
        ("Feature control", "siteconfig:feature_control_panel", "bi-toggle-on"),
        ("Message groups", "communication:group_list", "bi-people"),
        ("Announcements", "communication:announcement_create", "bi-megaphone"),
    ]:
        url = _safe_reverse(url_name)
        if url:
            hubs.append({"label": label, "url": url, "icon": icon})
    return hubs


# Honor SUPERUSERS as well as staff — `staff_member_required` alone bounces a
# superadmin whose account isn't flagged is_staff (they got 502/Forbidden here),
# inconsistent with every sibling config view (backend_dashboard, cockpit configure,
# user_may_configure_tenant_experience all allow is_staff OR is_superuser).
@user_passes_test(
    lambda u: u.is_active and (u.is_staff or u.is_superuser),
    login_url=settings.LOGIN_URL,
)
def console_domains_hub(request: HttpRequest) -> HttpResponse:
    """Single bounded console: operational hubs + configuration domains + (manager) platform config + operational links. Backoffice merged here; one UI."""
    domains = _build_console_domains_context(request)
    operational_hubs = _build_operational_hubs_context(request)
    studio_shell_url = _safe_reverse("studio_os:shell")
    school = getattr(request, "school", None)
    ccc_onboarding = None
    if school is not None:
        try:
            from apps.platform_runtime.onboarding import (
                get_school_onboarding_progress,
            )

            ccc_onboarding = get_school_onboarding_progress(
                school, user=request.user
            )
        except (
            AttributeError,
            ImportError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            ccc_onboarding = None

    context = {
        "domains": domains,
        "operational_hubs": operational_hubs,
        "studio_shell_url": studio_shell_url,
        "studio_experience_url": _safe_reverse("studio_os:experience"),
        "guided_onboarding_url": _safe_reverse("siteconfig:guided_onboarding"),
        "theme_colors_hub_url": _safe_reverse("siteconfig:theme_colors"),
        "outcome_groups": build_outcome_groups_for_request(request),
        "why_enabled_summary": WHY_ENABLED_SUMMARY,
        "operator_control_model": build_operator_control_model_for_request(request),
        "ccc_source_legend": get_ccc_source_legend_display_labels(),
        "ccc_publish_staging_hint": PUBLISH_STAGING_HINT,
        "ccc_staging_links": build_ccc_staging_publish_links_for_request(request),
        # Light chrome on tenant portal; dark chrome on manager control plane
        "ccc_outcome_compact": getattr(request, "public_host_kind", None) != "manager",
        "ccc_onboarding": ccc_onboarding,
    }
    if _is_manager_scope(request):
        try:
            context["super_dashboard_url"] = reverse("super:dashboard")
        except NoReverseMatch:
            context["super_dashboard_url"] = None
        try:
            context["platform_operator_hub_url"] = reverse("super:platform_operator_hub")
        except NoReverseMatch:
            context["platform_operator_hub_url"] = None
    else:
        context["super_dashboard_url"] = _safe_reverse(
            "accounts:backend_dashboard", request
        )
        context["platform_operator_hub_url"] = None
    context["platform_config"] = _build_platform_config_context(request)
    context["operational_links"] = _build_operational_links_context(request)
    context["compact"] = getattr(request, "public_host_kind", None) != "manager"
    return render_siteconfig_operator_page(
        request,
        portal_template="siteconfig/console_domains_hub.html",
        body_template="siteconfig/partials/console_domains_hub_body.html",
        manager_body_template="siteconfig/partials/console_domains_hub_manager_body.html",
        context=context,
        cp_title=_("Configuration Control Center"),
        breadcrumbs=[
            operator_cp_breadcrumb(_("Configuration Control Center"), active=True),
        ],
    )

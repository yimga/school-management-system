# -*- coding: utf-8 -*-
"""
Studio OS — single shell with five work modes.
Replaces fragmented customizer / theme / feature control / report library / workflow hub with one workspace.
Shared preview (2.1) and publish/rollback (2.2) via studio_preview, studio_publish_api, studio_save_draft_api.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from apps.platform_runtime.structured_logging import (
    log_exception_with_context,
    request_context_for_log,
)
from apps.schools.control_plane import (
    use_control_plane_shell,
    user_can_access_studio_on_request,
)
from .services import (
    get_studio_activity_feed,
    get_studio_compare_context,
    get_automation_dependency_graph,
    get_studio_global_search,
    get_studio_preview_context,
    get_studio_preview_url,
    get_studio_publish_audit,
    get_studio_recommendations,
    get_studio_role_preview_entries,
    get_studio_command_palette_entries,
    get_studio_version_history,
    get_output_dependency_graph,
    studio_rollback_available,
    studio_publish,
    studio_save_draft,
)


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_recommendations_api(request):
    """§4.1 Unified recommendation engine hook. GET ?mode= — returns JSON {recommendations: [{label, url, detail, tone}]}."""
    if not user_can_access_studio_on_request(request):
        return JsonResponse({"recommendations": []})
    mode = (request.GET.get("mode") or "").strip().lower() or None
    recs = get_studio_recommendations(request, mode)
    return JsonResponse({"recommendations": recs})


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_system_config_console(request):
    """§6.1 Bounded console: tenant-safe links + manager-host fallbacks for super-only tools."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    from django.conf import settings as dj_settings

    mgr = (getattr(dj_settings, "MANAGER_PLATFORM_BASE_URL", None) or "").strip().rstrip(
        "/"
    )
    links = []

    def _add_local(label, viewname, embed=False):
        try:
            u = reverse(viewname)
            if embed:
                u += "?embed=1" if "?" not in u else "&embed=1"
            links.append(
                {
                    "label": label,
                    "url": u,
                    "external": False,
                    "hint": "",
                }
            )
            return True
        except NoReverseMatch:
            return False

    def _add_manager(label, path, hint):
        if not mgr:
            return
        links.append(
            {
                "label": label,
                "url": f"{mgr}{path}",
                "external": True,
                "hint": hint,
            }
        )

    _add_local(_("Capabilities"), "siteconfig:feature_control_panel", embed=True)
    _add_local(_("Blueprints & policy packs"), "siteconfig:get_blueprints", embed=True)
    if not _add_local(_("Runtime inspector"), "super:runtime_inspector"):
        _add_manager(
            _("Runtime inspector"),
            "/super/runtime-inspector/",
            _("Manager host — superadmin"),
        )
    if not _add_local(_("Metadata governance"), "metadata:metadata_governance"):
        _add_manager(
            _("Metadata governance"),
            "/api/internal/metadata/governance/",
            _("Manager / platform"),
        )
    if not _add_local(_("Lineage & registry"), "metadata:metadata_lineage_graph"):
        _add_manager(
            _("Lineage & registry"),
            "/api/internal/metadata/lineage/graph/?embed=1",
            _("Manager / platform"),
        )
    _add_local(_("Integrations (API Center)"), "apicenter:dashboard")
    if not _add_local(_("Plans & entitlements"), "super:billing_dashboard", embed=True):
        _add_manager(
            _("Plans & billing"),
            "/super/billing/?embed=1",
            _("Manager host"),
        )
    _add_local(_("Diff / impact summary"), "studio_os:control_impact", embed=True)

    return render(
        request,
        "studio_os/system_config_console.html",
        {
            "page_title": _("System config"),
            "page_subtitle": _(
                "Each link opens the real surface. Super-only items open the manager host when you are on a school domain."
            ),
            "config_links": links,
            "action_url": reverse("studio_os:control"),
            "action_text": _("Back to Control"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_control_impact(request):
    """§4.6 Control Studio optional: Diff / impact summary. Renders control mode impact_summary for embedding in rail."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    preview_ctx = get_studio_preview_context("control", request)
    return render(
        request,
        "studio_os/control_impact.html",
        {
            "impact_summary": preview_ctx.get("impact_summary") or "",
            "dependency_warnings": preview_ctx.get("dependency_warnings") or [],
            "page_title": _("Diff / impact summary"),
            "page_subtitle": _(
                "Review feature toggles and runtime state before publishing. Use Runtime inspector for impact and source tracing."
            ),
            "action_url": reverse("studio_os:control"),
            "action_text": _("Back to Control"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_ai_cleanup(request):
    """§4.6 Control Studio optional: AI cleanup suggestions. Renders control-mode recommendations for embedding in rail."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    recs = get_studio_recommendations(request, "control")
    return render(
        request,
        "studio_os/ai_cleanup.html",
        {
            "recommendations": recs,
            "page_title": _("AI cleanup suggestions"),
            "page_subtitle": _(
                "Capabilities and audit log suggestions for feature state."
            ),
            "action_url": reverse("studio_os:control"),
            "action_text": _("Back to Control"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_experience_recommendations(request):
    """§4.2 Experience Studio optional: AI recommendations. Renders experience-mode recommendations for embedding in rail."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    recs = get_studio_recommendations(request, "experience")
    return render(
        request,
        "studio_os/experience_recommendations.html",
        {
            "recommendations": recs,
            "page_title": _("AI recommendations"),
            "page_subtitle": _("Experience-mode suggestions for theme and branding."),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_experience_compare(request):
    """§4.2 Experience Studio optional: Compare (before/after). §5.6 Live Previews: Add before/after."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    compare_ctx = get_studio_compare_context(request, "experience")
    return render(
        request,
        "studio_os/experience_compare.html",
        {
            "before_entries": compare_ctx.get("before_entries") or [],
            "after_entries": compare_ctx.get("after_entries") or [],
            "has_before": compare_ctx.get("has_before", False),
            "page_title": "Compare (before / after)",
            "page_subtitle": "Publish a theme change to see before/after comparison.",
            "action_url": reverse("studio_os:experience"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_experience_theme_tokens(request):
    """§4.2 Experience Studio optional: Theme tokens. Explains design tokens (CSS variables) used by in-shell theme form and outputs."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    theme_url = ""
    try:
        theme_url = reverse("siteconfig:theme_colors") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/experience_theme_tokens.html",
        {
            "theme_colors_url": theme_url,
            "page_title": _("Theme tokens"),
            "page_subtitle": _(
                "Design tokens (CSS variables) drive theme and in-shell form; configure in Theme & colors."
            ),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_experience_portal_shell_layouts(request):
    """§4.2 Experience Studio optional: Portal shell layouts. Explains portal shell structure (sidebar, header, content) and where to configure."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    customizer_url = ""
    try:
        customizer_url = reverse("studio_os:experience") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/experience_portal_shell_layouts.html",
        {
            "customizer_url": customizer_url,
            "page_title": _("Portal shell layouts"),
            "page_subtitle": _(
                "Portal shell structure (sidebar, header, content areas); configure in Customizer and School theme."
            ),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_experience_dashboard_visual_packs(request):
    """§4.2 Experience Studio optional: Dashboard visual packs. Explains dashboard widgets, charts, layout presets; links to dashboard/customizer."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    dashboard_url = ""
    try:
        dashboard_url = reverse("accounts:backend_dashboard") + "?embed=1"
    except NoReverseMatch:
        pass
    customizer_url = ""
    try:
        customizer_url = reverse("studio_os:experience") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/experience_dashboard_visual_packs.html",
        {
            "dashboard_url": dashboard_url,
            "customizer_url": customizer_url,
            "page_title": _("Dashboard visual packs"),
            "page_subtitle": _(
                "Widgets, charts, and layout presets for role-based dashboards; configure in Backend dashboard and Customizer."
            ),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_experience_school_website_blocks(request):
    """§4.2 Experience Studio optional: School website blocks. Explains landing page sections and school website content; links to marketing and Customizer."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    marketing_url = ""
    try:
        marketing_url = reverse("marketing_landing") + "?embed=1"
    except NoReverseMatch:
        pass
    customizer_url = ""
    try:
        customizer_url = reverse("studio_os:experience") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/experience_school_website_blocks.html",
        {
            "marketing_url": marketing_url,
            "customizer_url": customizer_url,
            "page_title": _("School website blocks"),
            "page_subtitle": _(
                "Landing page sections, hero, and content blocks for your school website; configure in Customizer and marketing pages."
            ),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_experience_communication_style_packs(request):
    """§4.2 Experience Studio optional: Communication style packs. Explains tone, templates, and notification styles; links to Customizer and communication settings."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    customizer_url = ""
    try:
        customizer_url = reverse("studio_os:experience") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/experience_communication_style_packs.html",
        {
            "customizer_url": customizer_url,
            "page_title": _("Communication style packs"),
            "page_subtitle": _(
                "Tone, templates, and notification styles for parent and staff communications; configure in Customizer and communication settings."
            ),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_experience_packs(request):
    """§4.2 Experience Studio optional: ExperiencePack. Explains packageable theme + layout + dashboard + communication; shows current pack and links to admin and Theme & colors."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    school = getattr(request, "school", None)
    effective_pack = None
    pack_count = 0
    try:
        from apps.brand_experience.experience_packs import get_effective_experience_pack
        from apps.packages.models import ExperiencePack
        from apps.packages.tenant_pack_install import sync_experience_pack_install_from_school

        if school:
            sync_result = sync_experience_pack_install_from_school(
                school, actor_id=getattr(request.user, "pk", None)
            )
            if not sync_result.get("ok") and not sync_result.get("skipped"):
                log_exception_with_context(
                    "studio_experience_packs sync_experience_pack_install_from_school",
                    **request_context_for_log(request),
                    exc_info=False,
                    extra={"errors": sync_result.get("errors")},
                )
        effective_pack = get_effective_experience_pack(school) if school else None
        pack_count = ExperiencePack.objects.filter(is_active=True).count()
    except (ImportError, AttributeError):
        pass
    theme_colors_url = ""
    admin_packs_url = ""
    try:
        theme_colors_url = reverse("siteconfig:theme_colors") + "?embed=1"
    except NoReverseMatch:
        pass
    try:
        admin_packs_url = reverse("admin:packages_experiencepack_changelist")
    except NoReverseMatch:
        pass
    package_impact_fetch_url = ""
    experience_graph_package_id = ""
    if school:
        try:
            package_impact_fetch_url = reverse("api:api-north-star-package-impact")
        except NoReverseMatch:
            package_impact_fetch_url = "/api/internal/north-star/package-impact/"
    if school and effective_pack:
        experience_graph_package_id = f"exp-pack:{effective_pack.code}"
    return render(
        request,
        "studio_os/experience_experience_packs.html",
        {
            "effective_pack": effective_pack,
            "pack_count": pack_count,
            "theme_colors_url": theme_colors_url,
            "admin_packs_url": admin_packs_url,
            "package_impact_fetch_url": package_impact_fetch_url,
            "experience_graph_package_id": experience_graph_package_id,
            "school": school,
            "page_title": _("Experience packs"),
            "page_subtitle": _(
                "Packageable theme, layout, dashboard visual, and communication style. Assign per school; compare and rollback from Experience Studio."
            ),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_output_dependency_graph(request):
    """§4.4 Output Studio optional: Dependency graph. Shows report pack dependencies for embedding in Output rail."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    graph = get_output_dependency_graph()
    return render(
        request,
        "studio_os/output_dependency_graph.html",
        {
            "graph": graph,
            "page_title": "Dependency graph",
            "page_subtitle": "Report packs and their dependencies (fields, policies, templates).",
            "action_url": reverse("studio_os:output"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_output_branding_inheritance(request):
    """§4.4 Output Studio optional: Branding inheritance. Explains that reports/documents inherit school theme (primary color, logo)."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    theme_url = ""
    try:
        theme_url = reverse("siteconfig:theme_colors") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/output_branding_inheritance.html",
        {
            "theme_colors_url": theme_url,
            "page_title": _("Branding inheritance"),
            "page_subtitle": _(
                "Reports and documents inherit school and theme branding. Configure theme and colors to control outputs."
            ),
            "action_url": reverse("studio_os:output"),
            "action_text": _("Back to Outputs"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_output_policy_registry(request):
    """§5.3 Report Library: Policy & registry compatibility. Explains how report packs align with policy registry and metadata lineage; links to Blueprints & policy and Lineage & registry."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    blueprints_url = ""
    lineage_url = ""
    report_library_url = ""
    try:
        blueprints_url = reverse("siteconfig:get_blueprints") + "?embed=1"
    except NoReverseMatch:
        pass
    try:
        lineage_url = reverse("metadata:metadata_lineage_graph") + "?embed=1"
    except NoReverseMatch:
        pass
    try:
        report_library_url = reverse("studio_os:output") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/output_policy_registry.html",
        {
            "page_title": _("Policy & registry"),
            "page_subtitle": _(
                "Reports and report packs align with policy (blueprints, grading, terms) and metadata registry (lineage, fields). Use Report library to build; Control for policy and lineage."
            ),
            "action_url": reverse("studio_os:output"),
            "action_text": _("Back to Outputs"),
            "blueprints_url": blueprints_url,
            "lineage_url": lineage_url,
            "report_library_url": report_library_url,
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_launch_select_plan(request):
    """§4.5 Launch Studio: Select plan. Placeholder when plans not productized; rail entry and view wired for when plan product ships."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    return render(
        request,
        "studio_os/launch_select_plan.html",
        {
            "page_title": _("Select plan"),
            "page_subtitle": _(
                "Choose your school's plan and entitlements. Full plan picker when productized."
            ),
            "action_url": reverse("studio_os:launch"),
            "action_text": _("Back to Launch"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_automation_conflict_detection(request):
    """§4.3 Automation Studio optional: Conflict detection. Explains workflow conflict detection and links to Workflow hub."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    workflow_hub_url = ""
    try:
        workflow_hub_url = reverse("studio_os:automation") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/automation_conflict_detection.html",
        {
            "workflow_hub_url": workflow_hub_url,
            "page_title": _("Conflict detection"),
            "page_subtitle": _(
                "Detect and resolve conflicts before activating workflows."
            ),
            "action_url": reverse("studio_os:automation"),
            "action_text": _("Back to Automation"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_automation_staged_activation(request):
    """§4.3 Automation Studio optional: Staged activation. Explains activating workflows in stages and links to Workflow hub."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    workflow_hub_url = ""
    try:
        workflow_hub_url = reverse("studio_os:automation") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/automation_staged_activation.html",
        {
            "workflow_hub_url": workflow_hub_url,
            "page_title": _("Staged activation"),
            "page_subtitle": _(
                "Activate workflows in stages; run simulations before going live."
            ),
            "action_url": reverse("studio_os:automation"),
            "action_text": _("Back to Automation"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_automation_replay_rollback(request):
    """§4.3 Automation Studio optional: Replay / rollback. Explains workflow replay and rollback; links to Workflow hub and unified rollback."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    workflow_hub_url = ""
    rollback_url = ""
    try:
        workflow_hub_url = reverse("studio_os:automation") + "?embed=1"
    except NoReverseMatch:
        pass
    try:
        rollback_url = reverse("studio_os:rollback") + "?mode=automation"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/automation_replay_rollback.html",
        {
            "workflow_hub_url": workflow_hub_url,
            "rollback_url": rollback_url,
            "page_title": _("Replay / rollback"),
            "page_subtitle": _(
                "Re-run workflow instances and roll back workflow or config changes."
            ),
            "action_url": reverse("studio_os:automation"),
            "action_text": _("Back to Automation"),
        },
    )


def _automation_explainer_view(
    request, template_name: str, page_title: str, page_subtitle: str
):
    """Shared helper for Automation Studio explainer pages (staff-only, workflow_hub_url, action back to automation)."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    workflow_hub_url = ""
    try:
        workflow_hub_url = reverse("studio_os:automation") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        template_name,
        {
            "workflow_hub_url": workflow_hub_url,
            "page_title": page_title,
            "page_subtitle": page_subtitle,
            "action_url": reverse("studio_os:automation"),
            "action_text": _("Back to Automation"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_automation_visual_builder(request):
    """§4.3 Automation Studio optional: Visual builder. Explains drag-and-drop workflow building; links to Workflow hub."""
    return _automation_explainer_view(
        request,
        "studio_os/automation_visual_builder.html",
        _("Visual builder"),
        _(
            "Build workflows visually with drag-and-drop; connect steps and conditions. Manage flows from the Workflow hub."
        ),
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_automation_natural_language_workflow(request):
    """§4.3 Automation Studio optional: Natural-language workflow generation. Explains NL-to-workflow; links to Workflow hub."""
    return _automation_explainer_view(
        request,
        "studio_os/automation_natural_language_workflow.html",
        _("Natural-language workflow"),
        _(
            "Describe workflows in plain language; the system suggests or generates flow steps. Refine and activate from the Workflow hub."
        ),
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_automation_simulation_engine(request):
    """§4.3 Automation Studio optional: Simulation engine. Explains run-before-activate; links to Workflow hub."""
    return _automation_explainer_view(
        request,
        "studio_os/automation_simulation_engine.html",
        _("Simulation engine"),
        _(
            "Run workflow simulations before going live. Verify behavior and impact from the Workflow hub, then activate when ready."
        ),
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_automation_dependency_graph(request):
    """§4.3 Automation Studio optional: Dependency graph. Shows workflow packs and their templates for embedding in Automation rail."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    graph = get_automation_dependency_graph()
    return render(
        request,
        "studio_os/automation_dependency_graph.html",
        {
            "graph": graph,
            "page_title": "Dependency graph",
            "page_subtitle": "Workflow packs and their templates (pack → templates).",
            "action_url": reverse("studio_os:automation"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_automation_workflow_health(request):
    """§4.3 Automation Studio optional: Workflow health metrics. Summary of active packs and templates."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    from apps.studio_os.services import get_automation_workflow_health_summary

    summary = get_automation_workflow_health_summary()
    workflow_hub_url = ""
    try:
        workflow_hub_url = reverse("studio_os:automation") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/automation_workflow_health.html",
        {
            "pack_count": summary.get("pack_count", 0),
            "template_count": summary.get("template_count", 0),
            "workflow_hub_url": workflow_hub_url,
            "page_title": _("Workflow health metrics"),
            "page_subtitle": _(
                "Active workflow packs and templates; run simulations from Workflow hub."
            ),
            "action_url": reverse("studio_os:automation"),
            "action_text": _("Back to Automation"),
        },
    )


STUDIO_MODES = [
    {
        "id": "experience",
        "label": "Experience",
        "description": "Shape branding, theme, and portals",
    },
    {
        "id": "automation",
        "label": "Automation",
        "description": "Workflows, approvals, and automation",
    },
    {
        "id": "output",
        "label": "Outputs",
        "description": "Reports, documents, and exports",
    },
    {"id": "launch", "label": "Launch", "description": "Setup and go live"},
    {
        "id": "control",
        "label": "Control",
        "description": "Capabilities, policies, and runtime",
    },
]


def _resolve_legacy_urls(request):
    """Links to current tools; each name resolved independently (manager vs tenant URLconf)."""
    from apps.studio_os.deep_links import studio_legacy_urls_map, studio_resolve_url

    legacy = studio_legacy_urls_map()
    for name, url_name in [
        ("approval_hub", "studio_os:approval_hub"),
        ("workflow_center", "studio_os:workflow_center"),
        ("import_hub", "studio_os:import_hub"),
    ]:
        if name not in legacy or not legacy.get(name):
            u = studio_resolve_url(url_name)
            if u:
                legacy[name] = u
    return legacy


def _studio_rail_append(
    rail: list, label: str, viewname: str, *, embed: bool = False
) -> None:
    from apps.studio_os.deep_links import resolve_studio_href

    u = resolve_studio_href(viewname, embed=embed)
    if u:
        rail.append({"label": label, "url": u, "embed": embed})


def _resolve_embed_urls(request):
    """URLs to embed in the Studio canvas per mode. Single-sourced from get_studio_preview_url."""
    return {
        mode: get_studio_preview_url(mode, request)
        for mode in ("experience", "automation", "output", "launch", "control")
    }


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_shell(request, mode=None):
    """
    Single Studio OS shell. mode in ('experience','automation','output','launch','control').
    If mode is None, show home (overview of modes).
    """
    if not user_can_access_studio_on_request(request):
        from django.shortcuts import redirect
        from django.contrib import messages

        messages.info(request, "Studio OS is available to staff.")
        return redirect(reverse("accounts:backend_dashboard"))

    mode = (mode or "").strip().lower() or None
    if mode and mode not in [m["id"] for m in STUDIO_MODES]:
        mode = None

    legacy_urls = _resolve_legacy_urls(request)
    embed_urls = _resolve_embed_urls(request)
    embed_url = embed_urls.get(mode) if mode else None
    # On manager host without a tenant/school, embedded views (theme_colors, guided_onboarding, etc.)
    # often redirect or fail; avoid iframe so we show the fallback with direct links instead of "connection refused".
    if (
        use_control_plane_shell(request)
        and not getattr(request, "school", None)
        and embed_url
    ):
        embed_url = None

    activity_feed = get_studio_activity_feed(request)
    recommendations = get_studio_recommendations(request, mode)
    command_palette_entries = get_studio_command_palette_entries(request)
    rollback_available = studio_rollback_available(mode, request) if mode else False

    try:
        preview_from_form_url = reverse("siteconfig:preview_from_form")
    except NoReverseMatch:
        preview_from_form_url = ""
    try:
        studio_preview_url = reverse("studio_os:preview")
    except NoReverseMatch:
        studio_preview_url = preview_from_form_url
    try:
        studio_publish_url = reverse("studio_os:publish")
    except NoReverseMatch:
        studio_publish_url = ""

    context = {
        "studio_modes": STUDIO_MODES,
        "current_mode": mode,
        "legacy_urls": legacy_urls,
        "embed_url": embed_url,
        "school": getattr(request, "school", None),
        "studio_activity_feed": activity_feed,
        "studio_recommendations": recommendations,
        "studio_command_palette_entries": command_palette_entries,
        "studio_role_preview_entries": get_studio_role_preview_entries(request),
        "studio_show_bottom_bar": False,
        "studio_bottom_bar_actions": [],
        "studio_rollback_available": rollback_available,
        "studio_preview_from_form_url": studio_preview_url,
        "studio_preview_url": studio_preview_url,
        "studio_publish_url": studio_publish_url,
        "studio_rollback_url": "",
    }

    school = getattr(request, "school", None)
    if mode == "experience":
        try:
            from apps.siteconfig.views import get_theme_colors_context

            context.update(get_theme_colors_context(request))
            context["use_experience_in_page"] = True
            context["back_url"] = reverse("studio_os:experience")
            context["studio_version_history"] = get_studio_version_history(
                request, "experience", limit=5
            )
            context["studio_audit"] = get_studio_publish_audit(
                request, "experience", limit=8
            )
        except (
            NoReverseMatch,
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
        ) as e:
            if not isinstance(e, NoReverseMatch):
                log_exception_with_context(
                    "studio_shell experience mode: get_theme_colors_context or version/audit failed",
                    **request_context_for_log(request),
                    extra={"mode": "experience"},
                )
            context["use_experience_in_page"] = False
            context["studio_version_history"] = []
            context["studio_audit"] = []
        experience_rail = []
        for label, vn in (
            ("Theme & colors", "siteconfig:theme_colors"),
            ("Customizer", "studio_os:experience"),
            ("School theme", "siteconfig:school_theme_settings"),
            ("Experience packs", "studio_os:experience_packs"),
            ("Import from website", "siteconfig:brand_import_from_url"),
            ("Compare", "studio_os:experience_compare"),
            ("AI recommendations", "studio_os:experience_recommendations"),
            ("Theme tokens", "studio_os:experience_theme_tokens"),
            ("Portal shell layouts", "studio_os:experience_portal_shell_layouts"),
            ("Dashboard visual packs", "studio_os:experience_dashboard_visual_packs"),
            ("School website blocks", "studio_os:experience_school_website_blocks"),
            (
                "Communication style packs",
                "studio_os:experience_communication_style_packs",
            ),
        ):
            _studio_rail_append(experience_rail, label, vn, embed=True)
        context["experience_left_rail"] = experience_rail

    if mode == "launch" and school:
        try:
            from apps.setup_studio.services import get_setup_studio_payload

            payload = get_setup_studio_payload(school)
            context["launch_payload"] = payload
            context["launch_role_previews"] = payload.get("role_previews") or []
            context["launch_health_summary"] = payload.get("health_summary") or ""
            context["launch_ready"] = payload.get("launch_ready", False)
        except (
            NoReverseMatch,
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
        ) as e:
            if not isinstance(e, NoReverseMatch):
                log_exception_with_context(
                    "studio_shell launch mode: get_setup_studio_payload failed",
                    **request_context_for_log(request),
                    extra={"mode": "launch"},
                )
            context["launch_payload"] = None
            context["launch_role_previews"] = []
            context["launch_health_summary"] = ""
            context["launch_ready"] = False
    elif mode == "launch":
        context["launch_payload"] = None
        context["launch_role_previews"] = []
        context["launch_health_summary"] = ""
        context["launch_ready"] = False

    if mode == "launch":
        launch_rail = []
        _studio_rail_append(
            launch_rail, "Guided onboarding", "siteconfig:guided_onboarding", embed=True
        )
        _studio_rail_append(
            launch_rail, "Create school", "super:create_school_wizard", embed=True
        )
        _studio_rail_append(
            launch_rail, "Select plan", "studio_os:launch_select_plan", embed=True
        )
        _studio_rail_append(
            launch_rail, "Blueprint gallery", "siteconfig:get_blueprints", embed=True
        )
        _studio_rail_append(launch_rail, "Import branding", "studio_os:experience", embed=True)
        _studio_rail_append(
            launch_rail, "Launch checklist", "siteconfig:guided_onboarding", embed=True
        )
        context["launch_left_rail"] = launch_rail

    if mode == "automation":
        from apps.studio_os.deep_links import resolve_studio_href

        workflow_entries = []
        automation_rail = []
        for label, vn, url_embed in (
            ("Outcomes", "automation:outcomes_console", True),
            ("Workflow hub", "studio_os:automation", True),
            ("Flow gallery", "siteconfig:workflow_flow_gallery", False),
            ("Approval hub", "studio_os:approval_hub", False),
            ("Dependency graph", "studio_os:automation_dependency_graph", True),
            ("Workflow health metrics", "studio_os:automation_workflow_health", True),
            ("Conflict detection", "studio_os:automation_conflict_detection", True),
            ("Staged activation", "studio_os:automation_staged_activation", True),
            ("Replay / rollback", "studio_os:automation_replay_rollback", True),
            ("Visual builder", "studio_os:automation_visual_builder", True),
            (
                "Natural-language workflow",
                "studio_os:automation_natural_language_workflow",
                True,
            ),
            ("Simulation engine", "studio_os:automation_simulation_engine", True),
        ):
            u = resolve_studio_href(vn, embed=url_embed)
            if u:
                workflow_entries.append({"label": label, "url": u})
                automation_rail.append({"label": label, "url": u, "embed": True})
        context["workflow_entries"] = workflow_entries
        context["automation_left_rail"] = automation_rail
        context["automation_simulation_summary"] = (
            "Run simulation from Workflow hub to see impact before activating."
        )

    if mode == "output":
        output_rail = []
        for label, vn in (
            ("Report library", "studio_os:output"),
            ("Document library", "portal:document_library_manage"),
            ("Report card builder", "siteconfig:reportcard_builder"),
            ("Dependency graph", "studio_os:output_dependency_graph"),
            ("Branding inheritance", "studio_os:output_branding_inheritance"),
            ("Policy & registry", "studio_os:output_policy_registry"),
        ):
            _studio_rail_append(output_rail, label, vn, embed=True)
        context["output_left_rail"] = output_rail

    if mode == "control":
        try:
            from apps.siteconfig.views_feature_control import (
                get_feature_control_audit_entries,
            )

            context["control_audit_entries"] = get_feature_control_audit_entries(
                request, limit=15
            )
        except (
            NoReverseMatch,
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
        ) as e:
            if not isinstance(e, NoReverseMatch):
                log_exception_with_context(
                    "studio_shell control mode: get_feature_control_audit_entries failed",
                    **request_context_for_log(request),
                    extra={"mode": "control"},
                )
            context["control_audit_entries"] = []
        control_rail = []
        from apps.studio_os.deep_links import resolve_studio_href

        _studio_rail_append(
            control_rail, "System config", "studio_os:system_config_console", embed=True
        )
        _studio_rail_append(
            control_rail, "Capabilities", "siteconfig:feature_control_panel", embed=True
        )
        u_audit = resolve_studio_href("siteconfig:feature_control_audit", embed=False)
        if u_audit:
            control_rail.append(
                {"label": "Audit log", "url": u_audit, "embed": True}
            )
        _studio_rail_append(
            control_rail, "Runtime inspector", "super:runtime_inspector", embed=False
        )
        _studio_rail_append(
            control_rail,
            "Metadata governance",
            "metadata:metadata_governance",
            embed=False,
        )
        _studio_rail_append(
            control_rail,
            "Lineage & registry",
            "metadata:metadata_lineage_graph",
            embed=True,
        )
        _studio_rail_append(
            control_rail, "Integrations", "apicenter:dashboard", embed=False
        )
        _studio_rail_append(
            control_rail, "Blueprints & policy packs", "siteconfig:get_blueprints", embed=True
        )
        _studio_rail_append(control_rail, "Policy diff", "super:policy_diff", embed=True)
        _studio_rail_append(
            control_rail, "Plans & entitlements", "super:billing_dashboard", embed=True
        )
        _studio_rail_append(control_rail, "Diff / impact summary", "studio_os:control_impact", embed=True)
        _studio_rail_append(
            control_rail, "AI cleanup suggestions", "studio_os:ai_cleanup", embed=True
        )
        context["control_left_rail"] = control_rail
        # In-shell control panel (no iframe) when user has permission
        if request.user.has_perm("settings.feature_control"):
            try:
                from django.template.loader import render_to_string
                from apps.siteconfig.views_feature_control import (
                    get_feature_control_panel_context,
                )

                ctrl_ctx = get_feature_control_panel_context(request)
                ctrl_ctx["control_next_url"] = reverse("studio_os:control")
                context["control_panel_html"] = render_to_string(
                    "siteconfig/feature_control_panel_partial.html",
                    ctrl_ctx,
                    request=request,
                )
                context["embed_url"] = None  # prefer in-page over iframe
            except (
                NoReverseMatch,
                ImportError,
                AttributeError,
                TypeError,
                ValueError,
            ) as e:
                if not isinstance(e, NoReverseMatch):
                    log_exception_with_context(
                        "studio_shell control mode: feature_control_panel render failed",
                        **request_context_for_log(request),
                        extra={"mode": "control"},
                    )
                context["control_panel_html"] = None
        else:
            context["control_panel_html"] = None

    show_bottom_bar = bool(
        mode == "experience" and context.get("use_experience_in_page")
    )
    bottom_bar_actions = []
    if show_bottom_bar:
        bottom_bar_actions = [
            {"id": "preview", "label": "Preview", "primary": False},
            {"id": "publish", "label": "Publish", "primary": True},
        ]
        if rollback_available:
            bottom_bar_actions.append(
                {"id": "rollback", "label": "Rollback", "primary": False}
            )
            try:
                context["studio_rollback_url"] = (
                    reverse("studio_os:rollback") + "?mode=" + mode
                )
            except NoReverseMatch:
                context["studio_rollback_url"] = ""

    context["studio_show_bottom_bar"] = show_bottom_bar
    context["studio_bottom_bar_actions"] = bottom_bar_actions

    if use_control_plane_shell(request):
        template = "studio_os/shell_control_plane.html"
    else:
        template = f"studio_os/modes/{mode}.html" if mode else "studio_os/shell.html"
    return render(request, template, context)


@never_cache
@require_http_methods(["GET", "POST"])
@login_required
def studio_rollback(request):
    """
    Perform rollback for current mode and redirect back to Studio.
    Experience: rollback last theme publish (session-scoped). Control: redirect to feature control with embed (user clicks Revert there).
    """

    def _wants_json() -> bool:
        return "application/json" in (request.headers.get("Accept") or "").lower()

    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    mode = (request.GET.get("mode") or request.POST.get("mode") or "").strip().lower()
    if mode == "experience":
        if request.method != "POST":
            if _wants_json():
                return JsonResponse(
                    {"ok": False, "errors": ["POST required"]}, status=405
                )
            return redirect(reverse("studio_os:experience"))

        prev = request.session.get("theme_previous_state")
        values = None
        if isinstance(prev, dict) and isinstance(prev.get("values"), dict):
            values = prev.get("values")
        elif isinstance(prev, dict):
            values = prev

        if not isinstance(values, dict) or not values:
            if _wants_json():
                return JsonResponse(
                    {"ok": False, "errors": ["No rollback state available."]},
                    status=400,
                )
            return redirect(reverse("studio_os:experience"))

        from django.utils import timezone
        from apps.platform_runtime.helpers import get_effective_site_settings

        site = get_effective_site_settings(request=request)
        if site is None:
            if _wants_json():
                return JsonResponse(
                    {
                        "ok": False,
                        "errors": ["Unable to resolve SiteSettings for rollback."],
                    },
                    status=400,
                )
            return redirect(reverse("studio_os:experience"))

        updated_fields = []
        for field_name, previous_value in values.items():
            id_attr = f"{field_name}_id"
            if hasattr(site, id_attr):
                setattr(site, id_attr, previous_value)
                updated_fields.append(field_name)
            elif hasattr(site, field_name):
                setattr(site, field_name, previous_value)
                updated_fields.append(field_name)

        theme_fields = list(
            dict.fromkeys(
                [f for f in updated_fields if isinstance(f, str) and f.strip()]
            )
        )
        save_fields = list(theme_fields)
        if hasattr(site, "updated_at"):
            save_fields.append("updated_at")
        if save_fields:
            site.save(update_fields=save_fields)

        actor_label = (
            request.user.get_username() if request.user.is_authenticated else "system"
        )
        now_label = timezone.localtime().strftime("%Y-%m-%d %H:%M")
        request.session.pop("theme_previous_state", None)
        request.session.pop("site_preview_settings", None)
        request.session.pop("preview_mode_enabled", None)
        request.session["theme_recent_change_meta"] = {
            "status": "rolled_back",
            "actor": actor_label,
            "timestamp": now_label,
            "changed_count": len(theme_fields),
            "changed_fields": theme_fields,
        }
        request.session.modified = True

        try:
            from django.contrib import messages

            messages.success(
                request, "Rolled back theme & experience to the previous saved state."
            )
        except (TypeError, AttributeError, ValueError):
            pass

        redirect_url = reverse("studio_os:experience")
        if _wants_json():
            return JsonResponse({"ok": True, "redirect_url": redirect_url})
        return redirect(redirect_url)
    if mode == "control":
        return redirect(reverse("siteconfig:feature_control_panel") + "?embed=1")
    return redirect(reverse("studio_os:shell"))


# ---- Shared preview engine (2.1): single entry point per mode ----


@never_cache
@require_http_methods(["POST"])
@login_required
def studio_preview(request):
    """
    Shared preview: POST mode=experience (plus form body) delegates to siteconfig preview_from_form;
    other modes return redirect_url to embed so client can open preview in new tab.
    """
    if not user_can_access_studio_on_request(request):
        return JsonResponse({"errors": ["Staff required"]}, status=403)
    mode = (request.POST.get("mode") or "").strip().lower()
    if mode == "experience":
        from apps.siteconfig.views import preview_from_form

        return preview_from_form(request)
    if mode in ("automation", "output", "launch", "control"):
        redirect_url = get_studio_preview_url(mode, request)
        if redirect_url:
            payload = {"redirect_url": redirect_url}
            # §5.6 Live Previews: include impact summary and dependency warnings when available
            preview_ctx = get_studio_preview_context(mode, request)
            if preview_ctx:
                payload["impact_summary"] = preview_ctx.get("impact_summary")
                payload["dependency_warnings"] = preview_ctx.get(
                    "dependency_warnings", []
                )
                if preview_ctx.get("health_summary"):
                    payload["health_summary"] = preview_ctx["health_summary"]
                if preview_ctx.get("recommended_next"):
                    payload["recommended_next"] = preview_ctx["recommended_next"]
            return JsonResponse(payload)
        return JsonResponse(
            {"errors": ["Preview URL not available for this mode."]}, status=400
        )
    return JsonResponse({"errors": ["Missing or invalid mode."]}, status=400)


@never_cache
@require_http_methods(["POST"])
@login_required
def studio_publish_api(request):
    """
    Shared publish: validate and persist. Experience uses perform_theme_experience_publish;
    other modes use services.studio_publish. Returns JSON {ok, redirect_url} or {ok: false, errors}.
    """
    if not user_can_access_studio_on_request(request):
        return JsonResponse({"ok": False, "errors": ["Staff required"]}, status=403)
    mode = (request.POST.get("mode") or "").strip().lower()
    if mode == "experience":
        from apps.siteconfig.views import perform_theme_experience_publish

        result = perform_theme_experience_publish(request)
        status = 200 if result.get("ok") else 400
        return JsonResponse(result, status=status)
    payload = dict(request.POST.items())
    result = studio_publish(mode, request, payload)
    status = 200 if result.get("ok") else 400
    return JsonResponse(result, status=status)


@never_cache
@require_http_methods(["POST"])
@login_required
def studio_save_draft_api(request):
    """Save draft (session stash). Returns JSON {ok} or {ok: false, errors}."""
    if not user_can_access_studio_on_request(request):
        return JsonResponse({"ok": False, "errors": ["Staff required"]}, status=403)
    mode = (request.POST.get("mode") or "").strip().lower()
    payload = dict(request.POST.items())
    result = studio_save_draft(mode, request, payload)
    status = 200 if result.get("ok") else 400
    return JsonResponse(result, status=status)


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_version_history_api(request):
    """GET ?mode=experience — version history for the mode. JSON list of {version, timestamp, actor, label}."""
    if not user_can_access_studio_on_request(request):
        return JsonResponse({"versions": []})
    mode = (request.GET.get("mode") or "").strip().lower()
    try:
        limit = min(20, max(1, int(request.GET.get("limit", 10))))
    except (TypeError, ValueError):
        limit = 10
    versions = get_studio_version_history(request, mode, limit=limit)
    return JsonResponse({"versions": versions})


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_global_search(request):
    """§4.1 global search API. GET ?q= — returns JSON {results: [{label, url, kind}]}."""
    if not user_can_access_studio_on_request(request):
        return JsonResponse({"results": []})
    q = (request.GET.get("q") or "").strip()
    try:
        limit = min(50, max(1, int(request.GET.get("limit", 20))))
    except (TypeError, ValueError):
        limit = 20
    results = get_studio_global_search(request, q, limit=limit)
    return JsonResponse({"results": results})


def studio_audit_api(request):
    """GET ?mode= — recent publish/rollback events. JSON list of activity items."""
    if not user_can_access_studio_on_request(request):
        return JsonResponse({"audit": []})
    mode = (request.GET.get("mode") or "").strip().lower() or None
    try:
        limit = min(50, max(1, int(request.GET.get("limit", 20))))
    except (TypeError, ValueError):
        limit = 20
    audit = get_studio_publish_audit(request, mode, limit=limit)
    return JsonResponse({"audit": audit})

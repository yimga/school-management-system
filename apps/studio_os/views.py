# -*- coding: utf-8 -*-
"""
Studio OS — single shell with five work modes.
Replaces fragmented customizer / theme / feature control / report library / workflow hub with one workspace.
Shared preview (2.1) and publish/rollback (2.2) via studio_preview, studio_publish_api, studio_save_draft_api.
"""

import logging

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
    log_control_plane_action,
    use_control_plane_shell,
    user_can_access_studio_on_request,
    user_has_control_plane_access,
)
from .services import (
    get_studio_activity_feed,
    get_studio_compare_context,
    get_automation_dependency_graph,
    get_studio_global_search,
    get_studio_mode_hero_context,
    get_studio_operator_toolbar,
    get_studio_overview_deck,
    get_studio_preview_context,
    get_studio_preview_url,
    get_studio_publish_audit,
    get_studio_recommendations,
    get_studio_role_preview_entries,
    get_studio_command_palette_entries,
    get_studio_version_history,
    get_output_dependency_graph,
    get_output_report_pack_preview_cards,
    studio_rollback_available,
    studio_publish,
    studio_save_draft,
)

STUDIO_MODES = [
    {
        "id": "experience",
        "label": "Experience",
        "description": "Shape branding, theme, and portals",
        "workflow_step_count": 4,
        "workflow_typical_minutes": 12,
    },
    {
        "id": "automation",
        "label": "Automation",
        "description": "Workflows, approvals, and automation",
        "workflow_step_count": 5,
        "workflow_typical_minutes": 18,
    },
    {
        "id": "output",
        "label": "Outputs",
        "description": "Reports, documents, and exports",
        "workflow_step_count": 3,
        "workflow_typical_minutes": 10,
    },
    {
        "id": "launch",
        "label": "Launch",
        "description": "Setup and go live",
        "workflow_step_count": 6,
        "workflow_typical_minutes": 25,
    },
    {
        "id": "control",
        "label": "Control",
        "description": "Capabilities, policies, and runtime",
        "workflow_step_count": 4,
        "workflow_typical_minutes": 15,
    },
]


def _automation_studio_base_url() -> str:
    try:
        return reverse("studio_os:automation")
    except NoReverseMatch:
        return ""


def _resolve_automation_iframe_src(pane: str, request=None) -> str:
    """Automation Studio: iframe only for heavy / external surfaces; default pane is native."""
    from apps.studio_os.deep_links import resolve_studio_href, url_is_cross_origin_request

    key = (pane or "").strip().lower()
    mapping = {
        "outcomes": ("automation:outcomes_console", True),
        "workflow": ("studio_os:workflow_center", True),
        "flow_gallery": ("siteconfig:workflow_flow_gallery", False),
        "approval": ("studio_os:approval_hub", False),
    }
    if key not in mapping:
        return ""
    vn, emb = mapping[key]
    u = resolve_studio_href(vn, embed=emb) or ""
    if request and u and url_is_cross_origin_request(request, u):
        return ""
    return u


def _automation_explainer_context(pane: str):
    """Context for in-shell explainer panes (native HTML, no iframe)."""
    from django.utils.translation import gettext as gt

    wf = ""
    try:
        wf = reverse("studio_os:automation") + "?pane=workflow"
    except NoReverseMatch:
        pass
    hint = gt("Manage flows, run simulations, and activate workflows.")
    explainers = {
        "conflict": {
            "title": gt("Conflict detection"),
            "subtitle": "",
            "body": gt(
                "Conflict detection helps identify overlapping or incompatible workflow definitions before activation. "
                "Use the Workflow center to run simulations and review dependencies; resolve conflicts there before enabling new flows."
            ),
            "workflow_hint": hint,
        },
        "staged": {
            "title": gt("Staged activation"),
            "subtitle": "",
            "body": gt(
                "Roll out workflow changes in stages: preview impact, enable for a subset, then promote. "
                "Use the Workflow center to run simulations before full activation."
            ),
            "workflow_hint": hint,
        },
        "replay": {
            "title": gt("Replay / rollback"),
            "subtitle": "",
            "body": gt(
                "Review workflow runs, replay instances for debugging, and roll back when needed. "
                "Use Automation rollback from the Studio toolbar when available."
            ),
            "workflow_hint": gt(
                "View runs, replay instances, and manage workflow config."
            ),
        },
        "visual_builder": {
            "title": gt("Visual builder"),
            "subtitle": "",
            "body": gt(
                "Build workflows visually with drag-and-drop: add steps, connect conditions, and define triggers. "
                "The Workflow center is where you create and edit flows; a full visual builder can integrate there when productized."
            ),
            "workflow_hint": gt("Manage flows and workflow templates."),
        },
        "nl_workflow": {
            "title": gt("Natural-language workflow"),
            "subtitle": "",
            "body": gt(
                "Describe automations in plain language; the system maps intent to workflow steps where supported. "
                "Use the Workflow center to refine and activate generated flows."
            ),
            "workflow_hint": gt("Create and manage workflows."),
        },
        "simulation": {
            "title": gt("Simulation engine"),
            "subtitle": "",
            "body": gt(
                "Run workflow simulations before going live. Verify behavior and impact from the Workflow center, then activate when ready."
            ),
            "workflow_hint": gt("Run simulations and activate workflows."),
        },
    }
    data = explainers.get((pane or "").strip().lower())
    if not data:
        return None
    return {
        "title": data["title"],
        "subtitle": data.get("subtitle", ""),
        "body": data["body"],
        "workflow_pane_url": wf,
        "workflow_hint": data.get("workflow_hint", hint),
    }


def _resolve_launch_iframe_src(request, pane: str) -> str:
    """Launch Studio: iframe for wizards; overview/plan/role_preview are native."""
    from apps.studio_os.deep_links import resolve_studio_href, url_is_cross_origin_request

    key = (pane or "").strip().lower()
    host_kind = getattr(request, "public_host_kind", None) if request is not None else None
    mapping = {
        "onboarding": ("siteconfig:guided_onboarding", True),
        "create_school": ("super:create_school_wizard", True),
        "blueprints": ("siteconfig:get_blueprints", True),
        "branding": ("studio_os:experience", True),
        "checklist": ("siteconfig:guided_onboarding", True),
        "migration": ("accounts:migration_wizard", True),
    }
    if key not in mapping:
        return ""
    vn, emb = mapping[key]
    if host_kind != "manager" and vn.startswith(("super:", "admin:")):
        return ""
    u = resolve_studio_href(vn, embed=emb) or ""
    if request and u and url_is_cross_origin_request(request, u):
        return ""
    return u


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
    allow_manager_links = getattr(request, "public_host_kind", None) == "manager"

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
        if not mgr or not allow_manager_links:
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

    from apps.siteconfig.control_outcome_center import (
        WHY_ENABLED_SUMMARY,
        build_operator_control_model_for_request,
        build_outcome_groups_for_request,
    )

    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/system_config_console.html",
        embed_title=_("Configuration Control Center") + " · " + str(_("Control")),
        shell_title=_("Configuration Control Center") + " · " + str(_("Control")),
        page_context={
            "page_title": _("Configuration Control Center"),
            "page_subtitle": _(
                "Outcome-based surfaces — runtime, packs, policy, entitlements, overrides. "
                "Each link opens the real tool; manager-only items use your platform host when needed."
            ),
            "config_links": links,
            "outcome_groups": build_outcome_groups_for_request(request),
            "why_enabled_summary": WHY_ENABLED_SUMMARY,
            "operator_control_model": build_operator_control_model_for_request(request),
            "action_url": reverse("studio_os:control"),
            "action_text": _("Back to Control"),
        },
        current_mode="control",
        extra_css="css/studio-system-config-console.css",
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_control_impact(request):
    """§4.6 Control Studio optional: Diff / impact summary. Renders control mode impact_summary for embedding in rail."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    preview_ctx = get_studio_preview_context("control", request)
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/control_impact.html",
        embed_title=_("Diff / impact summary") + " · " + str(_("Control")),
        shell_title=_("Diff / impact summary") + " · " + str(_("Control")),
        page_context={
            "impact_summary": preview_ctx.get("impact_summary") or "",
            "dependency_warnings": preview_ctx.get("dependency_warnings") or [],
            "page_title": _("Diff / impact summary"),
            "page_subtitle": _(
                "Review feature toggles and runtime state before publishing. Use Runtime inspector for impact and source tracing."
            ),
            "action_url": reverse("studio_os:control"),
            "action_text": _("Back to Control"),
        },
        current_mode="control",
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_ai_cleanup(request):
    """§4.6 Control Studio optional: AI cleanup suggestions. Renders control-mode recommendations for embedding in rail."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    recs = get_studio_recommendations(request, "control")
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/ai_cleanup.html",
        embed_title=_("AI cleanup suggestions") + " · " + str(_("Control")),
        shell_title=_("AI cleanup suggestions") + " · " + str(_("Control")),
        page_context={
            "recommendations": recs,
            "page_title": _("AI cleanup suggestions"),
            "page_subtitle": _(
                "Capabilities and audit log suggestions for feature state."
            ),
            "action_url": reverse("studio_os:control"),
            "action_text": _("Back to Control"),
        },
        current_mode="control",
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_experience_recommendations(request):
    """§4.2 Experience Studio optional: AI recommendations. Renders experience-mode recommendations for embedding in rail."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    recs = get_studio_recommendations(request, "experience")
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/experience_recommendations.html",
        embed_title=_("AI recommendations") + " · " + str(_("Experience")),
        shell_title=_("AI recommendations") + " · " + str(_("Experience")),
        page_context={
            "recommendations": recs,
            "page_title": _("AI recommendations"),
            "page_subtitle": _("Experience-mode suggestions for theme and branding."),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
        current_mode="experience",
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_experience_compare(request):
    """§4.2 Experience Studio optional: Compare (before/after). §5.6 Live Previews: Add before/after."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    compare_ctx = get_studio_compare_context(request, "experience")
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/experience_compare.html",
        embed_title=_("Compare (before / after)") + " · " + str(_("Experience")),
        shell_title=_("Compare (before / after)") + " · " + str(_("Experience")),
        page_context={
            "before_entries": compare_ctx.get("before_entries") or [],
            "after_entries": compare_ctx.get("after_entries") or [],
            "has_before": compare_ctx.get("has_before", False),
            "page_title": _("Compare (before / after)"),
            "page_subtitle": _(
                "Publish a theme change to see before/after comparison."
            ),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
        current_mode="experience",
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
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/experience_theme_tokens.html",
        embed_title=_("Theme tokens") + " · " + str(_("Experience")),
        shell_title=_("Theme tokens") + " · " + str(_("Experience")),
        page_context={
            "theme_colors_url": theme_url,
            "page_title": _("Theme tokens"),
            "page_subtitle": _(
                "Design tokens (CSS variables) drive theme and in-shell form; configure in Theme & colors."
            ),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
        current_mode="experience",
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
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/experience_portal_shell_layouts.html",
        embed_title=_("Portal shell layouts") + " · " + str(_("Experience")),
        shell_title=_("Portal shell layouts") + " · " + str(_("Experience")),
        page_context={
            "customizer_url": customizer_url,
            "page_title": _("Portal shell layouts"),
            "page_subtitle": _(
                "Portal shell structure (sidebar, header, content areas); configure in Customizer and School theme."
            ),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
        current_mode="experience",
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
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/experience_dashboard_visual_packs.html",
        embed_title=_("Dashboard visual packs") + " · " + str(_("Experience")),
        shell_title=_("Dashboard visual packs") + " · " + str(_("Experience")),
        page_context={
            "dashboard_url": dashboard_url,
            "customizer_url": customizer_url,
            "page_title": _("Dashboard visual packs"),
            "page_subtitle": _(
                "Widgets, charts, and layout presets for role-based dashboards; configure in Backend dashboard and Customizer."
            ),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
        current_mode="experience",
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
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/experience_school_website_blocks.html",
        embed_title=_("School website blocks") + " · " + str(_("Experience")),
        shell_title=_("School website blocks") + " · " + str(_("Experience")),
        page_context={
            "marketing_url": marketing_url,
            "customizer_url": customizer_url,
            "page_title": _("School website blocks"),
            "page_subtitle": _(
                "Landing page sections, hero, and content blocks for your school website; configure in Customizer and marketing pages."
            ),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
        current_mode="experience",
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
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/experience_communication_style_packs.html",
        embed_title=_("Communication style packs") + " · " + str(_("Experience")),
        shell_title=_("Communication style packs") + " · " + str(_("Experience")),
        page_context={
            "customizer_url": customizer_url,
            "page_title": _("Communication style packs"),
            "page_subtitle": _(
                "Tone, templates, and notification styles for parent and staff communications; configure in Customizer and communication settings."
            ),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
        current_mode="experience",
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
    installed_packages_url = ""
    try:
        theme_colors_url = reverse("siteconfig:theme_colors") + "?embed=1"
    except NoReverseMatch:
        pass
    try:
        installed_packages_url = reverse("siteconfig:installed_packages_rollback")
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
    pack_catalog = {}
    pack_catalog_warnings: list[str] = []
    try:
        from apps.marketplace.pack_registry import (
            load_platform_pack_catalog,
            validate_platform_pack_catalog,
        )

        pack_catalog = load_platform_pack_catalog()
        pack_catalog_warnings = validate_platform_pack_catalog(pack_catalog)
    except (ImportError, ValueError, OSError, TypeError):
        try:
            from apps.studio_os.school_infrastructure import (
                load_pack_catalog_from_disk,
                validate_pack_catalog_entries,
            )

            pack_catalog = load_pack_catalog_from_disk()
            pack_catalog_warnings = validate_pack_catalog_entries(pack_catalog)
        except (ImportError, OSError, TypeError, ValueError):
            pack_catalog = {}
            pack_catalog_warnings = []
    launch_infrastructure_url = ""
    try:
        launch_infrastructure_url = (
            reverse("studio_os:launch") + "?pane=infrastructure"
        )
    except NoReverseMatch:
        pass
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/experience_experience_packs.html",
        embed_title=_("Experience packs") + " · " + str(_("Experience")),
        shell_title=_("Experience packs") + " · " + str(_("Experience")),
        page_context={
            "effective_pack": effective_pack,
            "pack_count": pack_count,
            "theme_colors_url": theme_colors_url,
            "installed_packages_url": installed_packages_url,
            "package_impact_fetch_url": package_impact_fetch_url,
            "experience_graph_package_id": experience_graph_package_id,
            "school": school,
            "page_title": _("Experience packs"),
            "page_subtitle": _(
                "Packageable theme, layout, dashboard visual, and communication style. Assign per school; compare and rollback from Experience Studio."
            ),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
            "platform_pack_catalog": pack_catalog,
            "platform_pack_catalog_warnings": pack_catalog_warnings,
            "launch_infrastructure_url": launch_infrastructure_url,
        },
        current_mode="experience",
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_output_dependency_graph(request):
    """§4.4 Output Studio optional: Dependency graph. Shows report pack dependencies for embedding in Output rail."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    graph = get_output_dependency_graph()
    out_base = reverse("studio_os:output")
    pack_preview_cards = get_output_report_pack_preview_cards(out_base=out_base)
    focus = (request.GET.get("pack") or "").strip()[:160]
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/output_dependency_graph.html",
        embed_title=_("Dependency graph") + " · " + str(_("Outputs")),
        shell_title=_("Dependency graph") + " · " + str(_("Outputs")),
        page_context={
            "graph": graph,
            "pack_preview_cards": pack_preview_cards,
            "focus_pack_code": focus,
            "page_title": _("Dependency graph"),
            "page_subtitle": _(
                "Report packs and their dependencies (fields, policies, templates)."
            ),
            "action_url": reverse("studio_os:output"),
            "action_text": _("Back to Outputs"),
        },
        current_mode="output",
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
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/output_branding_inheritance.html",
        embed_title=_("Branding inheritance") + " · " + str(_("Outputs")),
        shell_title=_("Branding inheritance") + " · " + str(_("Outputs")),
        page_context={
            "theme_colors_url": theme_url,
            "page_title": _("Branding inheritance"),
            "page_subtitle": _(
                "Reports and documents inherit school and theme branding. Configure theme and colors to control outputs."
            ),
            "action_url": reverse("studio_os:output"),
            "action_text": _("Back to Outputs"),
        },
        current_mode="output",
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
        report_library_url = reverse("studio_os:output") + "?pane=reports"
    except NoReverseMatch:
        pass
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/output_policy_registry.html",
        embed_title=_("Policy & registry") + " · " + str(_("Outputs")),
        shell_title=_("Policy & registry") + " · " + str(_("Outputs")),
        page_context={
            "page_title": _("Policy & registry"),
            "page_subtitle": _(
                "Reports and report packs align with policy (blueprints, grading, terms) and metadata registry (lineage, fields). Use Output Studio · Report library & letters; Control for policy and lineage."
            ),
            "action_url": reverse("studio_os:output"),
            "action_text": _("Back to Outputs"),
            "blueprints_url": blueprints_url,
            "lineage_url": lineage_url,
            "report_library_url": report_library_url,
        },
        current_mode="output",
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_launch_select_plan(request):
    """§4.5 Launch Studio: Select plan. Placeholder when plans not productized; rail entry and view wired for when plan product ships."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/launch_select_plan.html",
        embed_title=_("Select plan") + " · " + str(_("Launch")),
        shell_title=_("Select plan") + " · " + str(_("Launch")),
        page_context={
            "page_title": _("Select plan"),
            "page_subtitle": _(
                "Choose your school's plan and entitlements. Full plan picker when productized."
            ),
            "action_url": reverse("studio_os:launch"),
            "action_text": _("Back to Launch"),
        },
        current_mode="launch",
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
        workflow_hub_url = reverse("studio_os:automation") + "?pane=workflow"
    except NoReverseMatch:
        pass
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/automation_conflict_detection.html",
        embed_title=_("Conflict detection") + " · " + str(_("Automation")),
        shell_title=_("Conflict detection") + " · " + str(_("Automation")),
        page_context={
            "workflow_hub_url": workflow_hub_url,
            "page_title": _("Conflict detection"),
            "page_subtitle": _(
                "Detect and resolve conflicts before activating workflows."
            ),
            "action_url": reverse("studio_os:automation"),
            "action_text": _("Back to Automation"),
        },
        current_mode="automation",
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
        workflow_hub_url = reverse("studio_os:automation") + "?pane=workflow"
    except NoReverseMatch:
        pass
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/automation_staged_activation.html",
        embed_title=_("Staged activation") + " · " + str(_("Automation")),
        shell_title=_("Staged activation") + " · " + str(_("Automation")),
        page_context={
            "workflow_hub_url": workflow_hub_url,
            "page_title": _("Staged activation"),
            "page_subtitle": _(
                "Activate workflows in stages; run simulations before going live."
            ),
            "action_url": reverse("studio_os:automation"),
            "action_text": _("Back to Automation"),
        },
        current_mode="automation",
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
        workflow_hub_url = reverse("studio_os:automation") + "?pane=workflow"
    except NoReverseMatch:
        pass
    try:
        rollback_url = reverse("studio_os:rollback") + "?mode=automation"
    except NoReverseMatch:
        pass
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/automation_replay_rollback.html",
        embed_title=_("Replay / rollback") + " · " + str(_("Automation")),
        shell_title=_("Replay / rollback") + " · " + str(_("Automation")),
        page_context={
            "workflow_hub_url": workflow_hub_url,
            "rollback_url": rollback_url,
            "page_title": _("Replay / rollback"),
            "page_subtitle": _(
                "Re-run workflow instances and roll back workflow or config changes."
            ),
            "action_url": reverse("studio_os:automation"),
            "action_text": _("Back to Automation"),
        },
        current_mode="automation",
    )


def _automation_explainer_view(
    request, canvas_partial: str, page_title: str, page_subtitle: str
):
    """Shared helper for Automation Studio explainer pages (staff-only, workflow_hub_url, action back to automation)."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    workflow_hub_url = ""
    try:
        workflow_hub_url = reverse("studio_os:automation") + "?pane=workflow"
    except NoReverseMatch:
        pass
    return _render_studio_subpage(
        request,
        canvas_partial=canvas_partial,
        embed_title=f"{page_title} · {str(_('Automation'))}",
        shell_title=f"{page_title} · {str(_('Automation'))}",
        page_context={
            "workflow_hub_url": workflow_hub_url,
            "page_title": page_title,
            "page_subtitle": page_subtitle,
            "action_url": reverse("studio_os:automation"),
            "action_text": _("Back to Automation"),
        },
        current_mode="automation",
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_automation_visual_builder(request):
    """§4.3 Automation Studio optional: Visual builder. Links to relational workflow designer + Workflow hub."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    workflow_hub_url = ""
    try:
        workflow_hub_url = reverse("studio_os:automation") + "?pane=workflow"
    except NoReverseMatch:
        pass
    visual_workflow_designer_url = ""
    try:
        visual_workflow_designer_url = reverse("automation:visual_workflow_designer")
    except NoReverseMatch:
        pass
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/automation_visual_builder.html",
        embed_title=f"{_('Visual builder')} · {str(_('Automation'))}",
        shell_title=f"{_('Visual builder')} · {str(_('Automation'))}",
        page_context={
            "workflow_hub_url": workflow_hub_url,
            "visual_workflow_designer_url": visual_workflow_designer_url,
            "page_title": _("Visual builder"),
            "page_subtitle": _(
                "Build workflows visually with drag-and-drop; connect steps and conditions. Open the visual designer or manage flows from the Workflow hub."
            ),
            "action_url": reverse("studio_os:automation"),
            "action_text": _("Back to Automation"),
        },
        current_mode="automation",
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_automation_natural_language_workflow(request):
    """§4.3 Automation Studio optional: Natural-language workflow generation. Explains NL-to-workflow; links to Workflow hub."""
    return _automation_explainer_view(
        request,
        "studio_os/partials/subpages/automation_natural_language_workflow.html",
        _("Natural-language workflow"),
        _(
            "Describe workflows in plain language; the system suggests or generates flow steps. Refine and activate from the Workflow hub."
        ),
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_automation_simulation_engine(request):
    """§4.3 Automation Studio: simulation guidance + canonical trigger payloads + API pointers."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    workflow_hub_url = ""
    try:
        workflow_hub_url = reverse("studio_os:automation") + "?pane=workflow"
    except NoReverseMatch:
        pass
    visual_designer_url = ""
    outcomes_console_url = ""
    simulate_api_url = ""
    dispatch_test_api_url = ""
    publish_api_url = ""
    try:
        visual_designer_url = reverse("automation:visual_workflow_designer")
    except NoReverseMatch:
        pass
    try:
        outcomes_console_url = reverse("automation:outcomes_console")
    except NoReverseMatch:
        pass
    try:
        simulate_api_url = reverse("automation:visual_workflow_simulate")
    except NoReverseMatch:
        pass
    try:
        dispatch_test_api_url = reverse("automation:visual_workflow_dispatch_test")
    except NoReverseMatch:
        pass
    try:
        publish_api_url = reverse("automation:visual_workflow_publish")
    except NoReverseMatch:
        pass

    domain_events_console_url = ""
    try:
        domain_events_console_url = reverse("events:event_console")
    except NoReverseMatch:
        pass
    domain_events_analytics_url = ""
    try:
        domain_events_analytics_url = reverse("events:event_analytics_console")
    except NoReverseMatch:
        pass

    school = getattr(request, "school", None)
    school_id = str(school.pk) if school is not None else ""
    canonical_triggers = []
    if school_id:
        from apps.automation.workflow_trigger_catalog import (
            get_operator_trigger_catalog_for_school,
        )

        canonical_triggers = get_operator_trigger_catalog_for_school(
            school_id, slice_only=False
        )

    ready_playbooks = []
    if school_id:
        from apps.automation.workflow_playbook_templates import (
            enrich_playbooks_for_template,
        )

        ready_playbooks = enrich_playbooks_for_template(school_id)

    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/automation_simulation_engine.html",
        embed_title=f"{_('Simulation engine')} · {str(_('Automation'))}",
        shell_title=f"{_('Simulation engine')} · {str(_('Automation'))}",
        page_context={
            "workflow_hub_url": workflow_hub_url,
            "visual_designer_url": visual_designer_url,
            "outcomes_console_url": outcomes_console_url,
            "simulate_api_url": simulate_api_url,
            "dispatch_test_api_url": dispatch_test_api_url,
            "publish_api_url": publish_api_url,
            "domain_events_console_url": domain_events_console_url,
            "domain_events_analytics_url": domain_events_analytics_url,
            "canonical_triggers": canonical_triggers,
            "ready_playbooks": ready_playbooks,
            "page_title": _("Simulation engine"),
            "page_subtitle": _(
                "Preview triggers, conditions, and actions before publishing. "
                "Simulation is dry-run only; live runs write audit rows visible in Automation outcomes."
            ),
            "action_url": reverse("studio_os:automation"),
            "action_text": _("Back to Automation"),
        },
        current_mode="automation",
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_automation_dependency_graph(request):
    """§4.3 Automation Studio optional: Dependency graph. Shows workflow packs and their templates for embedding in Automation rail."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    graph = get_automation_dependency_graph()
    try:
        auto_back = reverse("studio_os:automation") + "?pane=dependency"
    except NoReverseMatch:
        auto_back = reverse("studio_os:automation")
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/automation_dependency_graph.html",
        embed_title=_("Dependency graph") + " · " + str(_("Automation")),
        shell_title=_("Dependency graph") + " · " + str(_("Automation")),
        page_context={
            "graph": graph,
            "page_title": _("Dependency graph"),
            "page_subtitle": _(
                "Workflow packs and their templates (pack → templates)."
            ),
            "action_url": auto_back,
            "action_text": _("Back to Automation"),
        },
        current_mode="automation",
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_automation_workflow_health(request):
    """§4.3 Automation Studio optional: Workflow health metrics. Summary of active packs and templates."""
    if not user_can_access_studio_on_request(request):
        return redirect(reverse("accounts:backend_dashboard"))
    from apps.studio_os.services import get_automation_workflow_health_summary

    summary = get_automation_workflow_health_summary(request)
    workflow_center_pane_url = ""
    try:
        workflow_center_pane_url = reverse("studio_os:automation") + "?pane=workflow"
    except NoReverseMatch:
        pass
    return _render_studio_subpage(
        request,
        canvas_partial="studio_os/partials/subpages/automation_workflow_health.html",
        embed_title=_("Workflow health metrics") + " · " + str(_("Automation")),
        shell_title=_("Workflow health metrics") + " · " + str(_("Automation")),
        page_context={
            "pack_count": summary.get("pack_count", 0),
            "template_count": summary.get("template_count", 0),
            "workflow_center_pane_url": workflow_center_pane_url,
            "page_title": _("Workflow health metrics"),
            "page_subtitle": _(
                "Active workflow packs and templates; run simulations from Workflow center."
            ),
            "action_url": reverse("studio_os:automation"),
            "action_text": _("Back to Automation"),
        },
        current_mode="automation",
    )


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
    rail: list,
    label: str,
    viewname: str,
    *,
    embed: bool = False,
    request=None,
) -> None:
    from apps.studio_os.deep_links import resolve_studio_href, url_is_cross_origin_request

    u = resolve_studio_href(viewname, embed=embed)
    if not u:
        return
    item_embed = bool(embed)
    external = False
    if request is not None and url_is_cross_origin_request(request, u):
        external = True
        item_embed = False
        u = resolve_studio_href(viewname, embed=False) or u
    rail.append(
        {"label": label, "url": u, "embed": item_embed, "external": external}
    )


def _resolve_embed_urls(request):
    """URLs to embed in the Studio canvas per mode. Single-sourced from get_studio_preview_url."""
    return {
        mode: get_studio_preview_url(mode, request)
        for mode in ("experience", "automation", "output", "launch", "control")
    }


def _request_wants_studio_embed(request) -> bool:
    return (request.GET.get("embed") or "").strip().lower() in ("1", "true", "yes")


def _studio_subpage_context(request, current_mode: str | None) -> dict:
    legacy_urls = _resolve_legacy_urls(request)
    activity_feed = get_studio_activity_feed(request)
    recommendations = get_studio_recommendations(request, current_mode)
    command_palette_entries = get_studio_command_palette_entries(request)
    rollback_available = (
        studio_rollback_available(current_mode, request) if current_mode else False
    )
    preview_from_form_url = ""
    studio_preview_url = ""
    studio_publish_url = ""
    try:
        preview_from_form_url = reverse("siteconfig:preview_from_form")
    except NoReverseMatch:
        pass
    try:
        studio_preview_url = reverse("studio_os:preview")
    except NoReverseMatch:
        studio_preview_url = preview_from_form_url
    try:
        studio_publish_url = reverse("studio_os:publish")
    except NoReverseMatch:
        pass
    ctx: dict = {
        "studio_modes": STUDIO_MODES,
        "current_mode": current_mode,
        "legacy_urls": legacy_urls,
        "embed_url": None,
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
    if rollback_available and current_mode:
        try:
            ctx["studio_rollback_url"] = (
                reverse("studio_os:rollback") + "?mode=" + current_mode
            )
        except NoReverseMatch:
            pass
    if current_mode == "automation":
        try:
            from apps.studio_os.services import get_automation_workflow_health_summary

            ctx["automation_health_summary"] = get_automation_workflow_health_summary(
                request
            )
        except (ImportError, AttributeError, TypeError, ValueError):
            ctx["automation_health_summary"] = {}
        ctx["automation_simulation_summary"] = _(
            "Run simulation from Workflow center to see impact before activating."
        )
    return ctx


def _render_studio_subpage(
    request,
    *,
    canvas_partial: str,
    embed_title: str,
    shell_title: str,
    page_context: dict,
    current_mode: str | None,
    extra_css: str | None = None,
):
    """
    Full Studio chrome (rail + command palette + context rail) unless ?embed=1
    (portal-only body for iframes and embedded rail links).
    """
    if _request_wants_studio_embed(request):
        emb = dict(page_context)
        emb["studio_embed_title"] = embed_title
        emb["studio_subpage_canvas_partial"] = canvas_partial
        emb["studio_subpage_extra_css"] = extra_css or ""
        return render(request, "studio_os/studio_subpage_embed.html", emb)

    ctx = _studio_subpage_context(request, current_mode)
    ctx.update(page_context)
    ctx["studio_subpage_title"] = shell_title
    ctx["studio_native_canvas_partial"] = canvas_partial
    if use_control_plane_shell(request):
        return render(request, "studio_os/shell_control_plane.html", ctx)
    return render(request, "studio_os/shell_subpage_wrap.html", ctx)


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

    if not mode:
        context["studio_overview_deck"] = get_studio_overview_deck(
            request,
            modes=STUDIO_MODES,
            recommendations=recommendations,
            activity_feed=activity_feed,
            legacy_urls=legacy_urls,
        )
        # v3.54.0 (2026-05-21): Overview command cockpit signal strip context. The 5-key
        # shape is consumed by templates/studio_os/partials/cockpit_signal_strip.html +
        # overview_command_cockpit.html. Keys may be int or None; None renders as honest
        # "—" placeholder with data-state="unknown" rather than fabricated zeros.
        # Backend wiring landed in v3.54.0 closeout via services.get_overview_signals;
        # the helper is defensive and returns None for any signal whose source is
        # unavailable, preserving the honest "unknown" UI state.
        try:
            from apps.studio_os.services import get_overview_signals

            context["overview_signals"] = get_overview_signals(request)
        except (ImportError, AttributeError, TypeError, ValueError):
            log_exception_with_context(
                "studio_shell overview: get_overview_signals failed",
                **request_context_for_log(request),
                extra={"mode": "overview"},
            )
            context["overview_signals"] = {
                "pending_launches": None,
                "draft_experiences": None,
                "active_automations": None,
                "output_readiness_pct": None,
                "open_blockers": None,
            }
        # Mirror launch_health_summary + launch_ready into Overview context so the
        # right-rail "Studio readiness" branch (shell.html v3.54.0) has signal.
        # Honest empty state when school absent or setup_studio payload unavailable.
        _overview_school = getattr(request, "school", None)
        context["launch_health_summary"] = ""
        context["launch_ready"] = False
        if _overview_school is not None:
            try:
                from apps.setup_studio.services import get_setup_studio_payload

                _overview_payload = get_setup_studio_payload(_overview_school)
                context["launch_health_summary"] = _overview_payload.get("health_summary") or ""
                context["launch_ready"] = bool(_overview_payload.get("launch_ready", False))
            except (ImportError, AttributeError, TypeError, ValueError):
                log_exception_with_context(
                    "studio_shell overview: launch summary mirror failed",
                    **request_context_for_log(request),
                    extra={"mode": "overview"},
                )

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
            context["experience_context_tool_links"] = []
            context["experience_workspace_two_col"] = True
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
            _studio_rail_append(
                experience_rail, label, vn, embed=True, request=request
            )
        context["experience_left_rail"] = experience_rail
        experience_context_tool_links = []
        for vn, lbl in (
            ("studio_os:experience_compare", _("Compare themes")),
            ("studio_os:experience_recommendations", _("AI recommendations")),
            ("studio_os:experience_packs", _("Experience packs")),
            ("studio_os:experience_theme_tokens", _("Theme tokens")),
            ("studio_os:experience_portal_shell_layouts", _("Portal shell layouts")),
            ("studio_os:experience_dashboard_visual_packs", _("Dashboard visual packs")),
            ("studio_os:experience_school_website_blocks", _("School website blocks")),
            (
                "studio_os:experience_communication_style_packs",
                _("Communication style packs"),
            ),
            ("siteconfig:school_theme_settings", _("School theme")),
            ("siteconfig:brand_import_from_url", _("Import from website")),
        ):
            try:
                experience_context_tool_links.append(
                    {"label": lbl, "url": reverse(vn)}
                )
            except NoReverseMatch:
                pass
        context["experience_context_tool_links"] = experience_context_tool_links
        context["experience_workspace_two_col"] = not bool(experience_context_tool_links)

        try:
            from apps.brand_experience.experience_templates import (
                LAYOUT_FAMILY_NAMES,
                list_overlays,
            )

            _overlay_rows = list_overlays(tenant_safe_only=True)[:8]
            for _row in _overlay_rows:
                _row["layout_family_name"] = LAYOUT_FAMILY_NAMES.get(
                    _row.get("layout_family"), ""
                )
            _tpl_urls: dict[str, str] = {}
            for _name, _url_name in (
                ("browse", "template_marketplace:browse"),
                ("ai_recommend", "template_marketplace:ai_recommend"),
            ):
                try:
                    _tpl_urls[_name] = reverse(_url_name)
                except NoReverseMatch:
                    _tpl_urls[_name] = ""
            if _tpl_urls.get("browse"):
                for _row in _overlay_rows:
                    try:
                        _row["detail_url"] = reverse(
                            "template_marketplace:detail", args=[_row["key"]]
                        )
                    except NoReverseMatch:
                        _row["detail_url"] = ""
            context["experience_template_overlays"] = _overlay_rows
            context["experience_template_marketplace_urls"] = _tpl_urls
        except (ImportError, AttributeError, TypeError, ValueError):
            context["experience_template_overlays"] = []
            context["experience_template_marketplace_urls"] = {}

    if mode == "launch" and school:
        try:
            from apps.setup_studio.services import get_setup_studio_payload

            payload = get_setup_studio_payload(school)
            context["launch_payload"] = payload
            from apps.setup_studio.zero_friction import get_zero_friction_payload

            context["zero_friction"] = get_zero_friction_payload(school)
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
            context["zero_friction"] = None
            context["launch_role_previews"] = []
            context["launch_health_summary"] = ""
            context["launch_ready"] = False
    elif mode == "launch":
        context["launch_payload"] = None
        context["zero_friction"] = None
        context["launch_role_previews"] = []
        context["launch_health_summary"] = ""
        context["launch_ready"] = False

    if mode == "launch":
        # v3.54.0: readiness summary for the launch readiness preview pane.
        # Defensive — honest empty dict on any failure.
        try:
            from apps.studio_os.services import get_launch_readiness_summary

            context["launch_readiness_summary"] = get_launch_readiness_summary(request)
        except (ImportError, AttributeError, TypeError, ValueError):
            log_exception_with_context(
                "studio_shell launch: get_launch_readiness_summary failed",
                **request_context_for_log(request),
                extra={"mode": "launch"},
            )
            context["launch_readiness_summary"] = {}
        launch_base = reverse("studio_os:launch")
        context["launch_studio_base_url"] = launch_base
        context["launch_left_rail"] = [
            {
                "label": _("Overview"),
                "url": f"{launch_base}?pane=overview",
                "pane": "overview",
            },
            {
                "label": _("Guided onboarding"),
                "url": f"{launch_base}?pane=onboarding",
                "pane": "onboarding",
            },
            {
                "label": _("Create school"),
                "url": f"{launch_base}?pane=create_school",
                "pane": "create_school",
            },
            {
                "label": _("Select plan"),
                "url": f"{launch_base}?pane=plan",
                "pane": "plan",
            },
            {
                "label": _("Blueprint gallery"),
                "url": f"{launch_base}?pane=blueprints",
                "pane": "blueprints",
            },
            {
                "label": _("School infrastructure"),
                "url": f"{launch_base}?pane=infrastructure",
                "pane": "infrastructure",
            },
            {
                "label": _("Import branding"),
                "url": f"{launch_base}?pane=branding",
                "pane": "branding",
            },
            {
                "label": _("Migration path"),
                "url": f"{launch_base}?pane=migration",
                "pane": "migration",
            },
            {
                "label": _("Preview by role"),
                "url": f"{launch_base}?pane=role_preview",
                "pane": "role_preview",
            },
            {
                "label": _("Launch checklist"),
                "url": f"{launch_base}?pane=checklist",
                "pane": "checklist",
            },
        ]
        pane_raw = (request.GET.get("pane") or "overview").strip().lower()
        allowed_launch = frozenset(
            {
                "overview",
                "onboarding",
                "create_school",
                "plan",
                "blueprints",
                "infrastructure",
                "branding",
                "migration",
                "role_preview",
                "checklist",
            }
        )
        launch_pane = pane_raw if pane_raw in allowed_launch else "overview"
        context["launch_pane"] = launch_pane
        context["launch_iframe_src"] = _resolve_launch_iframe_src(request, launch_pane)
        try:
            from apps.studio_os.school_infrastructure import (
                get_infrastructure_context_for_shell,
            )

            context.update(get_infrastructure_context_for_shell(request))
        except (ImportError, AttributeError, TypeError, ValueError, OSError, KeyError):
            context["school_template_summaries"] = []
            context["platform_catalog_valid"] = False
            context["current_blueprint_reference"] = None

    if mode == "automation":
        from apps.studio_os.services import get_automation_workflow_health_summary

        auto_base = _automation_studio_base_url()
        if not auto_base:
            try:
                auto_base = reverse("studio_os:automation")
            except NoReverseMatch:
                auto_base = ""
        pane_raw = (request.GET.get("pane") or "overview").strip().lower()
        allowed_auto = frozenset(
            {
                "overview",
                "outcomes",
                "workflow",
                "flow_gallery",
                "approval",
                "dependency",
                "health",
                "conflict",
                "staged",
                "replay",
                "visual_builder",
                "nl_workflow",
                "simulation",
            }
        )
        automation_pane = pane_raw if pane_raw in allowed_auto else "overview"
        context["automation_pane"] = automation_pane
        context["automation_conflict_pane_url"] = (
            f"{auto_base}?pane=conflict" if auto_base else ""
        )
        context["automation_iframe_src"] = _resolve_automation_iframe_src(
            automation_pane, request
        )
        graph = get_automation_dependency_graph()
        context["automation_dependency_graph"] = graph
        summary = get_automation_workflow_health_summary(request)
        context["automation_health_summary"] = summary
        wf_pane = f"{auto_base}?pane=workflow" if auto_base else ""
        context["automation_workflow_center_pane_url"] = wf_pane
        context["automation_simulation_pane_url"] = (
            f"{auto_base}?pane=simulation" if auto_base else ""
        )
        explainer_panes = frozenset(
            {
                "conflict",
                "staged",
                "replay",
                "visual_builder",
                "nl_workflow",
                "simulation",
            }
        )
        if automation_pane in explainer_panes:
            context["automation_explainer"] = _automation_explainer_context(
                automation_pane
            )
        else:
            context["automation_explainer"] = None
        if auto_base:
            context["automation_left_rail"] = [
                {
                    "label": _("Overview"),
                    "url": f"{auto_base}?pane=overview",
                    "pane": "overview",
                },
                {
                    "label": _("Outcomes"),
                    "url": f"{auto_base}?pane=outcomes",
                    "pane": "outcomes",
                },
                {
                    "label": _("Workflow center"),
                    "url": f"{auto_base}?pane=workflow",
                    "pane": "workflow",
                },
                {
                    "label": _("Flow gallery"),
                    "url": f"{auto_base}?pane=flow_gallery",
                    "pane": "flow_gallery",
                },
                {
                    "label": _("Approval hub"),
                    "url": f"{auto_base}?pane=approval",
                    "pane": "approval",
                },
                {
                    "label": _("Dependency graph"),
                    "url": f"{auto_base}?pane=dependency",
                    "pane": "dependency",
                },
                {
                    "label": _("Workflow health metrics"),
                    "url": f"{auto_base}?pane=health",
                    "pane": "health",
                },
                {
                    "label": _("Conflict detection"),
                    "url": f"{auto_base}?pane=conflict",
                    "pane": "conflict",
                },
                {
                    "label": _("Staged activation"),
                    "url": f"{auto_base}?pane=staged",
                    "pane": "staged",
                },
                {
                    "label": _("Replay / rollback"),
                    "url": f"{auto_base}?pane=replay",
                    "pane": "replay",
                },
                {
                    "label": _("Visual builder"),
                    "url": f"{auto_base}?pane=visual_builder",
                    "pane": "visual_builder",
                },
                {
                    "label": _("Natural-language workflow"),
                    "url": f"{auto_base}?pane=nl_workflow",
                    "pane": "nl_workflow",
                },
                {
                    "label": _("Simulation engine"),
                    "url": f"{auto_base}?pane=simulation",
                    "pane": "simulation",
                },
            ]
        else:
            context["automation_left_rail"] = []
        context["workflow_entries"] = []
        context["automation_simulation_summary"] = _(
            "Run simulation from Workflow center to see impact before activating."
        )
        try:
            from apps.studio_os.services import get_automation_simulation_preview

            context["automation_simulation_preview"] = get_automation_simulation_preview(
                request
            )
        except (ImportError, AttributeError, TypeError, ValueError, OSError, KeyError):
            context["automation_simulation_preview"] = None
        try:
            from apps.studio_os.school_infrastructure import (
                get_automation_studio_environment,
            )

            context.update(get_automation_studio_environment(request))
        except (ImportError, AttributeError, TypeError, ValueError, OSError, KeyError):
            context["automation_environment"] = None

    if mode == "output":
        pane_raw = (request.GET.get("pane") or "dependency").strip().lower()
        allowed_panes = frozenset(
            {
                "dependency",
                "reports",
                "documents",
                "builder",
                "credentials",
                "branding",
                "policy",
            }
        )
        output_pane = pane_raw if pane_raw in allowed_panes else "dependency"
        context["output_pane"] = output_pane
        out_base = reverse("studio_os:output")
        context["output_dependency_graph"] = get_output_dependency_graph()
        context["output_pack_preview_cards"] = get_output_report_pack_preview_cards(
            out_base=out_base
        )
        # v3.54.0: readiness summary for the readiness preview pane + cockpit.
        # Defensive — honest empty dict on any failure; templates fall back to
        # derived counts from output_dependency_graph.
        try:
            from apps.studio_os.services import get_output_readiness_summary

            context["output_readiness_summary"] = get_output_readiness_summary()
        except (ImportError, AttributeError, TypeError, ValueError):
            log_exception_with_context(
                "studio_shell output: get_output_readiness_summary failed",
                **request_context_for_log(request),
                extra={"mode": "output"},
            )
            context["output_readiness_summary"] = {}
        _focus_pack = (request.GET.get("pack") or "").strip()
        context["output_focus_pack_code"] = _focus_pack[:160] if _focus_pack else ""
        context["output_doc_library"] = None
        context["output_documents_denied"] = False
        context["output_reportcard_builder"] = None
        context["output_builder_denied"] = False
        context["output_branding_native"] = None
        context["output_policy_native"] = None
        context["output_reports_native"] = None
        context["output_reports_denied"] = False
        context["output_credentials_native"] = None
        _perm = getattr(request.user, "has_feature_permission", lambda _c: False)
        _can_settings = _perm("settings.manage")

        if output_pane == "documents":
            if _can_settings:
                from apps.portal.views_documents import (
                    build_document_library_manage_context,
                )

                context["output_doc_library"] = build_document_library_manage_context(
                    request, studio_output_native=True
                )
            else:
                context["output_documents_denied"] = True
            context["output_iframe_src"] = ""
        elif output_pane == "reports":
            bulk_letters_url = ""
            try:
                bulk_letters_url = reverse("siteconfig:bulk_letters")
            except NoReverseMatch:
                pass
            if _can_settings:
                context["output_reports_native"] = {
                    "page_title": _("Report library & packs"),
                    "page_subtitle": _(
                        "Report packs, bulk letters, and the dependency graph — "
                        "one place in Output Studio (legacy /siteconfig/reports/ redirects here)."
                    ),
                    "dependency_pane_url": f"{out_base}?pane=dependency",
                    "bulk_letters_url": bulk_letters_url,
                    "builder_pane_url": f"{out_base}?pane=builder",
                    "credentials_pane_url": f"{out_base}?pane=credentials",
                    "action_url": out_base,
                    "action_text": _("Back to Outputs"),
                }
            else:
                context["output_reports_denied"] = True
            context["output_iframe_src"] = ""
        elif output_pane == "credentials":
            staff_id_url = ""
            backend_students_url = ""
            try:
                staff_id_url = reverse("portal:my_digital_id")
            except NoReverseMatch:
                pass
            try:
                backend_students_url = reverse("accounts:backend_student_list")
            except NoReverseMatch:
                pass
            context["output_credentials_native"] = {
                "page_title": _("IDs & certificates"),
                "page_subtitle": _(
                    "Digital IDs and printed-style outputs: staff badges, parent/student cards, "
                    "and report certificates. Unfold model pages remain for edge CRUD; prefer Studio "
                    "and portal flows below."
                ),
                "staff_id_url": staff_id_url,
                "backend_students_url": backend_students_url,
                "action_url": reverse("studio_os:output"),
                "action_text": _("Back to Outputs"),
            }
            context["output_iframe_src"] = ""
        elif output_pane == "branding":
            theme_url = ""
            try:
                theme_url = reverse("siteconfig:theme_colors") + "?embed=1"
            except NoReverseMatch:
                pass
            context["output_branding_native"] = {
                "page_title": _("Branding inheritance"),
                "page_subtitle": _(
                    "Reports and documents inherit school theme branding. Configure theme and colors to control outputs."
                ),
                "theme_colors_url": theme_url,
                "action_url": reverse("studio_os:output"),
                "action_text": _("Back to Outputs"),
            }
            context["output_iframe_src"] = ""
        elif output_pane == "policy":
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
                report_library_url = reverse("studio_os:output") + "?pane=reports"
            except NoReverseMatch:
                pass
            context["output_policy_native"] = {
                "page_title": _("Policy & registry"),
                "page_subtitle": _(
                    "Align report packs with policy blueprints and metadata lineage."
                ),
                "blueprints_url": blueprints_url,
                "lineage_url": lineage_url,
                "report_library_url": report_library_url,
                "action_url": reverse("studio_os:output"),
                "action_text": _("Back to Outputs"),
            }
            context["output_iframe_src"] = ""
        elif output_pane == "builder":
            if _can_settings:
                from apps.siteconfig.views import build_reportcard_builder_context

                context["output_reportcard_builder"] = (
                    build_reportcard_builder_context(
                        request, studio_output_native=True
                    )
                )
            else:
                context["output_builder_denied"] = True
            context["output_iframe_src"] = ""
        elif output_pane == "dependency":
            context["output_iframe_src"] = ""
        else:
            context["output_iframe_src"] = ""

        context["output_left_rail"] = [
            {
                "label": _("Report & pack graph"),
                "url": f"{out_base}?pane=dependency",
                "embed": False,
                "pane": "dependency",
            },
            {
                "label": _("Report library & letters"),
                "url": f"{out_base}?pane=reports",
                "embed": False,
                "pane": "reports",
            },
            {
                "label": _("Document library"),
                "url": f"{out_base}?pane=documents",
                "embed": False,
                "pane": "documents",
            },
            {
                "label": _("Report card builder"),
                "url": f"{out_base}?pane=builder",
                "embed": False,
                "pane": "builder",
            },
            {
                "label": _("IDs & certificates"),
                "url": f"{out_base}?pane=credentials",
                "embed": False,
                "pane": "credentials",
            },
            {
                "label": _("Branding inheritance"),
                "url": f"{out_base}?pane=branding",
                "embed": False,
                "pane": "branding",
            },
            {
                "label": _("Policy & registry"),
                "url": f"{out_base}?pane=policy",
                "embed": False,
                "pane": "policy",
            },
        ]

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
        from apps.studio_os.navigation import build_control_governance_rail

        context["control_left_rail"] = build_control_governance_rail(request)
        # Phase 3 — outcome groups (manager + tenant: fallback urlconf resolves super:)
        from apps.siteconfig.control_outcome_center import (
            WHY_ENABLED_SUMMARY,
            build_control_studio_rail_sections,
            build_operator_control_model_for_request,
        )

        context["control_outcome_sections"] = build_control_studio_rail_sections(
            request
        )
        context["why_enabled_summary"] = WHY_ENABLED_SUMMARY
        context["operator_control_model"] = build_operator_control_model_for_request(
            request
        )
        context["control_outcome_hub"] = []
        # In-shell control panel (no iframe) when user has permission
        if request.user.has_perm("settings.feature_control"):
            try:
                from django.template.loader import render_to_string
                from apps.siteconfig.views_feature_control import (
                    get_feature_control_panel_context,
                )

                ctrl_ctx = get_feature_control_panel_context(request)
                ctrl_ctx["control_next_url"] = reverse("studio_os:control")
                ctrl_ctx["studio_inline"] = True
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

    from apps.studio_os.studio_guidance import apply_studio_guidance_to_context

    apply_studio_guidance_to_context(context, mode=mode)

    if mode:
        # The mode hero is decorative chrome; a failure building it must never 500
        # the whole studio shell (defense-in-depth around the automation i18n fix).
        try:
            context["studio_mode_hero"] = get_studio_mode_hero_context(
                mode,
                request,
                legacy_urls=legacy_urls,
                launch_payload=context.get("launch_payload"),
                theme_contrast_report=context.get("theme_contrast_report"),
                output_readiness_summary=context.get("output_readiness_summary"),
                automation_primary_url=context.get("automation_workflow_center_pane_url"),
                automation_secondary_url=context.get("automation_simulation_pane_url"),
                automation_health_summary=context.get("automation_health_summary"),
            )
        except Exception:
            logging.getLogger(__name__).warning(
                "studio_mode_hero build failed (mode=%s)", mode, exc_info=True
            )
            context["studio_mode_hero"] = {}

    if use_control_plane_shell(request):
        context["studio_operator_toolbar"] = get_studio_operator_toolbar(
            request, current_mode=mode
        )
        template = "studio_os/shell_control_plane.html"
    else:
        template = f"studio_os/modes/{mode}.html" if mode else "studio_os/shell.html"
    return render(request, template, context)


@never_cache
@require_http_methods(["POST"])
@login_required
def studio_set_operator_school(request):
    """Set or clear manager-host Studio preview tenant via session school_id (not impersonation)."""
    from django.contrib import messages
    from django.utils.http import url_has_allowed_host_and_scheme
    from django.utils.translation import gettext as _

    from apps.schools.models import School

    if not user_has_control_plane_access(getattr(request, "user", None)):
        return redirect(reverse("accounts:backend_dashboard"))

    fallback = reverse("studio_os:shell")
    next_url = (request.POST.get("next") or fallback).strip()
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = fallback

    school_id = (request.POST.get("school_id") or "").strip()
    if school_id:
        school = School.objects.filter(pk=school_id, is_active=True).first()
        if school is None:
            messages.error(request, _("School not found or inactive."))
            return redirect(next_url)
        request.session["school_id"] = str(school.pk)
        request.session.modified = True
        messages.success(
            request,
            _("Preview context set to %(name)s.") % {"name": school.name},
        )
        log_control_plane_action(
            request,
            "studio_set_operator_school",
            "School",
            str(school.pk),
            object_repr=school.name,
            reason="Studio operator preview context",
            sensitivity="MEDIUM",
        )
    else:
        request.session.pop("school_id", None)
        request.session.modified = True
        messages.info(request, _("Cleared Studio preview tenant."))
        log_control_plane_action(
            request,
            "studio_clear_operator_school",
            "School",
            "",
            object_repr="(cleared)",
            reason="Studio operator preview context cleared",
            sensitivity="LOW",
        )
    return redirect(next_url)


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
        from apps.platform_runtime.helpers import get_platform_site_settings_record
        from apps.siteconfig.forms import THEME_EXPERIENCE_FIELD_NAMES

        # Persist on the real platform singleton row — not get_effective_site_settings() (shallow resolver shell).
        site = get_platform_site_settings_record(create=False)
        if site is None:
            if _wants_json():
                return JsonResponse(
                    {
                        "ok": False,
                        "errors": [
                            "Unable to resolve the tenant site settings row for rollback."
                        ],
                    },
                    status=400,
                )
            return redirect(reverse("studio_os:experience"))

        allowed = frozenset(THEME_EXPERIENCE_FIELD_NAMES)
        field_updates = {
            str(k): v
            for k, v in values.items()
            if isinstance(k, str) and k.strip() and k in allowed
        }
        if not field_updates:
            if _wants_json():
                return JsonResponse(
                    {
                        "ok": False,
                        "errors": ["No recognized theme fields in rollback state."],
                    },
                    status=400,
                )
            return redirect(reverse("studio_os:experience"))

        # Phase B: colors and other virtual theme keys live in RuntimeDefaults.payload — mirror ThemeColorsForm.save().
        if callable(getattr(site, "apply_theme_experience_state", None)):
            site.apply_theme_experience_state(
                field_updates=field_updates,
                save=True,
            )
        elif callable(getattr(site, "apply_feature_control_state", None)):
            site.apply_feature_control_state(field_updates=field_updates)
        else:
            raise RuntimeError(
                "Tenant site settings row does not expose a Phase B write contract (apply_theme_experience_state/apply_feature_control_state)."
            )

        theme_fields = sorted(field_updates.keys())

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


@never_cache
@require_http_methods(["GET"])
@login_required
def school_infrastructure_preview_api(request):
    """
    GET ?template=private_school — JSON preview: resolved packs, diff rows, dependency hints.
    Read-only; no tenant mutation.
    """
    if not user_can_access_studio_on_request(request):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    school = getattr(request, "school", None)
    template_key = (request.GET.get("template") or "").strip()
    if not template_key:
        return JsonResponse({"ok": False, "error": "template query required"}, status=400)
    try:
        from apps.studio_os.school_infrastructure import build_infrastructure_preview

        payload = build_infrastructure_preview(school, template_key)
        # Avoid sending full policy blobs in JSON API
        tpl = dict(payload.get("template") or {})
        tpl.pop("notes", None)
        out = {k: v for k, v in payload.items() if k != "template"}
        out["template"] = tpl
        out["ok"] = payload.get("ok", False)
        return JsonResponse(out)
    except FileNotFoundError:
        return JsonResponse({"ok": False, "error": "unknown template"}, status=404)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as e:
        log_exception_with_context(
            "school_infrastructure_preview_api",
            **request_context_for_log(request),
            exc_info=True,
            extra={"error": str(e)},
        )
        return JsonResponse({"ok": False, "error": "preview failed"}, status=500)


@never_cache
@require_http_methods(["GET", "POST"])
@login_required
def school_infrastructure_validate_api(request):
    """
    Validate template against catalog (GET ?template= or POST template=).
    Returns errors list when unresolved pack keys or catalog warnings exist.
    """
    if not user_can_access_studio_on_request(request):
        return JsonResponse({"ok": False, "errors": ["forbidden"]}, status=403)
    school = getattr(request, "school", None)
    if request.method == "POST":
        template_key = (request.POST.get("template") or "").strip()
    else:
        template_key = (request.GET.get("template") or "").strip()
    if not template_key:
        return JsonResponse({"ok": False, "errors": ["template required"]}, status=400)
    try:
        from apps.studio_os.school_infrastructure import build_infrastructure_preview

        payload = build_infrastructure_preview(school, template_key)
        errors: list[str] = []
        errors.extend(payload.get("catalog_warnings") or [])
        for u in payload.get("unresolved_pack_keys") or []:
            errors.append(f"unresolved {u}")
        return JsonResponse(
            {
                "ok": len(errors) == 0 and payload.get("ok"),
                "errors": errors,
                "unresolved_pack_keys": payload.get("unresolved_pack_keys") or [],
            }
        )
    except FileNotFoundError:
        return JsonResponse({"ok": False, "errors": ["unknown template"]}, status=404)


@never_cache
@require_http_methods(["POST"])
@login_required
def school_infrastructure_apply_api(request):
    """
    Tenant-safe apply is not supported from Studio; platform administrators govern pack promotion.
    Always returns supported=false (honest contract).
    """
    if not user_can_access_studio_on_request(request):
        return JsonResponse({"ok": False, "supported": False}, status=403)
    return JsonResponse(
        {
            "ok": False,
            "supported": False,
            "reason": "School infrastructure apply is platform-governed. Use blueprint requests or your platform administrator.",
        },
        status=501,
    )

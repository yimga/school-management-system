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
from .services import (
    get_studio_activity_feed,
    get_studio_compare_context,
    get_automation_dependency_graph,
    get_automation_workflow_health_summary,
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
    if not getattr(request.user, "is_staff", False):
        return JsonResponse({"recommendations": []})
    mode = (request.GET.get("mode") or "").strip().lower() or None
    recs = get_studio_recommendations(request, mode)
    return JsonResponse({"recommendations": recs})


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_control_impact(request):
    """§4.6 Control Studio optional: Diff / impact summary. Renders control mode impact_summary for embedding in rail."""
    if not getattr(request.user, "is_staff", False):
        return redirect(reverse("accounts:backend_dashboard"))
    preview_ctx = get_studio_preview_context("control", request)
    return render(
        request,
        "studio_os/control_impact.html",
        {
            "impact_summary": preview_ctx.get("impact_summary") or "",
            "dependency_warnings": preview_ctx.get("dependency_warnings") or [],
            "page_title": _("Diff / impact summary"),
            "page_subtitle": _("Review feature toggles and runtime state before publishing. Use Runtime inspector for impact and source tracing."),
            "action_url": reverse("studio_os:control"),
            "action_text": _("Back to Control"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_ai_cleanup(request):
    """§4.6 Control Studio optional: AI cleanup suggestions. Renders control-mode recommendations for embedding in rail."""
    if not getattr(request.user, "is_staff", False):
        return redirect(reverse("accounts:backend_dashboard"))
    recs = get_studio_recommendations(request, "control")
    return render(
        request,
        "studio_os/ai_cleanup.html",
        {
            "recommendations": recs,
            "page_title": _("AI cleanup suggestions"),
            "page_subtitle": _("Capabilities and audit log suggestions for feature state."),
            "action_url": reverse("studio_os:control"),
            "action_text": _("Back to Control"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_experience_recommendations(request):
    """§4.2 Experience Studio optional: AI recommendations. Renders experience-mode recommendations for embedding in rail."""
    if not getattr(request.user, "is_staff", False):
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
    if not getattr(request.user, "is_staff", False):
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
    if not getattr(request.user, "is_staff", False):
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
            "page_subtitle": _("Design tokens (CSS variables) drive theme and in-shell form; configure in Theme & colors."),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_experience_portal_shell_layouts(request):
    """§4.2 Experience Studio optional: Portal shell layouts. Explains portal shell structure (sidebar, header, content) and where to configure."""
    if not getattr(request.user, "is_staff", False):
        return redirect(reverse("accounts:backend_dashboard"))
    customizer_url = ""
    try:
        customizer_url = reverse("siteconfig:customizer") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/experience_portal_shell_layouts.html",
        {
            "customizer_url": customizer_url,
            "page_title": _("Portal shell layouts"),
            "page_subtitle": _("Portal shell structure (sidebar, header, content areas); configure in Customizer and School theme."),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_experience_dashboard_visual_packs(request):
    """§4.2 Experience Studio optional: Dashboard visual packs. Explains dashboard widgets, charts, layout presets; links to dashboard/customizer."""
    if not getattr(request.user, "is_staff", False):
        return redirect(reverse("accounts:backend_dashboard"))
    dashboard_url = ""
    try:
        dashboard_url = reverse("accounts:backend_dashboard") + "?embed=1"
    except NoReverseMatch:
        pass
    customizer_url = ""
    try:
        customizer_url = reverse("siteconfig:customizer") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/experience_dashboard_visual_packs.html",
        {
            "dashboard_url": dashboard_url,
            "customizer_url": customizer_url,
            "page_title": _("Dashboard visual packs"),
            "page_subtitle": _("Widgets, charts, and layout presets for role-based dashboards; configure in Backend dashboard and Customizer."),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_experience_school_website_blocks(request):
    """§4.2 Experience Studio optional: School website blocks. Explains landing page sections and school website content; links to marketing and Customizer."""
    if not getattr(request.user, "is_staff", False):
        return redirect(reverse("accounts:backend_dashboard"))
    marketing_url = ""
    try:
        marketing_url = reverse("marketing_landing") + "?embed=1"
    except NoReverseMatch:
        pass
    customizer_url = ""
    try:
        customizer_url = reverse("siteconfig:customizer") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/experience_school_website_blocks.html",
        {
            "marketing_url": marketing_url,
            "customizer_url": customizer_url,
            "page_title": _("School website blocks"),
            "page_subtitle": _("Landing page sections, hero, and content blocks for your school website; configure in Customizer and marketing pages."),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_experience_communication_style_packs(request):
    """§4.2 Experience Studio optional: Communication style packs. Explains tone, templates, and notification styles; links to Customizer and communication settings."""
    if not getattr(request.user, "is_staff", False):
        return redirect(reverse("accounts:backend_dashboard"))
    customizer_url = ""
    try:
        customizer_url = reverse("siteconfig:customizer") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/experience_communication_style_packs.html",
        {
            "customizer_url": customizer_url,
            "page_title": _("Communication style packs"),
            "page_subtitle": _("Tone, templates, and notification styles for parent and staff communications; configure in Customizer and communication settings."),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_experience_packs(request):
    """§4.2 Experience Studio optional: ExperiencePack. Explains packageable theme + layout + dashboard + communication; shows current pack and links to admin and Theme & colors."""
    if not getattr(request.user, "is_staff", False):
        return redirect(reverse("accounts:backend_dashboard"))
    school = getattr(request, "school", None)
    effective_pack = None
    pack_count = 0
    try:
        from apps.brand_experience.experience_packs import get_effective_experience_pack
        from apps.packages.models import ExperiencePack
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
    return render(
        request,
        "studio_os/experience_experience_packs.html",
        {
            "effective_pack": effective_pack,
            "pack_count": pack_count,
            "theme_colors_url": theme_colors_url,
            "admin_packs_url": admin_packs_url,
            "page_title": _("Experience packs"),
            "page_subtitle": _("Packageable theme, layout, dashboard visual, and communication style. Assign per school; compare and rollback from Experience Studio."),
            "action_url": reverse("studio_os:experience"),
            "action_text": _("Back to Experience"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_output_dependency_graph(request):
    """§4.4 Output Studio optional: Dependency graph. Shows report pack dependencies for embedding in Output rail."""
    if not getattr(request.user, "is_staff", False):
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
    if not getattr(request.user, "is_staff", False):
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
            "page_subtitle": _("Reports and documents inherit school and theme branding. Configure theme and colors to control outputs."),
            "action_url": reverse("studio_os:output"),
            "action_text": _("Back to Outputs"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_output_policy_registry(request):
    """§5.3 Report Library: Policy & registry compatibility. Explains how report packs align with policy registry and metadata lineage; links to Blueprints & policy and Lineage & registry."""
    if not getattr(request.user, "is_staff", False):
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
        report_library_url = reverse("siteconfig:report_library") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/output_policy_registry.html",
        {
            "page_title": _("Policy & registry"),
            "page_subtitle": _("Reports and report packs align with policy (blueprints, grading, terms) and metadata registry (lineage, fields). Use Report library to build; Control for policy and lineage."),
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
def studio_automation_conflict_detection(request):
    """§4.3 Automation Studio optional: Conflict detection. Explains workflow conflict detection and links to Workflow hub."""
    if not getattr(request.user, "is_staff", False):
        return redirect(reverse("accounts:backend_dashboard"))
    workflow_hub_url = ""
    try:
        workflow_hub_url = reverse("siteconfig:workflow_hub") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/automation_conflict_detection.html",
        {
            "workflow_hub_url": workflow_hub_url,
            "page_title": _("Conflict detection"),
            "page_subtitle": _("Detect and resolve conflicts before activating workflows."),
            "action_url": reverse("studio_os:automation"),
            "action_text": _("Back to Automation"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_automation_staged_activation(request):
    """§4.3 Automation Studio optional: Staged activation. Explains activating workflows in stages and links to Workflow hub."""
    if not getattr(request.user, "is_staff", False):
        return redirect(reverse("accounts:backend_dashboard"))
    workflow_hub_url = ""
    try:
        workflow_hub_url = reverse("siteconfig:workflow_hub") + "?embed=1"
    except NoReverseMatch:
        pass
    return render(
        request,
        "studio_os/automation_staged_activation.html",
        {
            "workflow_hub_url": workflow_hub_url,
            "page_title": _("Staged activation"),
            "page_subtitle": _("Activate workflows in stages; run simulations before going live."),
            "action_url": reverse("studio_os:automation"),
            "action_text": _("Back to Automation"),
        },
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_automation_replay_rollback(request):
    """§4.3 Automation Studio optional: Replay / rollback. Explains workflow replay and rollback; links to Workflow hub and unified rollback."""
    if not getattr(request.user, "is_staff", False):
        return redirect(reverse("accounts:backend_dashboard"))
    workflow_hub_url = ""
    rollback_url = ""
    try:
        workflow_hub_url = reverse("siteconfig:workflow_hub") + "?embed=1"
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
            "page_subtitle": _("Re-run workflow instances and roll back workflow or config changes."),
            "action_url": reverse("studio_os:automation"),
            "action_text": _("Back to Automation"),
        },
    )


def _automation_explainer_view(request, template_name: str, page_title: str, page_subtitle: str):
    """Shared helper for Automation Studio explainer pages (staff-only, workflow_hub_url, action back to automation)."""
    if not getattr(request.user, "is_staff", False):
        return redirect(reverse("accounts:backend_dashboard"))
    workflow_hub_url = ""
    try:
        workflow_hub_url = reverse("siteconfig:workflow_hub") + "?embed=1"
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
        _("Build workflows visually with drag-and-drop; connect steps and conditions. Manage flows from the Workflow hub."),
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
        _("Describe workflows in plain language; the system suggests or generates flow steps. Refine and activate from the Workflow hub."),
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
        _("Run workflow simulations before going live. Verify behavior and impact from the Workflow hub, then activate when ready."),
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def studio_automation_dependency_graph(request):
    """§4.3 Automation Studio optional: Dependency graph. Shows workflow packs and their templates for embedding in Automation rail."""
    if not getattr(request.user, "is_staff", False):
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
    if not getattr(request.user, "is_staff", False):
        return redirect(reverse("accounts:backend_dashboard"))
    from apps.studio_os.services import get_automation_workflow_health_summary
    summary = get_automation_workflow_health_summary()
    workflow_hub_url = ""
    try:
        workflow_hub_url = reverse("siteconfig:workflow_hub") + "?embed=1"
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
            "page_subtitle": _("Active workflow packs and templates; run simulations from Workflow hub."),
            "action_url": reverse("studio_os:automation"),
            "action_text": _("Back to Automation"),
        },
    )


STUDIO_MODES = [
    {"id": "experience", "label": "Experience", "description": "Shape branding, theme, and portals"},
    {"id": "automation", "label": "Automation", "description": "Workflows, approvals, and automation"},
    {"id": "output", "label": "Outputs", "description": "Reports, documents, and exports"},
    {"id": "launch", "label": "Launch", "description": "Setup and go live"},
    {"id": "control", "label": "Control", "description": "Capabilities, policies, and runtime"},
]


def _resolve_legacy_urls(request):
    """Links to current tools until each mode is fully in-shell. Reduces clicks by offering one entry."""
    legacy = {}
    try:
        legacy["customizer"] = reverse("siteconfig:customizer")
        legacy["theme_colors"] = reverse("siteconfig:theme_colors")
        legacy["feature_control"] = reverse("siteconfig:feature_control_panel")
        legacy["report_library"] = reverse("siteconfig:report_library")
        legacy["workflow_hub"] = reverse("siteconfig:workflow_hub")
        legacy["guided_onboarding"] = reverse("siteconfig:guided_onboarding")
        legacy["document_library"] = reverse("portal:document_library_manage")
        legacy["reportcard_builder"] = reverse("siteconfig:reportcard_builder")
        legacy["workflow_flow_gallery"] = reverse("siteconfig:workflow_flow_gallery")
        legacy["backend_dashboard"] = reverse("accounts:backend_dashboard")
    except NoReverseMatch:
        pass
    return legacy


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
    if not getattr(request.user, "is_staff", False):
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
            context["studio_version_history"] = get_studio_version_history(request, "experience", limit=5)
            context["studio_audit"] = get_studio_publish_audit(request, "experience", limit=8)
        except (NoReverseMatch, ImportError, AttributeError, TypeError, ValueError) as e:
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
        try:
            experience_rail.append({
                "label": "Theme & colors",
                "url": reverse("siteconfig:theme_colors") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            experience_rail.append({
                "label": "Customizer",
                "url": reverse("siteconfig:customizer") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            experience_rail.append({
                "label": "School theme",
                "url": reverse("siteconfig:school_theme_settings") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            experience_rail.append({
                "label": "Experience packs",
                "url": reverse("studio_os:experience_packs") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            experience_rail.append({
                "label": "Import from website",
                "url": reverse("siteconfig:brand_import_from_url") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            experience_rail.append({
                "label": "Compare",
                "url": reverse("studio_os:experience_compare") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            experience_rail.append({
                "label": "AI recommendations",
                "url": reverse("studio_os:experience_recommendations") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            experience_rail.append({
                "label": "Theme tokens",
                "url": reverse("studio_os:experience_theme_tokens") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            experience_rail.append({
                "label": "Portal shell layouts",
                "url": reverse("studio_os:experience_portal_shell_layouts") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            experience_rail.append({
                "label": "Dashboard visual packs",
                "url": reverse("studio_os:experience_dashboard_visual_packs") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            experience_rail.append({
                "label": "School website blocks",
                "url": reverse("studio_os:experience_school_website_blocks") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            experience_rail.append({
                "label": "Communication style packs",
                "url": reverse("studio_os:experience_communication_style_packs") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        context["experience_left_rail"] = experience_rail

    if mode == "launch" and school:
        try:
            from apps.setup_studio.services import get_setup_studio_payload
            payload = get_setup_studio_payload(school)
            context["launch_payload"] = payload
            context["launch_role_previews"] = payload.get("role_previews") or []
            context["launch_health_summary"] = payload.get("health_summary") or ""
            context["launch_ready"] = payload.get("launch_ready", False)
        except (NoReverseMatch, ImportError, AttributeError, TypeError, ValueError) as e:
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
        try:
            launch_rail.append({
                "label": "Guided onboarding",
                "url": reverse("siteconfig:guided_onboarding") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            launch_rail.append({
                "label": "Create school",
                "url": reverse("super:create_school_wizard"),
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            launch_rail.append({
                "label": "Blueprint gallery",
                "url": reverse("siteconfig:get_blueprints") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            launch_rail.append({
                "label": "Import branding",
                "url": reverse("studio_os:experience") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            launch_rail.append({
                "label": "Launch checklist",
                "url": reverse("siteconfig:guided_onboarding") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        context["launch_left_rail"] = launch_rail

    if mode == "automation":
        workflow_entries = []
        automation_rail = []
        try:
            workflow_entries.append({"label": "Outcomes", "url": reverse("automation:outcomes_console") + "?embed=1"})
            workflow_entries.append({"label": "Workflow hub", "url": reverse("siteconfig:workflow_hub") + "?embed=1"})
            workflow_entries.append({"label": "Flow gallery", "url": reverse("siteconfig:workflow_flow_gallery")})
            workflow_entries.append({"label": "Approval hub", "url": reverse("accounts:approval_workflow_hub")})
            workflow_entries.append({
                "label": "Dependency graph",
                "url": reverse("studio_os:automation_dependency_graph") + "?embed=1",
            })
            workflow_entries.append({
                "label": "Workflow health metrics",
                "url": reverse("studio_os:automation_workflow_health") + "?embed=1",
            })
            workflow_entries.append({
                "label": "Conflict detection",
                "url": reverse("studio_os:automation_conflict_detection") + "?embed=1",
            })
            workflow_entries.append({
                "label": "Staged activation",
                "url": reverse("studio_os:automation_staged_activation") + "?embed=1",
            })
            workflow_entries.append({
                "label": "Replay / rollback",
                "url": reverse("studio_os:automation_replay_rollback") + "?embed=1",
            })
            workflow_entries.append({
                "label": "Visual builder",
                "url": reverse("studio_os:automation_visual_builder") + "?embed=1",
            })
            workflow_entries.append({
                "label": "Natural-language workflow",
                "url": reverse("studio_os:automation_natural_language_workflow") + "?embed=1",
            })
            workflow_entries.append({
                "label": "Simulation engine",
                "url": reverse("studio_os:automation_simulation_engine") + "?embed=1",
            })
            for entry in workflow_entries:
                automation_rail.append({"label": entry["label"], "url": entry["url"], "embed": True})
        except NoReverseMatch:
            pass
        context["workflow_entries"] = workflow_entries
        context["automation_left_rail"] = automation_rail
        context["automation_simulation_summary"] = (
            "Run simulation from Workflow hub to see impact before activating."
        )

    if mode == "output":
        output_rail = []
        try:
            output_rail.append({
                "label": "Report library",
                "url": reverse("siteconfig:report_library") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            output_rail.append({
                "label": "Document library",
                "url": reverse("portal:document_library_manage") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            output_rail.append({
                "label": "Report card builder",
                "url": reverse("siteconfig:reportcard_builder") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            output_rail.append({
                "label": "Dependency graph",
                "url": reverse("studio_os:output_dependency_graph") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            output_rail.append({
                "label": "Branding inheritance",
                "url": reverse("studio_os:output_branding_inheritance") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            output_rail.append({
                "label": "Policy & registry",
                "url": reverse("studio_os:output_policy_registry") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        context["output_left_rail"] = output_rail

    if mode == "control":
        try:
            from apps.siteconfig.views_feature_control import get_feature_control_audit_entries
            context["control_audit_entries"] = get_feature_control_audit_entries(request, limit=15)
        except (NoReverseMatch, ImportError, AttributeError, TypeError, ValueError) as e:
            if not isinstance(e, NoReverseMatch):
                log_exception_with_context(
                    "studio_shell control mode: get_feature_control_audit_entries failed",
                    **request_context_for_log(request),
                    extra={"mode": "control"},
                )
            context["control_audit_entries"] = []
        control_rail = []
        try:
            control_rail.append({
                "label": "Capabilities",
                "url": reverse("siteconfig:feature_control_panel") + "?embed=1",
                "embed": True,
            })
            control_rail.append({
                "label": "Audit log",
                "url": reverse("siteconfig:feature_control_audit"),
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            control_rail.append({
                "label": "Runtime inspector",
                "url": reverse("super:runtime_inspector"),
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            control_rail.append({
                "label": "Metadata governance",
                "url": reverse("metadata:metadata_governance"),
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            control_rail.append({
                "label": "Lineage & registry",
                "url": reverse("metadata:metadata_lineage_graph") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            control_rail.append({
                "label": "Integrations",
                "url": reverse("apicenter:dashboard"),
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            control_rail.append({
                "label": "Blueprints & policy packs",
                "url": reverse("siteconfig:get_blueprints") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            control_rail.append({
                "label": "Plans & entitlements",
                "url": reverse("super:billing_dashboard") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            control_rail.append({
                "label": "Diff / impact summary",
                "url": reverse("studio_os:control_impact") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        try:
            control_rail.append({
                "label": "AI cleanup suggestions",
                "url": reverse("studio_os:ai_cleanup") + "?embed=1",
                "embed": True,
            })
        except NoReverseMatch:
            pass
        context["control_left_rail"] = control_rail
        # In-shell control panel (no iframe) when user has permission
        if request.user.has_perm("settings.feature_control"):
            try:
                from django.template.loader import render_to_string
                from apps.siteconfig.views_feature_control import get_feature_control_panel_context
                ctrl_ctx = get_feature_control_panel_context(request)
                ctrl_ctx["control_next_url"] = reverse("studio_os:control")
                context["control_panel_html"] = render_to_string(
                    "siteconfig/feature_control_panel_partial.html",
                    ctrl_ctx,
                    request=request,
                )
                context["embed_url"] = None  # prefer in-page over iframe
            except (NoReverseMatch, ImportError, AttributeError, TypeError, ValueError) as e:
                if not isinstance(e, NoReverseMatch):
                    log_exception_with_context(
                        "studio_shell control mode: feature_control_panel render failed",
                        **request_context_for_log(request),
                        extra={"mode": "control"},
                    )
                context["control_panel_html"] = None
        else:
            context["control_panel_html"] = None

    show_bottom_bar = bool(mode == "experience" and context.get("use_experience_in_page"))
    bottom_bar_actions = []
    if show_bottom_bar:
        bottom_bar_actions = [
            {"id": "preview", "label": "Preview", "primary": False},
            {"id": "publish", "label": "Publish", "primary": True},
        ]
        if rollback_available:
            bottom_bar_actions.append({"id": "rollback", "label": "Rollback", "primary": False})
            try:
                context["studio_rollback_url"] = reverse("studio_os:rollback") + "?mode=" + mode
            except NoReverseMatch:
                context["studio_rollback_url"] = ""

    context["studio_show_bottom_bar"] = show_bottom_bar
    context["studio_bottom_bar_actions"] = bottom_bar_actions

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

    if not getattr(request.user, "is_staff", False):
        return redirect(reverse("accounts:backend_dashboard"))
    mode = (request.GET.get("mode") or request.POST.get("mode") or "").strip().lower()
    if mode == "experience":
        if request.method != "POST":
            if _wants_json():
                return JsonResponse({"ok": False, "errors": ["POST required"]}, status=405)
            return redirect(reverse("studio_os:experience"))

        prev = request.session.get("theme_previous_state")
        values = None
        if isinstance(prev, dict) and isinstance(prev.get("values"), dict):
            values = prev.get("values")
        elif isinstance(prev, dict):
            values = prev

        if not isinstance(values, dict) or not values:
            if _wants_json():
                return JsonResponse({"ok": False, "errors": ["No rollback state available."]}, status=400)
            return redirect(reverse("studio_os:experience"))

        from django.utils import timezone
        from apps.platform_runtime.helpers import get_effective_site_settings

        site = get_effective_site_settings(request=request)
        if site is None:
            if _wants_json():
                return JsonResponse({"ok": False, "errors": ["Unable to resolve SiteSettings for rollback."]}, status=400)
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

        theme_fields = list(dict.fromkeys([f for f in updated_fields if isinstance(f, str) and f.strip()]))
        save_fields = list(theme_fields)
        if hasattr(site, "updated_at"):
            save_fields.append("updated_at")
        if save_fields:
            site.save(update_fields=save_fields)

        actor_label = request.user.get_username() if request.user.is_authenticated else "system"
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

            messages.success(request, "Rolled back theme & experience to the previous saved state.")
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
    if not getattr(request.user, "is_staff", False):
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
                payload["dependency_warnings"] = preview_ctx.get("dependency_warnings", [])
                if preview_ctx.get("health_summary"):
                    payload["health_summary"] = preview_ctx["health_summary"]
                if preview_ctx.get("recommended_next"):
                    payload["recommended_next"] = preview_ctx["recommended_next"]
            return JsonResponse(payload)
        return JsonResponse({"errors": ["Preview URL not available for this mode."]}, status=400)
    return JsonResponse({"errors": ["Missing or invalid mode."]}, status=400)


@never_cache
@require_http_methods(["POST"])
@login_required
def studio_publish_api(request):
    """
    Shared publish: validate and persist. Experience uses perform_theme_experience_publish;
    other modes use services.studio_publish. Returns JSON {ok, redirect_url} or {ok: false, errors}.
    """
    if not getattr(request.user, "is_staff", False):
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
    if not getattr(request.user, "is_staff", False):
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
    if not getattr(request.user, "is_staff", False):
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
    if not getattr(request.user, "is_staff", False):
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
    if not getattr(request.user, "is_staff", False):
        return JsonResponse({"audit": []})
    mode = (request.GET.get("mode") or "").strip().lower() or None
    try:
        limit = min(50, max(1, int(request.GET.get("limit", 20))))
    except (TypeError, ValueError):
        limit = 20
    audit = get_studio_publish_audit(request, mode, limit=limit)
    return JsonResponse({"audit": audit})

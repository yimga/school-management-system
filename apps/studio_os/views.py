# -*- coding: utf-8 -*-
"""
Studio OS — single shell with five work modes.
Replaces fragmented customizer / theme / feature control / report library / workflow hub with one workspace.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .services import (
    get_studio_activity_feed,
    get_studio_recommendations,
    get_studio_command_palette_entries,
    studio_rollback_available,
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
    except Exception:
        pass
    return legacy


def _resolve_embed_urls(request):
    """URLs to embed in the Studio canvas per mode (Phase 2–4: in-shell iframe). Use ?embed=1 so embedded page does not redirect back to Studio."""
    urls = {}
    try:
        urls["experience"] = reverse("siteconfig:theme_colors") + "?embed=1"
        urls["automation"] = reverse("siteconfig:workflow_hub") + "?embed=1"
        urls["output"] = reverse("siteconfig:report_library") + "?embed=1"
        urls["launch"] = reverse("siteconfig:guided_onboarding") + "?embed=1"
        urls["control"] = reverse("siteconfig:feature_control_panel") + "?embed=1"
    except Exception:
        pass
    return urls


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

    show_bottom_bar = bool(mode)
    bottom_bar_actions = []
    if mode:
        bottom_bar_actions = [
            {"id": "preview", "label": "Preview", "primary": False},
            {"id": "publish", "label": "Publish", "primary": True},
        ]
        if rollback_available:
            bottom_bar_actions.append({"id": "rollback", "label": "Rollback", "primary": False})

    try:
        preview_from_form_url = reverse("siteconfig:preview_from_form")
    except Exception:
        preview_from_form_url = ""

    context = {
        "studio_modes": STUDIO_MODES,
        "current_mode": mode,
        "legacy_urls": legacy_urls,
        "embed_url": embed_url,
        "school": getattr(request, "school", None),
        "studio_activity_feed": activity_feed,
        "studio_recommendations": recommendations,
        "studio_command_palette_entries": command_palette_entries,
        "studio_show_bottom_bar": show_bottom_bar,
        "studio_bottom_bar_actions": bottom_bar_actions,
        "studio_rollback_available": rollback_available,
        "studio_preview_from_form_url": preview_from_form_url,
    }

    school = getattr(request, "school", None)
    if mode == "experience":
        try:
            from apps.siteconfig.views import get_theme_colors_context
            context.update(get_theme_colors_context(request))
            context["use_experience_in_page"] = True
            context["back_url"] = reverse("studio_os:experience")
        except Exception:
            context["use_experience_in_page"] = False

    if mode == "launch" and school:
        try:
            from apps.setup_studio.services import get_setup_studio_payload
            context["launch_payload"] = get_setup_studio_payload(school)
        except Exception:
            context["launch_payload"] = None
    elif mode == "launch":
        context["launch_payload"] = None

    if mode == "automation":
        workflow_entries = []
        try:
            workflow_entries.append({"label": "Workflow hub", "url": reverse("siteconfig:workflow_hub") + "?embed=1"})
            workflow_entries.append({"label": "Flow gallery", "url": reverse("siteconfig:workflow_flow_gallery")})
            workflow_entries.append({"label": "Approval hub", "url": reverse("accounts:approval_workflow_hub")})
        except Exception:
            pass
        context["workflow_entries"] = workflow_entries

    if mode == "control":
        try:
            from apps.siteconfig.views_feature_control import get_feature_control_audit_entries
            context["control_audit_entries"] = get_feature_control_audit_entries(request, limit=15)
        except Exception:
            context["control_audit_entries"] = []
        control_rail = []
        try:
            control_rail.append({"label": "Capabilities", "url": reverse("siteconfig:feature_control_panel") + "?embed=1"})
            control_rail.append({"label": "Audit log", "url": reverse("siteconfig:feature_control_audit")})
        except Exception:
            pass
        context["control_left_rail"] = control_rail

    if mode and rollback_available:
        try:
            context["studio_rollback_url"] = reverse("studio_os:rollback") + "?mode=" + mode
        except Exception:
            context["studio_rollback_url"] = ""
    else:
        context["studio_rollback_url"] = ""

    template = f"studio_os/modes/{mode}.html" if mode else "studio_os/shell.html"
    return render(request, template, context)


@never_cache
@require_http_methods(["GET", "POST"])
@login_required
def studio_rollback(request):
    """
    Perform rollback for current mode and redirect back to Studio.
    Experience: clear theme preview/recent change session; Control: redirect to feature control with embed (user clicks Revert there).
    """
    if not getattr(request.user, "is_staff", False):
        return redirect(reverse("accounts:backend_dashboard"))
    mode = (request.GET.get("mode") or request.POST.get("mode") or "").strip().lower()
    if mode == "experience":
        request.session.pop("theme_recent_change_meta", None)
        request.session.pop("site_preview_settings", None)
        request.session.pop("preview_mode_enabled", None)
        request.session.modified = True
        return redirect(reverse("studio_os:experience"))
    if mode == "control":
        return redirect(reverse("siteconfig:feature_control_panel") + "?embed=1")
    return redirect(reverse("studio_os:shell"))

# -*- coding: utf-8 -*-
"""
Dashboard Configuration Hub (Part 2b): list templates, assign by role.
Phase 4: Workflow hub and Dashboard hub — single tenant-facing entry points; all composition via resolvers.
§2.4 Broad except: workflow_hub/get_blueprints use NoReverseMatch and _OPTIONAL_HUB_ERRORS for optional imports/query.
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from django.db import DatabaseError
from django.utils.translation import gettext as _

from apps.siteconfig.control_plane_render import (
    default_operator_breadcrumbs,
    operator_cp_breadcrumb,
    render_siteconfig_operator_page,
    render_siteconfig_stem,
)
from apps.siteconfig.operator_school import redirect_missing_operator_school
from apps.siteconfig.models_dashboard import DashboardTemplate, TenantLayoutAssignment
from apps.siteconfig.models_workflow import WorkflowTemplate, TenantWorkflow
from apps.siteconfig.tenant_experience_policy import user_may_manage_backend_config

logger = logging.getLogger(__name__)

# §2.4 Typed exceptions for optional hub URLs/imports (reverse, BlueprintPack, build_manager_absolute_url); allowlist 0.
_OPTIONAL_HUB_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    DatabaseError,
)


def _preview_label(value: str) -> str:
    return str(value or "").replace("_", " ").replace("-", " ").title()


def _template_preview_payload(template, *, chrome_label: str = "") -> dict:
    schema = getattr(template, "config_schema", None) or {}
    if not isinstance(schema, dict):
        schema = {}
    modules = schema.get("modules") if isinstance(schema.get("modules"), dict) else {}
    sections = schema.get("sections") if isinstance(schema.get("sections"), dict) else {}
    theme = schema.get("theme") if isinstance(schema.get("theme"), dict) else {}
    role_home = schema.get("role_home") if isinstance(schema.get("role_home"), dict) else {}
    pack = getattr(template, "dashboard_pack", None)
    visible_modules = [
        _preview_label(key) for key, enabled in modules.items() if bool(enabled)
    ]
    hidden_modules = [
        _preview_label(key) for key, enabled in modules.items() if not bool(enabled)
    ]
    hidden_sections = [
        _preview_label(key) for key, enabled in sections.items() if not bool(enabled)
    ]
    kpis = [
        _preview_label(key)
        for key in schema.get("kpis", [])
        if str(key or "").strip()
    ]
    focus_areas = [
        str(item)
        for item in role_home.get("focus_areas", [])
        if str(item or "").strip()
    ]
    return {
        "id": str(template.pk),
        "name": template.name,
        "description": template.description or "",
        "pack": getattr(pack, "name", "") or "",
        "pack_code": getattr(pack, "code", "") or schema.get("source_pack", "") or "",
        "family": getattr(pack, "family", "") or "",
        "chrome": chrome_label,
        "eyebrow": role_home.get("eyebrow", "") or template.name,
        "purpose": role_home.get("purpose", "") or template.description or "",
        "focus_areas": focus_areas,
        "kpis": kpis,
        "visible_modules": visible_modules,
        "hidden_modules": hidden_modules,
        "hidden_sections": hidden_sections,
        "theme": theme.get("visual_preset", "") or "",
    }


def _fallback_preview_payload(role_label: str) -> dict:
    return {
        "id": "",
        "name": _("Platform default"),
        "description": _(
            "No role-specific template is assigned yet. Runtime falls back to the built-in role home."
        ),
        "pack": "",
        "pack_code": "",
        "family": "",
        "chrome": "theme_pack_default",
        "eyebrow": role_label,
        "purpose": _("Built-in role home until a dashboard template is assigned."),
        "focus_areas": [],
        "kpis": [],
        "visible_modules": [],
        "hidden_modules": [],
        "hidden_sections": [],
        "theme": "",
    }


@never_cache
@require_http_methods(["GET"])
@login_required
def dashboard_hub(request):
    """
    Phase 4: Dashboard hub — single tenant-facing entry. Dashboards are composed by role via
    dashboard_resolver.for_role(school, role). This page links to configuration (assign template per role).
    """
    if not user_may_manage_backend_config(request.user):
        messages.warning(request, "Access restricted to school administrators.")
        return redirect(reverse("accounts:backend_dashboard"))
    school = getattr(request, "school", None)
    if not school:
        return redirect_missing_operator_school(
            request,
            detail=_(
                "No school context. Switch to a school to manage dashboards."
            ),
        )
    config_url = reverse("siteconfig:dashboard_configuration_hub")
    backend_url = reverse("accounts:backend_dashboard")
    assignment_count = TenantLayoutAssignment.objects.filter(school=school).count()
    ctx = {
        "school": school,
        "config_url": config_url,
        "backend_url": backend_url,
        "assignment_count": assignment_count,
        "page_title": _("Configuration Center"),
        "page_subtitle": _(
            "Role dashboards and layout defaults for %(school_name)s — assign templates so each role lands on the right widgets."
        )
        % {"school_name": school.name},
        "action_url": backend_url,
        "action_text": _("Back to backend"),
    }
    return render_siteconfig_operator_page(
        request,
        portal_template="siteconfig/dashboard_hub.html",
        body_template="siteconfig/partials/dashboard_hub_body.html",
        context=ctx,
        cp_title=_("Dashboard hub"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("Dashboard hub"), active=True),
        ),
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def get_blueprints(request):
    """
    Tenant-facing "Get blueprints" entry (11.2). Blueprint packs are applied by platform admin;
    this page lets tenants discover available packs and request application (or link to manager).
    """
    if not user_may_manage_backend_config(request.user):
        messages.warning(request, "Access restricted to school administrators.")
        return redirect(reverse("accounts:backend_dashboard"))
    school = getattr(request, "school", None)
    if not school:
        return redirect_missing_operator_school(request)
    packs = []
    applied_pack = None
    pack_update_available = False
    try:
        from apps.policies.models import BlueprintPack, TenantBlueprint

        packs = list(
            BlueprintPack.objects.filter(is_active=True).order_by("category", "name")[
                :50
            ]
        )
        tb = (
            TenantBlueprint.objects.filter(school=school)
            .select_related("applied_pack")
            .first()
        )
        applied_pack = tb.applied_pack if tb else None
        if applied_pack:
            pack_update_available = (
                applied_pack.schools_with_outdated_bundle()
                .filter(pk=school.pk)
                .exists()
            )
    except _OPTIONAL_HUB_ERRORS as e:
        logger.debug("get_blueprints optional packs/query: %s", e)
    try:
        from apps.schools.tenant_url import build_manager_absolute_url

        manager_blueprints_url = build_manager_absolute_url(
            request, "/super/marketplace/blueprints/"
        )
    except _OPTIONAL_HUB_ERRORS as e:
        logger.debug("get_blueprints optional manager_blueprints_url: %s", e)
        manager_blueprints_url = None
    platform_catalog_preview = None
    try:
        from apps.studio_os.school_infrastructure import catalog_pack_rows_for_blueprints_page

        platform_catalog_preview = catalog_pack_rows_for_blueprints_page(limit=24)
    except _OPTIONAL_HUB_ERRORS as e:
        logger.debug("get_blueprints optional platform_catalog_preview: %s", e)
        platform_catalog_preview = None
    # §2e row 8 page maturity: page_header + data-page-archetype (CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL §5.1)
    if request.GET.get("embed"):
        try:
            action_url = reverse("studio_os:control")
            action_text = _("Back to Control")
        except NoReverseMatch:
            action_url = reverse("siteconfig:dashboard_hub")
            action_text = _("Back to dashboard")
    else:
        action_url = reverse("siteconfig:dashboard_hub")
        action_text = _("Back to dashboard")
    return render_siteconfig_operator_page(
        request,
        portal_template="siteconfig/get_blueprints.html",
        body_template="siteconfig/partials/get_blueprints_body.html",
        context={
            "school": school,
            "packs": packs,
            "applied_pack": applied_pack,
            "pack_update_available": pack_update_available,
            "manager_blueprints_url": manager_blueprints_url,
            "platform_catalog_preview": platform_catalog_preview,
            "page_title": _("Blueprints"),
            "page_subtitle": _(
                "Policy blueprint packs for %(school)s. Packs are applied by your platform administrator."
            )
            % {"school": school.name},
            "action_url": action_url,
            "action_text": action_text,
        },
        cp_title=_("Blueprints & policy packs"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("Blueprints & policy packs"), active=True),
        ),
    )


@never_cache
@require_http_methods(["GET", "POST"])
@login_required
def dashboard_configuration_hub(request):
    """
    Configuration Hub: list DashboardTemplates and assign template per role for current school.
    """
    if not user_may_manage_backend_config(request.user):
        messages.warning(request, "Access restricted to school administrators.")
        return redirect(reverse("accounts:backend_dashboard"))
    school = getattr(request, "school", None)
    if not school:
        return redirect_missing_operator_school(
            request,
            detail=_(
                "No school context. Switch to a school to manage dashboard layouts."
            ),
        )

    templates = list(
        DashboardTemplate.objects.filter(is_active=True)
        .select_related("dashboard_pack")
        .order_by("name")
    )
    assignments = {
        a.role: a
        for a in TenantLayoutAssignment.objects.filter(school=school).select_related(
            "template", "template__dashboard_pack"
        )
    }

    if request.method == "POST":
        role = (request.POST.get("role") or "").strip().upper()
        template_id = request.POST.get("template_id")
        if role in dict(TenantLayoutAssignment.ROLE_CHOICES) and template_id:
            try:
                template = DashboardTemplate.objects.get(
                    pk=int(template_id), is_active=True
                )
            except (ValueError, DashboardTemplate.DoesNotExist):
                messages.error(request, "Invalid template.")
            else:
                obj, created = TenantLayoutAssignment.objects.update_or_create(
                    school=school,
                    role=role,
                    defaults={"template": template, "is_active": True},
                )
                messages.success(
                    request,
                    "Assignment updated: %s → %s." % (role, template.name),
                )
                return redirect(reverse("siteconfig:dashboard_configuration_hub"))
        else:
            messages.error(request, "Select a role and a template.")

    role_choices = TenantLayoutAssignment.ROLE_CHOICES
    from apps.siteconfig.portal_chrome import describe_portal_chrome_override
    from apps.platform_runtime.live_preview import get_preview_url

    # List of (role_value, role_label, assignment or None, chrome_label) for table
    assignment_rows = []
    role_preview_profiles = {}
    for role_val, role_label in role_choices:
        assignment = assignments.get(role_val)
        template = assignment.template if assignment else None
        chrome_label = describe_portal_chrome_override(template)
        assignment_rows.append(
            (
                role_val,
                role_label,
                assignment,
                chrome_label,
            )
        )
        current_profile = (
            _template_preview_payload(template, chrome_label=chrome_label)
            if template
            else _fallback_preview_payload(role_label)
        )
        role_preview_profiles[role_val] = {
            "role": role_val,
            "label": role_label,
            "current": current_profile,
            "preview_urls": {
                device: get_preview_url(
                    role=role_val,
                    device=device,
                    tenant_id=getattr(school, "pk", None),
                    path="/",
                )
                for device in ("desktop", "tablet", "mobile")
            },
        }
    template_preview_profiles = {
        str(template.pk): _template_preview_payload(
            template,
            chrome_label=describe_portal_chrome_override(template),
        )
        for template in templates
    }
    dashboard_hub_url = reverse("siteconfig:dashboard_hub")
    # §2e row 8 page maturity: studio_os page_header + data-page-archetype (CONTROL_PLANE §5.1)
    return render_siteconfig_stem(
        request,
        "dashboard_configuration_hub",
        {
            "templates": templates,
            "assignments": assignments,
            "assignment_rows": assignment_rows,
            "role_choices": role_choices,
            "role_preview_profiles": role_preview_profiles,
            "template_preview_profiles": template_preview_profiles,
            "school": school,
            "page_title": _("Configuration Center — dashboards by role"),
            "page_subtitle": _(
                "Map each role to a dashboard template for %(school_name)s. Unassigned roles fall back to platform defaults until you complete setup."
            )
            % {"school_name": school.name},
            "action_url": dashboard_hub_url,
            "action_text": _("Back to Configuration Center home"),
        },
        cp_title=_("Dashboard configuration"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("Dashboard hub"), url=dashboard_hub_url),
            operator_cp_breadcrumb(_("Dashboard configuration"), active=True),
        ),
    )


@never_cache
@require_http_methods(["GET", "POST"])
@login_required
def workflow_flow_gallery(request):
    """
    Flow Gallery (Part 2c): list WorkflowTemplates and TenantWorkflow assignments.
    Phase 4: POST to activate, deactivate, or rollback (clear overrides) within guardrails.
    """
    if not user_may_manage_backend_config(request.user):
        messages.warning(request, "Access restricted to school administrators.")
        return redirect(reverse("accounts:backend_dashboard"))
    school = getattr(request, "school", None)
    if not school:
        return redirect_missing_operator_school(request)

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        template_id = request.POST.get("template_id")
        if action and template_id:
            try:
                template = WorkflowTemplate.objects.get(
                    pk=int(template_id), is_active=True
                )
            except (ValueError, WorkflowTemplate.DoesNotExist):
                messages.error(request, "Invalid template.")
            else:
                tw, created = TenantWorkflow.objects.get_or_create(
                    school=school,
                    template=template,
                    defaults={"is_active": False, "overrides": {}},
                )
                if action == "activate":
                    tw.is_active = True
                    tw.save(update_fields=["is_active", "updated_at"])
                    messages.success(request, f"Activated: {template.name}.")
                elif action == "deactivate":
                    tw.is_active = False
                    tw.save(update_fields=["is_active", "updated_at"])
                    messages.success(request, f"Deactivated: {template.name}.")
                elif action == "rollback":
                    tw.overrides = {}
                    tw.save(update_fields=["overrides", "updated_at"])
                    messages.success(
                        request, f"Rolled back overrides for: {template.name}."
                    )
                else:
                    messages.error(request, "Unknown action.")
                return redirect(reverse("siteconfig:workflow_flow_gallery"))

    templates = list(WorkflowTemplate.objects.filter(is_active=True).order_by("code"))
    assignments_by_tpl = {
        a.template_id: a
        for a in TenantWorkflow.objects.filter(school=school).select_related("template")
    }
    template_rows = [(t, assignments_by_tpl.get(t.id)) for t in templates]

    # §2e row 8 page maturity: page_header + data-page-archetype (CONTROL_PLANE §5.1)
    if request.GET.get("embed"):
        try:
            action_url = reverse("studio_os:automation")
            action_text = _("Back to Automation")
        except NoReverseMatch:
            action_url = reverse("studio_os:automation")
            action_text = _("Back to Workflow hub")
    else:
        action_url = reverse("studio_os:automation")
        action_text = _("Back to Workflow hub")

    return render_siteconfig_operator_page(
        request,
        portal_template="siteconfig/workflow_flow_gallery.html",
        body_template="siteconfig/partials/workflow_flow_gallery_body.html",
        context={
            "templates": templates,
            "template_rows": template_rows,
            "school": school,
            "page_title": _("Workflow Flow Gallery"),
            "page_subtitle": _(
                "Pre-built workflows and assignments for %(school)s. Activate, deactivate, or rollback within guardrails."
            )
            % {"school": school.name},
            "action_url": action_url,
            "action_text": action_text,
        },
        cp_title=_("Workflow flow gallery"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("Workflow flow gallery"), active=True),
        ),
    )

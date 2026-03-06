# -*- coding: utf-8 -*-
"""
Dashboard Configuration Hub (Part 2b): list templates, assign by role.
Phase 4: Workflow hub and Dashboard hub — single tenant-facing entry points; all composition via resolvers.
"""
import logging

from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache

from apps.siteconfig.models_dashboard import DashboardTemplate, TenantLayoutAssignment
from apps.siteconfig.models_workflow import WorkflowTemplate, TenantWorkflow

logger = logging.getLogger(__name__)


@never_cache
@require_http_methods(["GET"])
@login_required
def dashboard_hub(request):
    """
    Phase 4: Dashboard hub — single tenant-facing entry. Dashboards are composed by role via
    dashboard_resolver.for_role(school, role). This page links to configuration (assign template per role).
    """
    if not getattr(request.user, "is_staff", False):
        messages.warning(request, "Access restricted to staff.")
        return redirect(reverse("accounts:backend_dashboard"))
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "No school context. Switch to a school to manage dashboards.")
        return redirect(reverse("accounts:backend_dashboard"))
    config_url = reverse("siteconfig:dashboard_configuration_hub")
    return render(
        request,
        "siteconfig/dashboard_hub.html",
        {"school": school, "config_url": config_url},
    )


@never_cache
@require_http_methods(["GET"])
@login_required
def workflow_hub(request):
    """
    Phase 4: Workflow hub — single tenant-facing entry. Browse approval workflows and
    workflow templates; customize within guardrails; rollback via flow gallery.
    """
    if not getattr(request.user, "is_staff", False):
        messages.warning(request, "Access restricted to staff.")
        return redirect(reverse("accounts:backend_dashboard"))
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "No school context.")
        return redirect(reverse("accounts:backend_dashboard"))
    approval_hub_url = reverse("accounts:approval_workflow_hub")
    flow_gallery_url = reverse("siteconfig:workflow_flow_gallery")
    return render(
        request,
        "siteconfig/workflow_hub.html",
        {
            "school": school,
            "approval_hub_url": approval_hub_url,
            "flow_gallery_url": flow_gallery_url,
        },
    )


@never_cache
@require_http_methods(["GET", "POST"])
@login_required
def dashboard_configuration_hub(request):
    """
    Configuration Hub: list DashboardTemplates and assign template per role for current school.
    """
    if not getattr(request.user, "is_staff", False):
        messages.warning(request, "Access restricted to staff.")
        return redirect(reverse("accounts:backend_dashboard"))
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "No school context. Switch to a school to manage dashboard layouts.")
        return redirect(reverse("accounts:backend_dashboard"))

    templates = list(DashboardTemplate.objects.filter(is_active=True).order_by("name"))
    assignments = {a.role: a for a in TenantLayoutAssignment.objects.filter(school=school).select_related("template")}

    if request.method == "POST":
        role = (request.POST.get("role") or "").strip().upper()
        template_id = request.POST.get("template_id")
        if role in dict(TenantLayoutAssignment.ROLE_CHOICES) and template_id:
            try:
                template = DashboardTemplate.objects.get(pk=int(template_id), is_active=True)
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
    # List of (role_value, role_label, assignment or None) for table
    assignment_rows = [
        (role_val, role_label, assignments.get(role_val))
        for role_val, role_label in role_choices
    ]
    return render(
        request,
        "siteconfig/dashboard_configuration_hub.html",
        {
            "templates": templates,
            "assignments": assignments,
            "assignment_rows": assignment_rows,
            "role_choices": role_choices,
            "school": school,
        },
    )


@never_cache
@require_http_methods(["GET", "POST"])
@login_required
def workflow_flow_gallery(request):
    """
    Flow Gallery (Part 2c): list WorkflowTemplates and TenantWorkflow assignments.
    Phase 4: POST to activate, deactivate, or rollback (clear overrides) within guardrails.
    """
    if not getattr(request.user, "is_staff", False):
        messages.warning(request, "Access restricted to staff.")
        return redirect(reverse("accounts:backend_dashboard"))
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "No school context.")
        return redirect(reverse("accounts:backend_dashboard"))

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        template_id = request.POST.get("template_id")
        if action and template_id:
            try:
                template = WorkflowTemplate.objects.get(pk=int(template_id), is_active=True)
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
                    messages.success(request, f"Rolled back overrides for: {template.name}.")
                else:
                    messages.error(request, "Unknown action.")
                return redirect(reverse("siteconfig:workflow_flow_gallery"))

    templates = list(WorkflowTemplate.objects.filter(is_active=True).order_by("code"))
    assignments_by_tpl = {
        a.template_id: a
        for a in TenantWorkflow.objects.filter(school=school).select_related("template")
    }
    template_rows = [(t, assignments_by_tpl.get(t.id)) for t in templates]

    return render(
        request,
        "siteconfig/workflow_flow_gallery.html",
        {
            "templates": templates,
            "template_rows": template_rows,
            "school": school,
        },
    )

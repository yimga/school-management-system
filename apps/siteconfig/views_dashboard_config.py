# -*- coding: utf-8 -*-
"""
Dashboard Configuration Hub (Part 2b): list templates, assign by role.
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
@require_http_methods(["GET"])
@login_required
def workflow_flow_gallery(request):
    """
    Flow Gallery (Part 2c): list WorkflowTemplates and TenantWorkflow assignments for current school.
    """
    if not getattr(request.user, "is_staff", False):
        messages.warning(request, "Access restricted to staff.")
        return redirect(reverse("accounts:backend_dashboard"))
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "No school context.")
        return redirect(reverse("accounts:backend_dashboard"))

    templates = list(WorkflowTemplate.objects.filter(is_active=True).order_by("code"))
    assignments = list(TenantWorkflow.objects.filter(school=school, is_active=True).select_related("template"))

    return render(
        request,
        "siteconfig/workflow_flow_gallery.html",
        {
            "templates": templates,
            "assignments": assignments,
            "school": school,
        },
    )

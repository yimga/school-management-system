# -*- coding: utf-8 -*-
"""School group / multi-campus hierarchy (read-only, tenant-scoped)."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import permission_required
from apps.platform_runtime.customer_health import calculate_school_health
from apps.schools.group_analytics import build_group_intelligence_context
from apps.schools.hierarchy_helpers import (
    get_group_school_summary,
    get_school_ancestors,
    get_school_tree,
    get_school_descendants,
)


@login_required
@permission_required("settings.manage", raise_exception=True)
@require_http_methods(["GET"])
def school_group_hierarchy(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseForbidden("No school context.")

    ancestors = get_school_ancestors(school)
    parent = school.parent_school
    child_schools = list(school.get_child_schools())
    tree = get_school_tree(school)
    descendant_count = get_school_descendants(school, include_self=False).count()

    summary = get_group_school_summary(school, request.user)
    school_health = calculate_school_health(school)

    admin_school_url = None
    if getattr(request.user, "is_superuser", False):
        try:
            admin_school_url = reverse("admin:schools_school_change", args=[school.pk])
        except NoReverseMatch:
            # Test / edge URLConf: still surface a canonical platform admin path.
            admin_school_url = f"/admin/schools/school/{school.pk}/change/"

    try:
        tenant_runtime_url = reverse("siteconfig:tenant_runtime_configuration_hub")
    except NoReverseMatch:
        tenant_runtime_url = None
    try:
        onboarding_url = reverse("siteconfig:onboarding")
    except NoReverseMatch:
        onboarding_url = None
    try:
        console_url = reverse("siteconfig:console_domains_hub")
    except NoReverseMatch:
        console_url = None
    try:
        security_surface_url = reverse("super:security_surface_dashboard")
    except NoReverseMatch:
        security_surface_url = None

    scope_label = "group" if parent or child_schools else "single-tenant"
    group_intel = build_group_intelligence_context(school, request.user)

    return render(
        request,
        "siteconfig/school_group_hierarchy.html",
        {
            "page_title": "School group hierarchy",
            "school": school,
            "parent_school": parent,
            "ancestors": ancestors,
            "child_schools": child_schools,
            "tree": tree,
            "descendant_count": descendant_count,
            "group_summary": summary,
            "school_health": school_health,
            "scope_label": scope_label,
            "tenant_runtime_url": tenant_runtime_url,
            "onboarding_url": onboarding_url,
            "console_url": console_url,
            "admin_school_url": admin_school_url,
            "group_intelligence": group_intel,
            "security_surface_url": security_surface_url,
        },
    )

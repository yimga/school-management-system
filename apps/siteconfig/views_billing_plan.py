"""
Read-only tenant billing / plan summary (GTM). No payment capture or Stripe.
Shows the school's assigned Plan row plus live headcount vs plan limits when available.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import permission_required
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.tenant_url import build_manager_absolute_url


def _plan_catalog_advanced_url(request: HttpRequest) -> str | None:
    """
    Break-glass plan catalog: Django admin changelist when registered; otherwise
    control-plane plans list (Plan CRUD is not on tenant/platform admin).
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_superuser", False):
        return None
    try:
        return reverse("admin:siteconfig_plan_changelist")
    except NoReverseMatch:
        pass
    try:
        rel = reverse("super:plans_list", urlconf="config.manager_urls")
    except NoReverseMatch:
        return None
    return build_manager_absolute_url(request, path=rel)


@login_required
@permission_required("settings.manage")
@require_http_methods(["GET"])
def billing_plan_readonly(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)
    plan = getattr(school, "plan", None) if school is not None else None
    addons: list = []
    if school is not None:
        addons = list(getattr(school, "addons", None) or [])

    student_count = 0
    teacher_count = 0
    if school is not None:
        student_count = StudentProfile.objects.filter(
            school=school, is_active=True
        ).count()
        teacher_count = TeacherProfile.objects.filter(school=school).count()

    plan_catalog_advanced_url = _plan_catalog_advanced_url(request)

    console_url = None
    try:
        console_url = reverse("siteconfig:console_domains_hub")
    except NoReverseMatch:
        pass

    return render(
        request,
        "siteconfig/billing_plan_readonly.html",
        {
            "school": school,
            "plan": plan,
            "addons": addons,
            "student_count": student_count,
            "teacher_count": teacher_count,
            "plan_catalog_advanced_url": plan_catalog_advanced_url,
            "console_url": console_url,
        },
    )

"""Tenant operator read-only view for DB grading scales and bands (North Star SLICE 2)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse


@login_required
def grading_scale_bands_operator_view(request):
    """Show effective grading scale + bands for the current tenant (school context required)."""
    from django.http import HttpResponseForbidden

    from apps.accounts.models import User
    from apps.policies.policy_registry import get_effective_policy

    school = getattr(request, "school", None)
    if not school:
        messages.warning(
            request,
            "Open this page from your school subdomain to view grading scale bands.",
        )
        return redirect("siteconfig:user_preferences")

    role = (getattr(request.user, "role", "") or "").upper()
    allowed_role = role in (
        User.Role.ADMIN,
        User.Role.LEADERSHIP,
        User.Role.IT_ADMIN,
        User.Role.PRINCIPAL,
        User.Role.VICE_PRINCIPAL,
    )
    if not allowed_role and not (
        getattr(request.user, "is_staff", False)
        or getattr(request.user, "is_superuser", False)
    ):
        return HttpResponseForbidden(
            "You do not have permission to view grading scale configuration."
        )

    from apps.evals.grading_scale_service import (
        get_effective_grading_scale_for_school,
        get_scale_bands_ordered,
    )
    from apps.siteconfig.tenant_config import get_grading_schema_for_school

    effective = get_effective_grading_scale_for_school(school)
    bands = get_scale_bands_ordered(effective)
    schema = get_grading_schema_for_school(school)
    policy = get_effective_policy(school)
    locale_scale = (schema.get("scale") or "") or (
        (policy.get("grading") or {}).get("grading_scale") or ""
    )

    admin_url = None
    if getattr(request.user, "is_superuser", False):
        try:
            if effective is not None:
                admin_url = reverse(
                    "admin:evals_gradingscale_change", args=[effective.pk]
                )
            else:
                admin_url = reverse("admin:evals_gradingscale_changelist")
        except NoReverseMatch:
            admin_url = None

    region = getattr(school, "default_region", None)

    return render(
        request,
        "siteconfig/grading_scale_bands.html",
        {
            "school": school,
            "region": region,
            "effective_scale": effective,
            "bands": bands,
            "locale_rosetta_scale": locale_scale,
            "cp_region_grading_url": reverse("siteconfig:region_grading_scales"),
            "grading_settings_url": reverse("siteconfig:grading_settings"),
            "admin_advanced_grading_url": admin_url,
            "runtime_hub_url": reverse("siteconfig:tenant_runtime_configuration_hub"),
        },
    )


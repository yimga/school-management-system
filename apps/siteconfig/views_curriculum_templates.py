"""North Star SLICE 3 — curriculum template registry (operator preview; apply is out of scope)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse


@login_required
def curriculum_templates_operator_view(request):
    """Named curriculum templates (reference catalog) for the current school context."""
    from django.http import HttpResponseForbidden

    from apps.accounts.models import User

    school = getattr(request, "school", None)
    if not school:
        messages.warning(
            request,
            "Open this page from your school subdomain to view curriculum templates.",
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
            "You do not have permission to view curriculum templates."
        )

    from apps.siteconfig.curriculum_templates_service import iter_curriculum_templates
    from apps.siteconfig.terminology_service import (
        describe_terminology_resolution,
        get_effective_terminology_for_school,
    )

    templates_list = list(iter_curriculum_templates())

    settings_dict = school.settings if isinstance(school.settings, dict) else {}
    template_key = (settings_dict.get("curriculum_template_key") or "").strip()
    eff = get_effective_terminology_for_school(school)
    resolution = describe_terminology_resolution(school)
    highlight_fr = template_key == "francophone_bac"

    admin_catalog_url = None
    if getattr(request.user, "is_superuser", False):
        try:
            admin_catalog_url = reverse(
                "admin:global_registries_educationsystemprofile_changelist"
            )
        except NoReverseMatch:
            admin_catalog_url = None

    return render(
        request,
        "siteconfig/curriculum_templates.html",
        {
            "school": school,
            "templates_list": templates_list,
            "grading_scale_bands_url": reverse("siteconfig:grading_scale_bands"),
            "region_grading_scales_url": reverse("siteconfig:region_grading_scales"),
            "grading_settings_url": reverse("siteconfig:grading_settings"),
            "runtime_hub_url": reverse("siteconfig:tenant_runtime_configuration_hub"),
            "console_domains_url": reverse("siteconfig:console_domains_hub"),
            "preview_only": True,
            "admin_education_profiles_url": admin_catalog_url,
            "effective_terminology": eff,
            "terminology_resolution": resolution,
            "terminology_highlight_francophone": highlight_fr,
        },
    )

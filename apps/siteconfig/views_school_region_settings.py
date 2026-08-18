"""Tenant self-service **School & Region settings** editor.

One tenant-admin surface to edit the school's core registry-backed configuration —
country, subdivision, timezone, currency, language, calendar, institution type,
education-system sector + types, language sub-system, and grading scale. These are
exactly the fields the Setup/Launch "Registry alignment" table checks.

Before this page, only grading + language (``grading_settings``) and currency
(``currency_settings``) had a tenant editor; institution type, education-system
sector/types, language sub-system, timezone, calendar and subdivision were set only
at create-time or by an operator — so a tenant could never resolve those alignment
rows themselves. That was the gap behind "how does a tenant edit the Education
system?".

Writes land where the alignment snapshot AND the rest of the platform read them:
model fields on ``School`` (country_code / subdivision / timezone / currency /
school_type / primary_sector / sub_system / education_system_types) and tenant
``settings`` keys via ``apply_tenant_settings_overrides`` (default_language /
calendar_system / default_currency / grading_scale). Only registry-valid codes are
accepted; anything else is ignored. Same admin gate as the sibling config editors.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

_SOFT = (AttributeError, TypeError, ValueError, DatabaseError, ImportError)


def _choices(qs, *, code_attr: str = "code", name_attr: str = "name") -> list[tuple[str, str]]:
    """(code, label) pairs from a registry queryset — code-only fallback for label."""
    out: list[tuple[str, str]] = []
    try:
        for row in qs:
            code = str(getattr(row, code_attr, "") or "").strip()
            if not code:
                continue
            label = str(getattr(row, name_attr, "") or "").strip() or code
            out.append((code, label))
    except _SOFT:
        return []
    return out


@login_required
def school_region_settings(request):
    school = getattr(request, "school", None)
    if not school:
        messages.warning(
            request,
            _("Select a school (use your school subdomain) to manage its settings."),
        )
        return redirect("siteconfig:user_preferences")

    from apps.siteconfig.tenant_experience_policy import (
        user_may_manage_backend_config,
    )

    if not user_may_manage_backend_config(request.user):
        # PermissionDenied routes through the branded handler403 (errors/403.html)
        # rather than a bare text response.
        raise PermissionDenied(
            str(_("You do not have permission to change school & region settings."))
        )

    from apps.registries.models import (
        CalendarSystemRegistry,
        CountryRegistry,
        CurrencyRegistry,
        EducationSystemTypeRegistry,
        InstitutionTypeRegistry,
        LocaleRegistry,
        SubdivisionRegistry,
        TimeZoneRegistry,
    )
    from apps.siteconfig.tenant_config import apply_tenant_settings_overrides

    cc = str(getattr(school, "country_code", "") or "").strip().upper()

    # ---- choice sets (registry-backed; degrade to empty on any registry error) --
    country_choices = _choices(
        CountryRegistry.objects.filter(is_active=True).order_by("name")
    )
    subdivision_choices = _choices(
        SubdivisionRegistry.objects.filter(
            country__code=cc, is_active=True
        ).order_by("name")
    )
    timezone_choices = _choices(
        TimeZoneRegistry.objects.filter(is_active=True).order_by("code")
    )
    currency_choices = _choices(
        CurrencyRegistry.objects.filter(is_active=True).order_by("code")
    )
    language_choices = _choices(
        LocaleRegistry.objects.filter(is_active=True).order_by("name")
    )
    calendar_choices = _choices(
        CalendarSystemRegistry.objects.filter(is_active=True).order_by("name")
    )
    institution_choices = _choices(
        InstitutionTypeRegistry.objects.filter(is_active=True).order_by(
            "sort_order", "name"
        )
    )
    sector_choices = _choices(
        EducationSystemTypeRegistry.objects.filter(
            category="sector", is_active=True
        ).order_by("sort_order", "name")
    )
    education_type_choices = _choices(
        EducationSystemTypeRegistry.objects.filter(is_active=True).order_by(
            "sort_order", "name"
        )
    )
    try:
        from apps.siteconfig.views import get_grading_scale_choices_for_school

        grading_choices = list(get_grading_scale_choices_for_school(school) or [])
    except _SOFT:
        grading_choices = []
    try:
        sub_system_choices = list(school.__class__.SubSystem.choices)
    except _SOFT:
        sub_system_choices = [("EN", "English sub-system"), ("FR", "French sub-system")]

    if request.method == "POST":
        model_updates: dict[str, object] = {}
        settings_updates: dict[str, object] = {}

        def _valid(name: str, choices: list[tuple[str, str]]) -> str | None:
            raw = str(request.POST.get(name, "") or "").strip()
            allowed = {c for c, _label in choices}
            return raw if raw and raw in allowed else None

        # --- School model fields -------------------------------------------------
        v = _valid("country_code", country_choices)
        if v:
            model_updates["country_code"] = v[:2].upper()
        v = _valid("timezone", timezone_choices)
        if v:
            model_updates["timezone"] = v
        v = _valid("currency", currency_choices)
        if v:
            model_updates["currency"] = v
            # Mirror to the settings key the alignment snapshot + resolver read.
            settings_updates["default_currency"] = v
        v = _valid("school_type", institution_choices)
        if v:
            model_updates["school_type"] = v
        v = _valid("primary_sector", sector_choices)
        if v:
            model_updates["primary_sector"] = v
        v = _valid("sub_system", sub_system_choices)
        if v:
            model_updates["sub_system"] = v

        # Subdivision is a FK resolved by (country, code).
        sub_raw = str(request.POST.get("subdivision", "") or "").strip()
        if sub_raw and sub_raw in {c for c, _l in subdivision_choices}:
            try:
                sub_obj = SubdivisionRegistry.objects.filter(
                    country__code=cc, code=sub_raw, is_active=True
                ).first()
                if sub_obj is not None:
                    school.subdivision = sub_obj
                    model_updates["subdivision"] = sub_obj
            except _SOFT:
                pass

        # --- tenant settings keys (policy-enforced writer) -----------------------
        v = _valid("default_language", language_choices)
        if v:
            settings_updates["default_language"] = v
        v = _valid("calendar_system", calendar_choices)
        if v:
            settings_updates["calendar_system"] = v
        v = _valid("grading_scale", grading_choices)
        if v:
            settings_updates["grading_scale"] = v

        # --- persist model fields ------------------------------------------------
        if model_updates:
            for field, value in model_updates.items():
                setattr(school, field, value)
            try:
                school.save(update_fields=[*model_updates.keys(), "updated_at"])
            except _SOFT:
                school.save()

        # --- persist education-system types (M2M) --------------------------------
        type_codes = [
            c
            for c in request.POST.getlist("education_system_types")
            if c and c in {code for code, _l in education_type_choices}
        ]
        if "education_system_types" in request.POST:
            try:
                objs = list(
                    EducationSystemTypeRegistry.objects.filter(
                        code__in=type_codes, is_active=True
                    )
                )
                school.education_system_types.set(objs)
            except _SOFT:
                pass

        # --- persist settings via the policy-aware writer ------------------------
        blocked_keys: list[str] = []
        if settings_updates:
            try:
                result = apply_tenant_settings_overrides(
                    school,
                    settings_updates,
                    actor_is_superadmin=bool(request.user.is_superuser),
                    force_override=False,
                    persist=True,
                )
                blocked_keys = sorted((result.get("blocked") or {}).keys())
            except _SOFT:
                blocked_keys = []

        if model_updates or settings_updates or ("education_system_types" in request.POST):
            messages.success(request, _("School & region settings updated."))
        if blocked_keys:
            messages.warning(
                request,
                _("Some settings are managed by policy and were not changed: %(keys)s")
                % {"keys": ", ".join(blocked_keys)},
            )
        return redirect("siteconfig:school_region_settings")

    # ---- GET: current values -------------------------------------------------
    settings = school.settings if isinstance(getattr(school, "settings", None), dict) else {}
    current_subdivision = ""
    try:
        current_subdivision = str(getattr(school.subdivision, "code", "") or "")
    except _SOFT:
        current_subdivision = ""
    try:
        current_types = set(
            school.education_system_types.values_list("code", flat=True)
        )
    except _SOFT:
        current_types = set()

    context = {
        "school": school,
        "action_url": reverse("siteconfig:user_preferences"),
        "action_text": _("Back to preferences"),
        "fields": [
            {
                "name": "country_code",
                "label": _("Country"),
                "choices": country_choices,
                "current": cc,
                "help": _("Your school's country. Drives regional defaults."),
            },
            {
                "name": "subdivision",
                "label": _("Region / subdivision"),
                "choices": subdivision_choices,
                "current": current_subdivision,
                "help": _("State, region, or province within your country."),
            },
            {
                "name": "timezone",
                "label": _("Time zone"),
                "choices": timezone_choices,
                "current": str(getattr(school, "timezone", "") or ""),
                "help": _("Used for schedules, attendance, and timestamps."),
            },
            {
                "name": "currency",
                "label": _("Currency"),
                "choices": currency_choices,
                "current": str(
                    settings.get("default_currency")
                    or getattr(school, "currency", "")
                    or ""
                ),
                "help": _("The currency for fees, invoices, and statements."),
            },
            {
                "name": "default_language",
                "label": _("Language"),
                "choices": language_choices,
                "current": str(settings.get("default_language") or ""),
                "help": _("Default interface language for this school."),
            },
            {
                "name": "calendar_system",
                "label": _("Calendar system"),
                "choices": calendar_choices,
                "current": str(settings.get("calendar_system") or ""),
                "help": _("Calendar used for terms, holidays, and reports."),
            },
            {
                "name": "school_type",
                "label": _("Institution type"),
                "choices": institution_choices,
                "current": str(getattr(school, "school_type", "") or ""),
                "help": _("The kind of institution (school, college, academy…)."),
            },
            {
                "name": "primary_sector",
                "label": _("Education system"),
                "choices": sector_choices,
                "current": str(getattr(school, "primary_sector", "") or ""),
                "help": _(
                    "Your school's sector — Public, Private, International, and so on."
                ),
            },
            {
                "name": "sub_system",
                "label": _("Language sub-system"),
                "choices": sub_system_choices,
                "current": str(getattr(school, "sub_system", "") or ""),
                "help": _(
                    "For bilingual countries: the anglophone / francophone sub-system."
                ),
            },
            {
                "name": "grading_scale",
                "label": _("Grading scale"),
                "choices": grading_choices,
                "current": str(settings.get("grading_scale") or ""),
                "help": _("The grading scale used on report cards and evaluations."),
            },
        ],
        "education_type_choices": education_type_choices,
        "current_education_types": current_types,
    }
    return render(request, "siteconfig/school_region_settings.html", context)

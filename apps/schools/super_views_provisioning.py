"""
School create API and provisioning entry (split from super_views for BR-12).
"""

from __future__ import annotations

import os

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_PROVISION,
    require_platform_scope,
)

logger = logging.getLogger(__name__)

from apps.registries.models import EducationLevelRegistry, EducationSystemTypeRegistry
from apps.registries.services import (
    ensure_registry_baseline,
    get_sector_role_suggestions,
    WEDGE_14_22_SECTOR_CODES,
)
from apps.siteconfig.education_profile_engine import list_template_catalog
from apps.siteconfig.global_catalog import GlobalGeoCatalog
from apps.siteconfig.tenant_config import apply_tenant_settings_overrides
from apps.global_registries.models import EducationSystemProfile
from apps.schools.super_views_helpers import (
    canonical_country_alpha2,
    ensure_region_for_country,
    resolve_registry_codes,
    resolve_subdivision,
    safe_school_timeline_url,
    safe_tenant_360_url,
    slug_from_school_name,
)
from apps.platform_runtime.workflow_tracker import pulse_workflow_step, track_workflow, workflow_step

from .models import School, SchoolProvisioningEvent
from .super_views_constants import CONTROL_PLANE_AUDIT_FAILURES


@require_POST
@require_platform_scope(PLATFORM_SCOPE_PROVISION)
@track_workflow(
    "tenant_school_create",
    steps=("validate", "create_row", "enqueue_provision"),
    expected_duration_seconds=45,
    email_on_failure=True,
)
def api_create_school(request):
    """
    Validate payload, create School row (is_active=False), enqueue provisioning task.
    Returns 202 + job_id or 400 with errors.
    """
    import json

    logo_file = None
    favicon_file = None
    content_type = (request.content_type or "").lower()
    try:
        if "multipart/form-data" in content_type:
            raw_payload = (request.POST.get("payload") or "").strip()
            if not raw_payload:
                return JsonResponse({"error": "Missing payload"}, status=400)
            data = json.loads(raw_payload)
            logo_file = request.FILES.get("logo")
            favicon_file = request.FILES.get("favicon")
        else:
            data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    ensure_registry_baseline()
    name = (data.get("name") or "").strip()
    slug = (data.get("slug") or "").strip().lower().replace(" ", "-")
    if not slug and name:
        slug = slug_from_school_name(name)
    subdomain = (data.get("subdomain") or slug or "").strip().lower()
    contact_email = (data.get("contact_email") or "").strip()
    region_code = GlobalGeoCatalog.normalize_country_code(
        (data.get("region_code") or "").strip()
    )
    raw_country_code = (data.get("country_code") or region_code or "").strip()
    country_code = GlobalGeoCatalog.normalize_country_code(raw_country_code)
    canonical_country_code = canonical_country_alpha2(raw_country_code or country_code)
    city_id = (data.get("city_id") or "").strip()
    sub_system = (data.get("sub_system") or School.SubSystem.EN).strip().upper()
    valid_subsystems = {School.SubSystem.EN, School.SubSystem.FR, School.SubSystem.INT}
    if sub_system not in valid_subsystems:
        sub_system = School.SubSystem.EN
    education_profile_code = (data.get("education_profile_code") or "").strip()
    education_system_ids = data.get("education_system_ids")
    if not isinstance(education_system_ids, list):
        education_system_ids = []
    education_system_ids = [str(x).strip() for x in education_system_ids if x]
    education_level_codes = data.get("education_level_codes")
    if not isinstance(education_level_codes, list):
        education_level_codes = []
    education_level_codes = [str(x).strip().upper() for x in education_level_codes if x]
    education_system_type_codes = data.get("education_system_type_codes")
    if not isinstance(education_system_type_codes, list):
        education_system_type_codes = []
    education_system_type_codes = [
        str(x).strip().upper() for x in education_system_type_codes if x
    ]
    subdivision_id = data.get("subdivision_id")
    province_id = data.get("province_id")
    if province_id is not None and province_id != "":
        try:
            province_id = int(province_id)
        except (TypeError, ValueError):
            province_id = None
    primary_color = (data.get("primary_color") or "#0d6efd").strip()
    accent_color = (data.get("accent_color") or "#198754").strip()
    theme_choice = (data.get("theme_choice") or "UNFOLD").strip().upper()
    if theme_choice not in {"UNFOLD", "JAZZMIN", "SNEAT"}:
        theme_choice = "UNFOLD"
    custom_domain = (data.get("custom_domain") or "").strip()
    plan_id = data.get("plan_id")
    if plan_id is not None and plan_id != "":
        try:
            plan_id = int(plan_id)
        except (TypeError, ValueError):
            plan_id = None
    addons = data.get("addons")
    if not isinstance(addons, list):
        addons = []

    if not subdomain and slug:
        subdomain = slug
    errors = []
    if not name:
        errors.append("name is required")
    if not slug and name:
        slug = slug_from_school_name(name)
    if not slug:
        errors.append("slug could not be derived from name; provide slug or name")
    if not contact_email:
        errors.append("contact_email is required")
    if education_profile_code:
        _ep = EducationSystemProfile.objects.filter(
            code=education_profile_code.strip(), is_active=True
        ).first()
        if (
            _ep is not None
            and _ep.approval_status != EducationSystemProfile.ApprovalStatus.APPROVED
        ):
            errors.append(
                "education_profile_code must reference an approved profile (draft or inactive profiles are rejected)"
            )
    if not education_system_type_codes:
        _ps = (data.get("primary_sector") or "").strip().upper()
        if _ps and (
            _ps in WEDGE_14_22_SECTOR_CODES
            or EducationSystemTypeRegistry.objects.filter(
                code=_ps, is_active=True
            ).exists()
        ):
            education_system_type_codes = [_ps]
        else:
            education_system_type_codes = [
                "INTERNATIONAL" if sub_system == School.SubSystem.INT else "PRIVATE"
            ]
    parent_school_id = (data.get("parent_school_id") or "").strip()
    parent_school = None
    if parent_school_id:
        try:
            parent_school = School.objects.filter(
                pk=parent_school_id, is_active=True
            ).first()
            if not parent_school:
                errors.append("parent_school_id must be an active school")
            else:
                parent_school_id = str(parent_school.pk)
        except (TypeError, ValueError):
            parent_school_id = ""
            errors.append("parent_school_id must be a valid UUID")
    if errors:
        return JsonResponse({"errors": errors}, status=400)

    if School.objects.filter(slug=slug).exists():
        return JsonResponse({"errors": ["slug already exists"]}, status=400)
    if subdomain and School.objects.filter(subdomain=subdomain).exists():
        return JsonResponse({"errors": ["subdomain already exists"]}, status=400)

    STANDARD_TEMPLATE_CODES = {
        row["code"]
        for row in list_template_catalog(
            country_code=country_code, sub_system=sub_system
        )
    }
    explicit_profile = None
    if education_profile_code:
        explicit_profile = EducationSystemProfile.objects.filter(
            code=education_profile_code,
            is_active=True,
            approval_status=EducationSystemProfile.ApprovalStatus.APPROVED,
        ).first()
        if (
            explicit_profile is None
            and education_profile_code not in STANDARD_TEMPLATE_CODES
        ):
            errors.append("education_profile_code is invalid")
        elif explicit_profile is not None and explicit_profile.sub_system not in {
            EducationSystemProfile.SubSystem.ANY,
            sub_system,
        }:
            errors.append("education_profile_code does not match selected sub-system")
    if errors:
        return JsonResponse({"errors": errors}, status=400)

    from apps.global_registries.models import RegionConfig, WeatherLocation

    default_region = None
    selected_city = GlobalGeoCatalog.get_city(city_id, country_code=country_code)
    selected_location = None
    if city_id and selected_city is None:
        try:
            selected_location = (
                WeatherLocation.objects.select_related("region")
                .filter(pk=int(city_id), is_active=True)
                .first()
            )
        except (TypeError, ValueError):
            selected_location = None
    if (
        selected_location
        and country_code
        and selected_location.region_id != country_code
    ):
        selected_location = None
    if selected_city:
        country_code = selected_city["country_code"]
        canonical_country_code = canonical_country_alpha2(
            selected_city.get("country_code_alpha2") or country_code
        )
        default_region = ensure_region_for_country(
            country_code, selected_city.get("timezone") or "UTC"
        )
    elif selected_location:
        default_region = selected_location.region
        country_code = selected_location.region_id
        canonical_country_code = canonical_country_alpha2(country_code)
    if default_region is None and country_code:
        default_region = RegionConfig.objects.filter(
            code=country_code
        ).first() or ensure_region_for_country(country_code)
    if default_region is None and region_code:
        default_region = RegionConfig.objects.filter(
            code=region_code
        ).first() or ensure_region_for_country(region_code)
    if default_region is None and explicit_profile and explicit_profile.region_id:
        default_region = explicit_profile.region
        country_code = explicit_profile.region_id
        canonical_country_code = canonical_country_alpha2(country_code)
    if default_region is not None and not canonical_country_code:
        canonical_country_code = canonical_country_alpha2(default_region.code)
    resolved_timezone = (
        (selected_city.get("timezone") if selected_city else "")
        or (selected_location.timezone if selected_location else "")
        or (explicit_profile.default_timezone if explicit_profile else "")
        or (default_region.timezone if default_region else "")
        or "UTC"
    )
    resolved_subdivision = resolve_subdivision(
        canonical_country_code or country_code,
        subdivision_id=subdivision_id,
        province_id=province_id,
    )
    selected_levels = resolve_registry_codes(
        EducationLevelRegistry, education_level_codes
    )
    selected_system_types = resolve_registry_codes(
        EducationSystemTypeRegistry, education_system_type_codes
    )
    if education_level_codes and len({row.code for row in selected_levels}) != len(
        set(education_level_codes)
    ):
        errors.append("education_level_codes contains unknown values")
    if education_system_type_codes and len(
        {row.code for row in selected_system_types}
    ) != len(set(education_system_type_codes)):
        errors.append("education_system_type_codes contains unknown values")
    if subdivision_id not in (None, "") and resolved_subdivision is None:
        errors.append("subdivision_id is invalid")

    school_template_key = (data.get("school_template_key") or "").strip()
    seed_demo_personas = bool(data.get("seed_demo_personas"))
    if school_template_key:
        try:
            from apps.studio_os.school_infrastructure import list_school_template_keys

            if school_template_key not in list_school_template_keys():
                errors.append("school_template_key is not a known blueprint template")
        except (ImportError, OSError, ValueError, TypeError):
            errors.append("school_template_key validation unavailable")

    if errors:
        return JsonResponse({"errors": errors}, status=400)

    wf_run = getattr(request, "_rmc_workflow_run", None)
    pulse_workflow_step(wf_run, "validate", payload={"slug": slug, "name": name[:80]})

    location_payload = {
        "country_code": country_code or (default_region.code if default_region else ""),
        "country_code_alpha2": canonical_country_code or "",
        "subdivision_code": resolved_subdivision.code if resolved_subdivision else "",
        "subdivision_name": resolved_subdivision.name if resolved_subdivision else "",
        "city": "",
        "label": "",
        "timezone": resolved_timezone,
        "city_id": city_id or "",
    }
    if selected_city:
        location_payload.update(
            {
                "city": selected_city.get("city", ""),
                "label": selected_city.get("label", ""),
                "latitude": selected_city.get("latitude"),
                "longitude": selected_city.get("longitude"),
            }
        )
    elif selected_location:
        location_payload.update(
            {
                "city": selected_location.city,
                "label": selected_location.display_label,
                "latitude": float(selected_location.latitude),
                "longitude": float(selected_location.longitude),
            }
        )

    school_settings_overrides = {
        "contact_email": contact_email,
        "provisioning": {
            "logo_uploaded": False,
            "education_profile_mode": "explicit" if explicit_profile else "auto",
            "education_system_ids": education_system_ids,
            "education_level_codes": [row.code for row in selected_levels],
            "education_system_type_codes": [row.code for row in selected_system_types],
            "province_id": province_id,
            "subdivision_id": resolved_subdivision.id if resolved_subdivision else None,
            "school_template_key": school_template_key,
            "seed_demo_personas_requested": seed_demo_personas,
        },
        "education_profile_code": (
            explicit_profile.code if explicit_profile else education_profile_code or ""
        ),
        "location": location_payload,
        "custom_domain": {
            "hostname": custom_domain or "",
            "status": "pending_verification" if custom_domain else "not_configured",
            "verified": False,
        },
    }

    primary_sector = ""
    for code in education_system_type_codes:
        if code in WEDGE_14_22_SECTOR_CODES:
            primary_sector = code
            break
    _sug = get_sector_role_suggestions(primary_sector)
    school_settings_overrides["provisioning"]["sector_suggested_roles"] = list(
        _sug.get("suggested_roles") or []
    )
    school_settings_overrides["provisioning"]["sector_role_description"] = str(
        _sug.get("description") or ""
    )
    create_kw = dict(
        name=name,
        slug=slug,
        subdomain=subdomain or slug,
        sub_system=sub_system,
        default_region=default_region,
        country_code=canonical_country_code or "",
        subdivision=resolved_subdivision,
        timezone=resolved_timezone,
        primary_color=primary_color,
        accent_color=accent_color,
        custom_domain=custom_domain or "",
        is_active=False,
        is_approved=os.getenv("ENABLE_SCHOOL_APPROVAL_WORKFLOW", "").strip().lower() not in ("1", "true", "yes"),
        settings={},
        primary_sector=primary_sector,
    )
    if parent_school_id and parent_school:
        create_kw["parent_school_id"] = parent_school.pk
    if hasattr(School, "theme_choice"):
        create_kw["theme_choice"] = theme_choice
    if plan_id and hasattr(School, "plan_id"):
        from apps.plans_entitlements.models import Plan

        if Plan.objects.filter(pk=plan_id, is_active=True).exists():
            create_kw["plan_id"] = plan_id
    if addons and hasattr(School, "addons"):
        addons = [str(x).strip() for x in addons if x]
        create_kw["addons"] = addons
    from apps.schools.school_brand_assets import (
        ensure_brand_profile_colors,
        persist_school_brand_favicon,
        persist_school_brand_logo,
    )

    try:
        with workflow_step(wf_run, "create_row"):
            with transaction.atomic():
                school = School.objects.create(**create_kw)
                try:
                    from apps.lifecycle.unified_lifecycle import (
                        CREATION_PATH_OPERATOR,
                        set_creation_path,
                    )

                    set_creation_path(school, CREATION_PATH_OPERATOR, save=False)
                except (ImportError, ValueError, TypeError, OSError):
                    pass
                ensure_brand_profile_colors(
                    school=school,
                    primary_color=primary_color,
                    accent_color=accent_color,
                )
                if logo_file:
                    persist_school_brand_logo(school=school, uploaded_file=logo_file)
                    school_settings_overrides["provisioning"]["logo_uploaded"] = True
                if favicon_file:
                    persist_school_brand_favicon(school=school, uploaded_file=favicon_file)
                    school_settings_overrides["provisioning"]["favicon_uploaded"] = True
    except ValidationError as exc:
        logger.warning(
            "School provisioning rejected: brand asset validation failed (logo=%s, favicon=%s): %s",
            bool(logo_file),
            bool(favicon_file),
            exc,
        )
        return JsonResponse({"errors": [str(exc)]}, status=400)
    if selected_levels:
        school.education_levels.set(selected_levels)
    if selected_system_types:
        school.education_system_types.set(selected_system_types)
    try:
        from apps.schools.control_plane import log_control_plane_action
        from apps.compliance.models_audit import AuditLog

        log_control_plane_action(
            request,
            AuditLog.Action.CREATE,
            "School",
            str(school.id),
            object_repr=school.name or str(school.id),
            reason="School created via super create-school API",
            sensitivity=AuditLog.Sensitivity.HIGH,
            new_values={
                "name": school.name,
                "slug": school.slug,
                "subdomain": school.subdomain,
            },
        )
    except CONTROL_PLANE_AUDIT_FAILURES:
        pass
    try:
        from apps.billing.services import ensure_subscription_for_school

        ensure_subscription_for_school(school)
    except CONTROL_PLANE_AUDIT_FAILURES:
        pass
    apply_tenant_settings_overrides(
        school=school,
        overrides=school_settings_overrides,
        actor_is_superadmin=bool(getattr(request.user, "is_superuser", False)),
        force_override=False,
        persist=True,
    )
    SchoolProvisioningEvent.log_event(
        school=school,
        event_type=SchoolProvisioningEvent.EventType.REQUEST_RECEIVED,
        status=SchoolProvisioningEvent.Status.INFO,
        message="Provisioning request accepted.",
        payload={
            "country_code": country_code
            or (default_region.code if default_region else ""),
            "sub_system": sub_system,
            "education_profile_code": (
                explicit_profile.code
                if explicit_profile
                else education_profile_code or ""
            ),
            "custom_domain": custom_domain or "",
        },
        created_by=request.user
        if getattr(request, "user", None) and request.user.is_authenticated
        else None,
    )
    if custom_domain:
        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.DOMAIN_PENDING,
            status=SchoolProvisioningEvent.Status.INFO,
            message=f"Custom domain {custom_domain} pending DNS verification.",
            payload={"hostname": custom_domain},
            created_by=request.user
            if getattr(request, "user", None) and request.user.is_authenticated
            else None,
        )

    from apps.schools.tasks import complete_provisioning_for_school

    with workflow_step(wf_run, "enqueue_provision", payload={"school_id": str(school.id)}):
        dispatch = complete_provisioning_for_school(
            str(school.id),
            contact_email=contact_email,
            seed_demo_personas=seed_demo_personas,
        )
    school.refresh_from_db(fields=["is_active"])
    job_id = dispatch.get("job_id")
    payload = {"job_id": job_id or "", "is_active": bool(getattr(school, "is_active", False))}
    if dispatch.get("fallback") and dispatch.get("reason"):
        payload["fallback_reason"] = dispatch["reason"]
    if dispatch.get("sync_completed"):
        payload["sync_completed"] = True
    SchoolProvisioningEvent.log_event(
        school=school,
        event_type=(
            SchoolProvisioningEvent.EventType.COMPLETED
            if getattr(school, "is_active", False)
            else SchoolProvisioningEvent.EventType.QUEUED
        ),
        status=(
            SchoolProvisioningEvent.Status.WARNING
            if dispatch.get("fallback") and not getattr(school, "is_active", False)
            else SchoolProvisioningEvent.Status.INFO
        ),
        message=(
            "Provisioning completed."
            if getattr(school, "is_active", False)
            else (dispatch.get("message") or "Provisioning queued.")
        ),
        payload=payload,
        created_by=request.user
        if getattr(request, "user", None) and request.user.is_authenticated
        else None,
    )

    from apps.schools.tenant_url import build_manager_absolute_url, tenant_absolute_url

    tenant_360_path = safe_tenant_360_url(school.id)
    tenant_360_url = (
        build_manager_absolute_url(request, tenant_360_path) if tenant_360_path else ""
    )
    theme_hub_url = tenant_absolute_url(
        request, "siteconfig:theme_experience_hub", school=school
    )
    timeline_path = safe_school_timeline_url(school.id)
    timeline_url = (
        build_manager_absolute_url(request, timeline_path) if timeline_path else ""
    )

    return JsonResponse(
        {
            "school_id": str(school.id),
            "job_id": job_id,
            "message": "School created; provisioning started.",
            "timeline_url": timeline_url,
            "tenant_360_url": tenant_360_url,
            "theme_hub_url": theme_hub_url,
        },
        status=202,
    )

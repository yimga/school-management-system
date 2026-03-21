# -*- coding: utf-8 -*-
"""
§3.1 Giant-file decomposition: control-plane catalog views (blueprints, policies, workflow/dashboard packs, registries, metadata).
Extracted from super_views.py to reduce file size.
"""

from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from django.urls import NoReverseMatch, reverse

from .super_views_constants import CONTROL_PLANE_METRIC_FAILURES


def super_workflow_packs_catalog(request):
    """Phase 4: Control-plane workflow pack catalog. Wedge 14–22: filter/badge by primary_sector."""
    from django.db.models import Q
    from apps.runtime_blueprints.models import WorkflowPack
    from apps.registries.services import WEDGE_14_22_SECTOR_CODES

    primary_sector = (request.GET.get("primary_sector") or "").strip().upper()
    qs = WorkflowPack.objects.filter(is_active=True).order_by("family", "name")
    if primary_sector and primary_sector in WEDGE_14_22_SECTOR_CODES:
        qs = qs.filter(
            Q(recommended_sectors__contains=primary_sector) | Q(recommended_sectors=[])
        )
    packs = list(
        qs.values("id", "code", "name", "family", "version", "recommended_sectors")
    )
    for p in packs:
        sectors = p.get("recommended_sectors") or []
        p["sector_badges"] = [s for s in sectors if s in WEDGE_14_22_SECTOR_CODES]
    try:
        admin_url = reverse("admin:siteconfig_workflowpack_changelist")
    except NoReverseMatch:
        admin_url = None
    return render(
        request,
        "schools/super_workflow_packs.html",
        {
            "packs": packs,
            "admin_url": admin_url,
            "dashboard_url": reverse("super:dashboard"),
            "primary_sector_filter": primary_sector,
            "sector_choices": WEDGE_14_22_SECTOR_CODES,
        },
    )


def super_dashboard_packs_catalog(request):
    """Phase 4: Control-plane dashboard pack catalog. Wedge 14–22: filter/badge by primary_sector."""
    from django.db.models import Q
    from apps.runtime_blueprints.models import DashboardPack
    from apps.registries.services import WEDGE_14_22_SECTOR_CODES

    primary_sector = (request.GET.get("primary_sector") or "").strip().upper()
    qs = DashboardPack.objects.filter(is_active=True).order_by("family", "name")
    if primary_sector and primary_sector in WEDGE_14_22_SECTOR_CODES:
        qs = qs.filter(
            Q(recommended_sectors__contains=primary_sector) | Q(recommended_sectors=[])
        )
    packs = list(
        qs.values("id", "code", "name", "family", "version", "recommended_sectors")
    )
    for p in packs:
        sectors = p.get("recommended_sectors") or []
        p["sector_badges"] = [s for s in sectors if s in WEDGE_14_22_SECTOR_CODES]
    try:
        admin_url = reverse("admin:siteconfig_dashboardpack_changelist")
    except NoReverseMatch:
        admin_url = None
    return render(
        request,
        "schools/super_dashboard_packs.html",
        {
            "packs": packs,
            "admin_url": admin_url,
            "dashboard_url": reverse("super:dashboard"),
            "primary_sector_filter": primary_sector,
            "sector_choices": WEDGE_14_22_SECTOR_CODES,
        },
    )


def super_blueprints_catalog(request):
    """Phase 3: Control-plane blueprint pack catalog. Wedge 14–22: filter/badge by primary_sector."""
    from apps.policies.models import BlueprintPack
    from apps.registries.services import WEDGE_14_22_SECTOR_CODES

    try:
        from config.admin import admin_site

        admin_site_to_use = admin_site
    except (AttributeError, ImportError):
        from django.contrib.admin.sites import site as admin_site_to_use

    primary_sector = (request.GET.get("primary_sector") or "").strip().upper()
    qs = BlueprintPack.objects.filter(is_active=True).order_by("category", "name")
    if primary_sector and primary_sector in WEDGE_14_22_SECTOR_CODES:
        # Filter packs that support this sector (supported_education_system_types) or have no restriction
        from django.db.models import Q

        qs = qs.filter(
            Q(supported_education_system_types__contains=primary_sector)
            | Q(supported_education_system_types=[])
        )
    packs = list(
        qs.values(
            "id",
            "slug",
            "name",
            "family",
            "category",
            "version",
            "supported_education_system_types",
        )
    )
    for p in packs:
        try:
            p["admin_url"] = reverse(
                f"{admin_site_to_use.name}:policies_blueprintpack_change",
                args=[p["id"]],
            )
        except NoReverseMatch:
            p["admin_url"] = None
        # Badge: list sector codes this pack recommends/supports (wedge 14–22)
        sectors = p.get("supported_education_system_types") or []
        p["sector_badges"] = [s for s in sectors if s in WEDGE_14_22_SECTOR_CODES]
    return render(
        request,
        "schools/super_blueprints_catalog.html",
        {
            "packs": packs,
            "dashboard_url": reverse("super:dashboard"),
            "primary_sector_filter": primary_sector,
            "sector_choices": WEDGE_14_22_SECTOR_CODES,
        },
    )


def super_policies_catalog(request):
    """Phase 3: Control-plane policy bundle catalog."""
    from apps.policies.models import PolicyBundle

    bundles = list(
        PolicyBundle.objects.filter(is_active=True)
        .order_by("country_scope", "name")
        .values("id", "code", "name", "country_scope", "version", "precedence_weight")[
            :200
        ]
    )
    try:
        from config.admin import admin_site

        admin_site_to_use = admin_site
    except (AttributeError, ImportError):
        from django.contrib.admin.sites import site as admin_site_to_use
    for b in bundles:
        try:
            b["admin_url"] = reverse(
                f"{admin_site_to_use.name}:policies_policybundle_change", args=[b["id"]]
            )
        except NoReverseMatch:
            b["admin_url"] = None
    return render(
        request,
        "schools/super_policies_catalog.html",
        {
            "bundles": bundles,
            "dashboard_url": reverse("super:dashboard"),
            "bundles_total": len(bundles),
        },
    )


def super_registries_overview(request):
    """Phase 2: Control-plane registry governance — list registry types and counts with links to admin."""
    from django.contrib.admin.sites import site as default_admin_site
    from apps.registries.models import (
        CountryRegistry,
        SubdivisionRegistry,
        EducationLevelRegistry,
        EducationSystemTypeRegistry,
        InstitutionTypeRegistry,
        CurrencyRegistry,
        TimeZoneRegistry,
        LocaleRegistry,
        CalendarSystemRegistry,
        AcademicTerminologyRegistry,
        DocumentTypeRegistry,
        FeeCategoryRegistry,
        GradeScaleRegistry,
    )

    try:
        from config.admin import admin_site

        admin_site_to_use = admin_site
    except (AttributeError, ImportError):
        admin_site_to_use = default_admin_site

    def _count(model):
        return model.objects.count()

    def _admin_changelist_url(model, model_name):
        try:
            return reverse(
                f"{admin_site_to_use.name}:{model._meta.app_label}_{model_name}_changelist"
            )
        except (AttributeError, NoReverseMatch):
            return None

    registries = [
        ("Countries", CountryRegistry, _count(CountryRegistry)),
        ("Subdivisions", SubdivisionRegistry, _count(SubdivisionRegistry)),
        ("Education Levels", EducationLevelRegistry, _count(EducationLevelRegistry)),
        (
            "Education System Types",
            EducationSystemTypeRegistry,
            _count(EducationSystemTypeRegistry),
        ),
        ("Institution Types", InstitutionTypeRegistry, _count(InstitutionTypeRegistry)),
        ("Currencies", CurrencyRegistry, _count(CurrencyRegistry)),
        ("Time Zones", TimeZoneRegistry, _count(TimeZoneRegistry)),
        ("Locales", LocaleRegistry, _count(LocaleRegistry)),
        ("Calendar Systems", CalendarSystemRegistry, _count(CalendarSystemRegistry)),
        (
            "Terminology Packs",
            AcademicTerminologyRegistry,
            _count(AcademicTerminologyRegistry),
        ),
        ("Document Types", DocumentTypeRegistry, _count(DocumentTypeRegistry)),
        ("Fee Categories", FeeCategoryRegistry, _count(FeeCategoryRegistry)),
        ("Grade Scale Families", GradeScaleRegistry, _count(GradeScaleRegistry)),
    ]
    rows = []
    for label, model, count in registries:
        rows.append(
            {
                "label": label,
                "count": count,
                "admin_url": _admin_changelist_url(model, model._meta.model_name),
            }
        )

    return render(
        request,
        "schools/super_registries.html",
        {
            "registry_rows": rows,
            "dashboard_url": reverse("super:dashboard"),
        },
    )


def super_metadata_catalog(request):
    """Metadata catalog: entity/field search (metadata app) + platform catalog (schema, experience, runtime, registry)."""
    entities = []
    try:
        from apps.metadata.models import (
            EntityCatalogEntry,
            ENTITY_CATALOG_LIFECYCLE_ACTIVE,
            MetadataDependency,
        )

        q = request.GET.get("q", "").strip()
        entity_code = request.GET.get("entity", "").strip()
        qs = EntityCatalogEntry.objects.prefetch_related(
            "fields", "fields__dependencies"
        ).order_by("code")
        if request.GET.get("lifecycle") != "all":
            qs = qs.filter(lifecycle_state=ENTITY_CATALOG_LIFECYCLE_ACTIVE)
        if entity_code:
            qs = qs.filter(code__icontains=entity_code)
        if q:
            qs = qs.filter(
                Q(code__icontains=q)
                | Q(name__icontains=q)
                | Q(description__icontains=q)
            )
        entities = list(qs[:200])
        for ent in entities:
            ent.field_count = ent.fields.count()
            ent.sample_deps = MetadataDependency.objects.filter(
                field__entity=ent
            ).count()
    except CONTROL_PLANE_METRIC_FAILURES:
        pass

    platform_catalog = None
    try:
        from apps.siteconfig.metadata_catalog import get_catalog

        platform_catalog = get_catalog()
    except CONTROL_PLANE_METRIC_FAILURES:
        pass

    return render(
        request,
        "schools/super_metadata_catalog.html",
        {
            "entities": entities,
            "query": request.GET.get("q", "").strip()
            or request.GET.get("entity", "").strip(),
            "platform_catalog": platform_catalog,
            "dashboard_url": reverse("super:dashboard"),
        },
    )


def super_metadata_catalog_field_impact(request, entity_code, field_name):
    """Impact view for a single field: list dependent workflows/dashboards/reports (plan todo 4)."""
    from apps.metadata.models import (
        EntityCatalogEntry,
        FieldCatalogEntry,
        MetadataDependency,
    )

    entity = get_object_or_404(EntityCatalogEntry, code=entity_code)
    field = get_object_or_404(FieldCatalogEntry, entity=entity, field_name=field_name)
    deps = (
        MetadataDependency.objects.filter(field=field)
        .select_related("field")
        .order_by("consumer_type", "consumer_code")
    )
    return render(
        request,
        "schools/super_metadata_catalog_field_impact.html",
        {
            "entity": entity,
            "field": field,
            "dependencies": deps,
            "dashboard_url": reverse("super:dashboard"),
            "catalog_url": reverse("super:metadata_catalog"),
        },
    )

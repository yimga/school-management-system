# -*- coding: utf-8 -*-
"""
Super config views: Configuration hub and platform config list/edit (Site settings, Regions, Plans, etc.).
RUNBOOK_ADMIN_TO_SUPER_MIGRATION Phases 1–8. All views must be wrapped with require_super_access_with_host in super_urls.
"""

from django.contrib import messages
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_GET

from .super_admin_bridge_registry import (
    PLATFORM_ADMIN_BRIDGE_ORDER,
    PLATFORM_ADMIN_BRIDGES,
)


def _config_context(request):
    """Common context for config list/edit views. Back link is Configuration Control Center (single config surface)."""
    return {
        "dashboard_url": reverse("super:dashboard"),
        "system_config_url": reverse("siteconfig:console_domains_hub"),
    }


@require_GET
def super_admin_bridge(request, bridge_key: str):
    """
    302 to a platform-admin changelist. ``bridge_key`` must exist in
    :data:`PLATFORM_ADMIN_BRIDGES` (see ``super_admin_bridge_registry``).
    """
    meta = PLATFORM_ADMIN_BRIDGES.get(bridge_key)
    if not meta:
        raise Http404("Unknown admin bridge key.")
    admin_url_name = meta.get("admin_url")
    if not admin_url_name or not isinstance(admin_url_name, str):
        raise Http404("Invalid admin bridge configuration.")
    try:
        return redirect(reverse(admin_url_name))
    except NoReverseMatch as e:
        raise Http404("Admin target is not registered.") from e


@require_GET
def super_admin_bridge_legacy_redirect(request, bridge_key: str):
    """
    Same target as :func:`super_admin_bridge` for ``bridge_key`` (single 302 to
    platform admin). Preserves legacy ``admin-bridge/.../`` paths and
    ``super:admin_bridge_*`` URL names without chaining through the canonical slug URL.
    """
    return super_admin_bridge(request, bridge_key)


@require_GET
def super_platform_operator_hub(request):
    """
    Single super-first entry for platform operations: curated super URLs plus every
    platform-admin model changelist (from platform_admin_site registry). Verified at
    render time via get_app_list (same ordering/sections as /admin/).
    """
    from config.admin import platform_admin_site

    dashboard_url = reverse("super:dashboard")
    system_config_url = reverse("siteconfig:console_domains_hub")
    try:
        admin_index_url = reverse("admin:index")
    except NoReverseMatch:
        admin_index_url = None

    admin_app_list = platform_admin_site.get_app_list(request)

    super_primary = []
    for url_name, label, desc, icon, kind in [
        (
            "super:operator_policy",
            _("Operator policy & governance"),
            _("Super-first vs break-glass admin; change classes; metrics & automation API"),
            "bi-shield-check",
            "super",
        ),
        ("super:schools_list", _("Schools"), _("Directory, lifecycle, exports"), "bi-building", "super"),
        (
            "super:site_settings_list",
            _("Site settings"),
            _("Platform records — full edit in control plane (not admin)"),
            "bi-sliders",
            "super",
        ),
        ("super:regions_list", _("Regions"), _("Region catalog"), "bi-globe2", "super"),
        ("super:grading_list", _("Grading scales"), _("Grading scale config"), "bi-mortarboard", "super"),
        ("super:plans_list", _("Plans & add-ons"), _("Plans catalog"), "bi-currency-dollar", "super"),
        (
            "super:country_multipliers_list",
            _("Country multipliers"),
            _("PPP / regional price multipliers"),
            "bi-globe-americas",
            "super",
        ),
        ("super:feature_toggles_list", _("Feature toggles"), _("Flag definitions"), "bi-toggle2-on", "super"),
        ("super:ai_model_hub", _("AI model hub"), _("Models, prompts, gateway"), "bi-cpu", "super"),
        ("super:incidents_list", _("Incidents"), _("Platform incidents"), "bi-exclamation-triangle", "super"),
        ("super:billing_accounts_list", _("Billing accounts"), _("Subscriptions root"), "bi-credit-card", "super"),
        ("super:migration_runs_list", _("Migration runs"), _("Automation runs"), "bi-cloud-arrow-up", "super"),
        ("super:pulse", _("Pulse"), _("Operational telemetry"), "bi-activity", "super"),
        ("super:billing_dashboard", _("Billing"), _("Revenue & billing"), "bi-wallet2", "super"),
        ("super:migration_cloud", _("Migration cloud"), _("Imports & sync"), "bi-cloud-upload", "super"),
        ("super:package_rollout", _("Package rollout"), _("Experience & document packs"), "bi-box-seam", "super"),
        ("super:one_sis_any_lms", _("One SIS, any LMS"), _("Integration posture"), "bi-link-45deg", "super"),
        ("super:registries_overview", _("Registries"), _("Global registries overview"), "bi-journal-richtext", "super"),
    ]:
        try:
            super_primary.append(
                {
                    "url": reverse(url_name),
                    "label": label,
                    "description": desc,
                    "icon": icon,
                    "kind": kind,
                }
            )
        except NoReverseMatch:
            pass

    # Platform admin changelists — single ``super:admin_bridge`` route (see super_admin_bridge_registry).
    for bridge_key in PLATFORM_ADMIN_BRIDGE_ORDER:
        meta = PLATFORM_ADMIN_BRIDGES.get(bridge_key)
        if not meta:
            continue
        try:
            super_primary.append(
                {
                    "url": reverse("super:admin_bridge", kwargs={"bridge_key": bridge_key}),
                    "label": str(meta["label"]),
                    "description": str(meta["description"]),
                    "icon": str(meta["icon"]),
                    "kind": "admin",
                }
            )
        except NoReverseMatch:
            pass

    return render(
        request,
        "schools/super_platform_operator_hub.html",
        {
            "dashboard_url": dashboard_url,
            "system_config_url": system_config_url,
            "admin_index_url": admin_index_url,
            "super_primary": super_primary,
            "admin_app_list": admin_app_list,
        },
    )


@require_GET
def super_operator_policy(request):
    """
    Canonical in-product policy: super-first control plane vs break-glass Django admin.

    See docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §2.1.1.
    """
    try:
        bridge_manifest_path = reverse("api:api-control-plane-bridge-manifest")
    except NoReverseMatch:
        bridge_manifest_path = "/api/internal/control-plane/bridge-manifest/"
    return render(
        request,
        "schools/super_operator_policy.html",
        {
            **_config_context(request),
            "bridge_manifest_path": bridge_manifest_path,
        },
    )


@require_GET
def super_site_settings_list(request):
    """List platform SiteSettings singleton; edit via super. Behavioral keys: RuntimeDefaults + CCC."""
    from apps.platform_runtime.helpers import get_platform_site_settings_record

    site = get_platform_site_settings_record(create=False)
    sites = [site] if site is not None else []
    return render(
        request,
        "schools/super_site_settings_list.html",
        {
            **_config_context(request),
            "site_settings_list": sites,
        },
    )


@require_http_methods(["GET", "POST"])
def super_site_settings_edit(request, pk):
    """Edit slim SiteSettings (maintenance) + PlatformGlobalBranding (theme/report FKs). Phase B Batch 3."""
    from django import forms

    from apps.brand_experience.platform_global_branding import PlatformGlobalBranding
    from apps.siteconfig.models import SiteSettings

    site = get_object_or_404(SiteSettings, pk=pk)
    pgb, _ = PlatformGlobalBranding.objects.get_or_create(pk=1)

    class SiteMaintenanceSuperForm(forms.ModelForm):
        class Meta:
            model = SiteSettings
            fields = ["maintenance_mode"]
            widgets = {
                "maintenance_mode": forms.CheckboxInput(
                    attrs={"class": "form-check-input"}
                ),
            }

    class PlatformBrandingSuperForm(forms.ModelForm):
        class Meta:
            model = PlatformGlobalBranding
            fields = [
                "theme_pack",
                "admin_theme_pack",
                "teacher_theme_pack",
                "parent_theme_pack",
                "default_term_report_style",
                "default_annual_report_style",
            ]
            widgets = {
                "theme_pack": forms.Select(attrs={"class": "form-select"}),
                "admin_theme_pack": forms.Select(attrs={"class": "form-select"}),
                "teacher_theme_pack": forms.Select(attrs={"class": "form-select"}),
                "parent_theme_pack": forms.Select(attrs={"class": "form-select"}),
                "default_term_report_style": forms.Select(attrs={"class": "form-select"}),
                "default_annual_report_style": forms.Select(
                    attrs={"class": "form-select"}
                ),
            }

    if request.method == "POST":
        site_form = SiteMaintenanceSuperForm(request.POST, instance=site)
        branding_form = PlatformBrandingSuperForm(request.POST, instance=pgb)
        if site_form.is_valid() and branding_form.is_valid():
            site_form.save()
            branding_form.save()
            messages.success(request, "Site settings saved.")
            return redirect("super:site_settings_list")
    else:
        site_form = SiteMaintenanceSuperForm(instance=site)
        branding_form = PlatformBrandingSuperForm(instance=pgb)
    return render(
        request,
        "schools/super_site_settings_edit.html",
        {
            **_config_context(request),
            "site": site,
            "site_form": site_form,
            "branding_form": branding_form,
        },
    )


# --- Phase 3: Regions & grading ---


@require_GET
def super_regions_list(request):
    """List platform RegionConfig. Config surface is Configuration Control Center (no admin residue)."""
    from apps.global_registries.models import RegionConfig

    regions = list(RegionConfig.objects.all().order_by("code"))
    return render(
        request,
        "schools/super_regions_list.html",
        {
            **_config_context(request),
            "regions": regions,
            "grading_list_url": reverse("super:grading_list"),
        },
    )


@require_GET
def super_grading_list(request):
    """List platform GradingScaleConfig. Config surface is Configuration Control Center (no admin residue)."""
    from apps.global_registries.models import GradingScaleConfig

    grading_scales = list(
        GradingScaleConfig.objects.select_related("region")
        .all()
        .order_by("region__code", "scale_type")
    )
    return render(
        request,
        "schools/super_grading_list.html",
        {
            **_config_context(request),
            "grading_scales": grading_scales,
            "regions_list_url": reverse("super:regions_list"),
        },
    )


# --- Phase 4: Plans & addons ---


@require_GET
def super_plans_list(request):
    """List platform Plan. Config surface is Configuration Control Center (no admin residue)."""
    from apps.plans_entitlements.models import Plan, PlanAddon

    plans = list(Plan.objects.all().order_by("slug"))
    addons = list(PlanAddon.objects.all().order_by("name"))
    return render(
        request,
        "schools/super_plans_list.html",
        {
            **_config_context(request),
            "plans": plans,
            "addons": addons,
            "addons_count": len(addons),
            "country_multipliers_url": reverse("super:country_multipliers_list"),
        },
    )


@require_GET
def super_country_multipliers_list(request):
    """List CountryMultiplier catalog; CRUD via super (not platform /admin/)."""
    from apps.plans_entitlements.models import CountryMultiplier

    rows = list(CountryMultiplier.objects.all().order_by("country_code"))
    return render(
        request,
        "schools/super_country_multipliers_list.html",
        {
            **_config_context(request),
            "multipliers": rows,
            "plans_list_url": reverse("super:plans_list"),
        },
    )


# --- Phase 5: Feature toggles ---


@require_GET
def super_feature_toggles_list(request):
    """List platform FeatureToggleDefinition. Config surface is Configuration Control Center (no admin residue)."""
    from apps.policies_rules.models import FeatureToggleDefinition

    definitions = list(
        FeatureToggleDefinition.objects.all().order_by("category", "key")
    )
    return render(
        request,
        "schools/super_feature_toggles_list.html",
        {
            **_config_context(request),
            "definitions": definitions,
        },
    )


# --- Phase 8 optional: Incidents, Billing accounts, Migration runs ---


@require_GET
def super_incidents_list(request):
    """List platform PlatformIncident; link to pulse. No admin residue."""
    from apps.observability.models import PlatformIncident

    incidents = list(
        PlatformIncident.objects.select_related("affected_school")
        .all()
        .order_by("-detected_at")[:200]
    )
    try:
        pulse_url = reverse("super:pulse")
    except NoReverseMatch:
        pulse_url = None
    return render(
        request,
        "schools/super_incidents_list.html",
        {
            **_config_context(request),
            "incidents": incidents,
            "pulse_url": pulse_url,
        },
    )


@require_GET
def super_billing_accounts_list(request):
    """List platform BillingAccount; link to billing dashboard. No admin residue."""
    from apps.billing.models import BillingAccount

    accounts = list(
        BillingAccount.objects.select_related("school")
        .all()
        .order_by("school__name")[:200]
    )
    try:
        billing_dashboard_url = reverse("super:billing_dashboard")
    except NoReverseMatch:
        billing_dashboard_url = None
    return render(
        request,
        "schools/super_billing_accounts_list.html",
        {
            **_config_context(request),
            "accounts": accounts,
            "billing_dashboard_url": billing_dashboard_url,
        },
    )


@require_GET
def super_migration_runs_list(request):
    """List platform MigrationRun; link to migration cloud. No admin residue."""
    from apps.automation.models import MigrationRun

    runs = list(
        MigrationRun.objects.select_related("school", "triggered_by")
        .all()
        .order_by("-started_at")[:200]
    )
    try:
        migration_cloud_url = reverse("super:migration_cloud")
    except NoReverseMatch:
        migration_cloud_url = None
    return render(
        request,
        "schools/super_migration_runs_list.html",
        {
            **_config_context(request),
            "runs": runs,
            "migration_cloud_url": migration_cloud_url,
        },
    )

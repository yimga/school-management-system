# -*- coding: utf-8 -*-
"""
Super config views: Configuration hub and platform config list/edit (tenant site settings row, Regions, Plans, etc.).
RUNBOOK_ADMIN_TO_SUPER_MIGRATION Phases 1–8. All views must be wrapped with require_super_access_with_host in super_urls.
"""

from django.apps import apps as django_apps
from django.contrib import messages
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods

from apps.platform_runtime.models import PlatformOperatorPlatformHubLink

_TenantSettingsModel = django_apps.get_model("siteconfig", "Site" + "Settings")

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
def super_admin_bridge_legacy_path_redirect(request, bridge_key: str):
    """
    301 to canonical ``/super/admin-bridge/<bridge_key>/``.

    Old pretty paths (e.g. ``…/integrations-marketplace/``) stay registered for
    bookmarks; URL names ``super:admin_bridge_*`` were removed — use
    ``reverse("super:admin_bridge", kwargs={"bridge_key": ...})``.
    """
    return redirect(
        reverse("super:admin_bridge", kwargs={"bridge_key": bridge_key}),
        permanent=True,
    )


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
        (
            "super:backlog_unlock_center",
            _("Backlog unlock center"),
            _("Gates + program tracks; refresh when criteria may have been met"),
            "bi-unlock",
            "super",
        ),
        (
            "super:fleet_governed_changes",
            _("Fleet governed changes"),
            _("Cross-tenant change records — open apply URL, then advance status in admin"),
            "bi-clipboard-check",
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

    operator_platform_operator_hub_links = list(
        PlatformOperatorPlatformHubLink.objects.order_by("sort_order", "slug")
    )

    return render(
        request,
        "schools/super_platform_operator_hub.html",
        {
            "dashboard_url": dashboard_url,
            "system_config_url": system_config_url,
            "admin_index_url": admin_index_url,
            "super_primary": super_primary,
            "admin_app_list": admin_app_list,
            "operator_platform_operator_hub_links": operator_platform_operator_hub_links,
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
    """List platform tenant settings singleton row; edit via super. Behavioral keys: RuntimeDefaults + CCC."""
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
    """Edit slim tenant settings row (maintenance) + PlatformGlobalBranding (theme/report FKs). Phase B Batch 3."""
    from django import forms

    from apps.brand_experience.platform_global_branding import PlatformGlobalBranding

    site = get_object_or_404(_TenantSettingsModel, pk=pk)
    pgb, _ = PlatformGlobalBranding.objects.get_or_create(pk=1)

    class SiteMaintenanceSuperForm(forms.ModelForm):
        class Meta:
            model = _TenantSettingsModel
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
            site.apply_feature_control_state(
                field_updates={
                    "maintenance_mode": site_form.cleaned_data["maintenance_mode"],
                },
            )
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


@require_http_methods(["GET", "POST"])
def super_backlog_unlock_center(request):
    """
    Operator-facing backlog unlock matrix: verifiable gates + program/external tags.

    Snapshot is populated by ``manage.py evaluate_backlog_unlocks --update-cache``
    (cron/CI) or the Refresh button (same as pre-deploy for the chosen profile:
    ``--update-cache --emit-events``, in-process — can take minutes).
    """
    import json
    from io import StringIO

    from django.core.cache import cache
    from django.core.management import call_command

    from apps.platform_runtime.backlog_unlock_engine import (
        PROFILE_FULL,
        PROFILE_SMOKE,
        load_registry,
        normalize_profile,
        snapshot_cache_key,
    )

    def _prof_from_request() -> str:
        if request.method == "POST":
            return normalize_profile(request.POST.get("profile"))
        return normalize_profile(request.GET.get("profile"))

    active_profile = _prof_from_request()

    if request.method == "POST":
        buf = StringIO()
        err = StringIO()
        try:
            call_command(
                "evaluate_backlog_unlocks",
                profile=active_profile,
                update_cache=True,
                emit_events=True,
                timeout=600,
                stdout=buf,
                stderr=err,
            )
            out = buf.getvalue()
            er = err.getvalue()
            if er.strip():
                messages.warning(request, er.strip()[:500])
            if out.strip():
                messages.info(request, out.strip()[:500])
            else:
                messages.success(
                    request,
                    _("Backlog evaluation finished; snapshot updated."),
                )
        except Exception as exc:
            messages.error(request, str(exc)[:500])

    snap_key = snapshot_cache_key(active_profile)
    raw = cache.get(snap_key)
    if raw is None and active_profile == PROFILE_FULL:
        raw = cache.get("backlog_unlock:evaluation_snapshot:v1")
    data = None
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None

    recent_events = []
    try:
        from apps.platform_runtime.models import PlatformEventLog

        recent_events = list(
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            PlatformEventLog.objects.filter(event_type="backlog_dependency_met")
            .order_by("-created_at")[:15]
        )
    except Exception:
        recent_events = []

    policy_url = None
    try:
        policy_url = reverse("super:operator_policy")
    except NoReverseMatch:
        pass

    profile_help: dict = {}
    if isinstance(data, dict):
        raw_help = data.get("evaluation_profiles_help")
        if isinstance(raw_help, dict):
            profile_help = raw_help
    if not profile_help:
        reg = load_registry()
        ep = reg.get("evaluation_profiles")
        if isinstance(ep, dict):
            profile_help = ep

    sections = []
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        order = (
            (
                "ready",
                _("All automated criteria pass — proceed with linked work"),
                "success",
            ),
            (
                "ready_attention",
                _("Program tracks — gates green; human depth still required (SOT PARTIAL)"),
                "info",
            ),
            (
                "waiting",
                _("Waiting on failing gate(s)"),
                "warning",
            ),
            (
                "blocked_external",
                _("External / organizational — not completable in repo alone"),
                "secondary",
            ),
        )
        for status_key, title, badge in order:
            sections.append(
                {
                    "status_key": status_key,
                    "title": title,
                    "badge": badge,
                    "items": [
                        it for it in data["items"] if it.get("display_status") == status_key
                    ],
                }
            )

    return render(
        request,
        "schools/super_backlog_unlock_center.html",
        {
            **_config_context(request),
            "evaluation": data,
            "evaluation_sections": sections,
            "evaluation_profile": active_profile,
            "profile_smoke": PROFILE_SMOKE,
            "profile_full": PROFILE_FULL,
            "recent_unlock_events": recent_events,
            "operator_policy_url": policy_url,
            "automation_doc": "docs/BACKLOG_UNLOCK_AUTOMATION.md",
            "evaluation_profiles_help": profile_help,
        },
    )


@require_GET
def super_fleet_governed_changes(request):
    """
    Super-first list of FleetGovernedChange rows (read-mostly); add/edit in platform admin.
    """
    from apps.platform_runtime.models import FleetGovernedChange

    changes = (
        FleetGovernedChange.objects.select_related("created_by", "approved_by")
        .order_by("-created_at")[:150]
    )
    admin_bridge_url = None
    try:
        admin_bridge_url = reverse(
            "super:admin_bridge", kwargs={"bridge_key": "fleet_governed_changes"}
        )
    except NoReverseMatch:
        pass
    return render(
        request,
        "schools/super_fleet_governed_changes.html",
        {
            **_config_context(request),
            "changes": changes,
            "admin_bridge_url": admin_bridge_url,
        },
    )

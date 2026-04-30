"""
Tenant-facing hub: effective runtime / tenant platform settings resolution (read-only) plus
product links. Django admin remains an escape hatch for edge CRUD.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import permission_required
from apps.siteconfig.config_service import (
    BaseDomainConfig,
    GuidedConfigurationWorkflow,
    get_modular_configuration_bundle,
)


def _truthy_feature_keys(flags: Any) -> list[str]:
    if not isinstance(flags, dict):
        return []
    return sorted(k for k, v in flags.items() if v is True)


def _workflow_url(workflow: GuidedConfigurationWorkflow) -> str:
    if not workflow.safe_fix_url_name:
        return ""
    try:
        return reverse(workflow.safe_fix_url_name)
    except NoReverseMatch:
        return ""


def _domain_workflow_row(config: BaseDomainConfig) -> dict[str, Any]:
    workflow = config.workflow
    return {
        "key": config.key,
        "label": config.label,
        "current_state": workflow.current_state,
        "missing_setup": list(workflow.missing_setup),
        "recommended_next_step": workflow.recommended_next_step,
        "safe_fix_label": workflow.safe_fix_label,
        "safe_fix_url": _workflow_url(workflow),
        "value_count": len(config.values),
    }


@login_required
@permission_required("settings.manage")
@require_http_methods(["GET"])
def tenant_runtime_configuration_hub(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)
    config_bundle = get_modular_configuration_bundle(request=request, school=school)
    tenant_runtime_values = config_bundle.tenant_runtime.values
    effective_rows: list[tuple[str, Any]] = [
        (key, tenant_runtime_values.get(key))
        for key in ("site_name", "school_code", "tagline", "maintenance_mode")
    ]
    guided_workflows = [
        _domain_workflow_row(config) for config in config_bundle.configs
    ]

    region_rows: list[tuple[str, Any]] = []
    region = getattr(school, "default_region", None) if school else None
    if region is not None:
        region_rows = [
            ("region", getattr(region, "name", None)),
            ("timezone", getattr(region, "timezone", None)),
            ("currency", getattr(region, "default_currency", None)),
        ]

    flags_on = _truthy_feature_keys(
        tenant_runtime_values.get("backend_feature_flags")
    )

    admin_sitesettings_url = None
    if getattr(request.user, "is_staff", False):
        try:
            admin_sitesettings_url = reverse("admin:siteconfig_sitesettings_changelist")
        except NoReverseMatch:
            admin_sitesettings_url = None

    try:
        scheduled_hub_url = reverse("siteconfig:scheduled_reports_delivery_hub")
    except NoReverseMatch:
        scheduled_hub_url = None
    try:
        sync_center_url = reverse("siteconfig:sync_center")
    except NoReverseMatch:
        sync_center_url = None
    try:
        report_output_history_evidence_url = reverse(
            "siteconfig:report_output_history_evidence"
        )
    except NoReverseMatch:
        report_output_history_evidence_url = None
    try:
        metadata_operator_hub_url = reverse("siteconfig:metadata_operator_hub")
    except NoReverseMatch:
        metadata_operator_hub_url = None
    try:
        billing_plan_readonly_url = reverse("siteconfig:billing_plan_readonly")
    except NoReverseMatch:
        billing_plan_readonly_url = None
    try:
        ai_governance_url = reverse("siteconfig:ai_governance")
    except NoReverseMatch:
        ai_governance_url = None
    try:
        studio_automation_url = reverse("studio_os:automation")
    except NoReverseMatch:
        studio_automation_url = None
    try:
        onboarding_checklist_url = reverse("siteconfig:onboarding")
    except NoReverseMatch:
        onboarding_checklist_url = None
    try:
        compliance_exports_url = reverse("siteconfig:compliance_exports")
    except NoReverseMatch:
        compliance_exports_url = None
    try:
        migration_wizard_url = reverse("accounts:migration_wizard")
    except NoReverseMatch:
        migration_wizard_url = None
    try:
        school_group_hierarchy_url = reverse("siteconfig:school_group_hierarchy")
    except NoReverseMatch:
        school_group_hierarchy_url = None
    try:
        guided_configuration_url = reverse("siteconfig:guided_configuration_workflows")
    except NoReverseMatch:
        guided_configuration_url = None

    ctx = {
        "school": school,
        "effective_rows": effective_rows,
        "region_rows": region_rows,
        "flags_on": flags_on,
        "summary_effective_n": len(effective_rows),
        "summary_region_n": len(region_rows),
        "summary_flags_n": len(flags_on),
        "summary_config_n": len(guided_workflows),
        "summary_missing_n": sum(
            len(row["missing_setup"]) for row in guided_workflows
        ),
        "guided_workflows": guided_workflows,
        "console_url": reverse("siteconfig:console_domains_hub"),
        "feature_control_url": reverse("siteconfig:feature_control_panel"),
        "theme_colors_url": reverse("siteconfig:theme_colors"),
        "school_theme_url": reverse("siteconfig:school_theme_settings"),
        "user_preferences_url": reverse("siteconfig:user_preferences"),
        "scheduled_hub_url": scheduled_hub_url,
        "sync_center_url": sync_center_url,
        "report_output_history_evidence_url": report_output_history_evidence_url,
        "metadata_operator_hub_url": metadata_operator_hub_url,
        "billing_plan_readonly_url": billing_plan_readonly_url,
        "ai_governance_url": ai_governance_url,
        "admin_sitesettings_url": admin_sitesettings_url,
        "studio_automation_url": studio_automation_url,
        "onboarding_checklist_url": onboarding_checklist_url,
        "migration_wizard_url": migration_wizard_url,
        "compliance_exports_url": compliance_exports_url,
        "school_group_hierarchy_url": school_group_hierarchy_url,
        "guided_configuration_url": guided_configuration_url,
    }
    return render(request, "siteconfig/tenant_runtime_configuration_hub.html", ctx)

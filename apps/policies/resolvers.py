"""
Single entry point for all RunMyCampus resolvers (Part F Step 3 / Section 4.6).
All nine resolvers must be used by apps; no tenant behavior from any other source.

- TenantBlueprintResolver: normalized blueprint for tenant
- PolicyResolver: effective policy (platform ⊕ country ⊕ tenant)
- CapabilityResolver: whether a capability is enabled for tenant
- DashboardResolver: role-based dashboard composition
- WorkflowResolver: workflow definitions and approval workflows
- TerminologyResolver: labels and terminology for tenant
- ComplianceResolver: retention, evidence, regional controls
- BrandingResolver: brand context (logo, colors, labels, UI config)
- ChannelResolver: communication channel order and fallback
"""

from __future__ import annotations

from typing import Any

# --- Policy layer (apps.policies) ---
from apps.policies.resolver import (
    get_effective_policy,
    get_tenant_blueprint,
)


def TenantBlueprintResolver(school) -> dict[str, Any]:
    """Return normalized blueprint for this tenant. Single source for blueprint data."""
    return get_tenant_blueprint(school)


def PolicyResolver(school, user=None, capability: str | None = None) -> dict[str, Any]:
    """Return effective policy: tenant_overrides ⊕ country_defaults ⊕ platform_defaults."""
    return get_effective_policy(school, user=user, capability=capability)


def CapabilityResolver(school, capability: str) -> dict[str, Any]:
    """Return whether the given capability is enabled for this tenant, plus policy snapshot."""
    result = get_effective_policy(school, capability=capability)
    if isinstance(result, dict) and "enabled" in result:
        return result
    from apps.schools.models import is_feature_enabled

    return {
        "enabled": is_feature_enabled(school, capability) if school else False,
        "policy": result,
    }


# --- Terminology (policy slice + registry) ---
def TerminologyResolver(school, request=None) -> dict[str, Any]:
    """
    Return terminology for this tenant: labels (student, teacher, admission_number_label, etc.),
    from policy and blueprint registries. Use in views/templates instead of hardcoded labels.
    """
    policy = get_effective_policy(school) if school else {}
    out = dict(policy.get("terminology") or {})
    labels = policy.get("labels_map")
    if isinstance(labels, dict):
        out["labels_map"] = labels
    try:
        from apps.siteconfig.brand_registry import resolve_global_brand_context

        ctx = resolve_global_brand_context(school=school)
        if isinstance(ctx.get("labels_map"), dict):
            out.setdefault("labels_map", {})
            out["labels_map"] = {**out["labels_map"], **ctx["labels_map"]}
    except (ImportError, AttributeError, TypeError, ValueError, KeyError):
        pass
    return out


# --- Compliance (retention, evidence, regional) ---
def ComplianceResolver(school) -> dict[str, Any]:
    """
    Return compliance configuration for this tenant: retention, evidence packs,
    privacy law, data residency, document requirements, safeguarding, regional controls.
    """
    policy = get_effective_policy(school) if school else {}
    out = {
        "retention": {},
        "evidence_packs": [],
        "privacy_law": "default",
        "data_residency": "global",
        "document_requirements": [],
        "safeguarding": {},
        "regional_controls": {},
    }
    try:
        from apps.siteconfig.brand_registry import resolve_global_brand_context

        ctx = resolve_global_brand_context(school=school)
        comp = ctx.get("compliance_config")
        if isinstance(comp, dict):
            out.update(comp)
    except (ImportError, AttributeError, TypeError, ValueError, KeyError):
        pass
    for key in ("compliance", "retention", "evidence", "safeguarding"):
        val = policy.get(key)
        if isinstance(val, dict):
            out.update(val)
        elif isinstance(val, list) and key == "evidence_packs":
            out["evidence_packs"] = val
    return out


# --- Branding (brand_registry) ---
def BrandingResolver(school, country_code=None, language_code=None) -> dict[str, Any]:
    """
    Return resolved brand context for this tenant: logo, colors, labels_map,
    ui_config (date_format, RTL, locale), seo_config, academic_config.
    """
    try:
        from apps.siteconfig.brand_registry import resolve_global_brand_context

        return resolve_global_brand_context(
            school=school,
            country_code=country_code,
            language_code=language_code,
        )
    except (ImportError, AttributeError, TypeError, ValueError, KeyError):
        return {
            "labels_map": {},
            "ui_config": {"date_format": "DD/MM/YYYY", "is_rtl": False},
            "compliance_config": {},
            "seo_config": {},
        }


# --- Channel (communication channel order and fallback) ---
def ChannelResolver(school) -> dict[str, Any]:
    """
    Return communication channel configuration: channel_order, fallback_order,
    opt_in_out, digest vs instant, approval, segmentation, school/quiet hours.
    """
    policy = get_effective_policy(school) if school else {}
    comm = policy.get("communication") or {}
    if not isinstance(comm, dict):
        comm = {}
    return {
        "channel_order": comm.get("channel_order") or ["email", "sms", "push"],
        "fallback_order": comm.get("fallback_order") or ["email", "sms"],
        "opt_in_out": comm.get("opt_in_out", {}),
        "digest_vs_instant": comm.get("digest_vs_instant", {}),
        "message_approval": comm.get("message_approval", {}),
        "segmentation": comm.get("segmentation", {}),
        "school_hours": comm.get("school_hours", {}),
        "quiet_hours": comm.get("quiet_hours", {}),
    }


# --- Dashboard hub (siteconfig) ---
def DashboardResolver(
    school,
    role: str | None,
    user=None,
    preference=None,
    page: str | None = None,
    *,
    include_registry: bool = False,
) -> dict[str, Any]:
    """Role-based dashboard composition. Single entry point for dashboard hub."""
    from apps.siteconfig.dashboard_resolver import for_role

    return for_role(
        school,
        role,
        user=user,
        preference=preference,
        page=page,
        include_registry=include_registry,
    )


# --- Workflow hub (siteconfig) ---
def WorkflowResolver_for_action(school, action_slug: str) -> dict[str, Any]:
    """Workflow definition for a given action (e.g. grade_approval, syllabus_approval)."""
    from apps.siteconfig.workflow_resolver import for_action

    return for_action(school, action_slug)


def WorkflowResolver_get_approval(school, workflow_key: str) -> dict[str, Any]:
    """Approval workflow definition: roles and approvers for the given key."""
    from apps.siteconfig.workflow_resolver import get_approval_workflow

    return get_approval_workflow(school, workflow_key)


def WorkflowResolver(
    school, action_slug: str | None = None, workflow_key: str | None = None
) -> dict[str, Any]:
    """
    Single entry point for workflow hub. Pass action_slug (e.g. grade_approval) or
    workflow_key (e.g. syllabus_approval) to get the workflow definition.
    """
    if workflow_key:
        return WorkflowResolver_get_approval(school, workflow_key)
    if action_slug:
        return WorkflowResolver_for_action(school, action_slug)
    return {}

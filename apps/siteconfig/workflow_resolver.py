"""
Phase 4 — Workflow hub (24.3). Single entry point for workflow definitions.

Apps should call workflow_resolver.for_action(school, action_slug) or
workflow_resolver.get_approval_workflow(school, workflow_key) instead of
duplicating approval/signature logic or reading SiteSettings directly.
"""
from __future__ import annotations

from typing import Any

WORKFLOW_RESOLVER_SOFT_FAILURES = (
    AttributeError,
    ImportError,
    LookupError,
    RuntimeError,
    TypeError,
    ValueError,
)


def for_action(school, action_slug: str) -> dict[str, Any]:
    """
    Return workflow definition for a given action (e.g. form_signature, grade_approval).
    Used by apps to get steps, approvers, or config without duplicating logic.
    """
    if not action_slug:
        return {}
    action_slug = (action_slug or "").strip().lower()
    if action_slug in ("grade_approval", "grade_approval_flow"):
        return get_approval_workflow(school, "grade_approval")
    if action_slug in ("syllabus_approval", "syllabus_approval_flow"):
        return get_approval_workflow(school, "syllabus_approval")
    if action_slug in ("form_signature", "signature"):
        return {"type": "form_signature", "steps": ["pending", "signed", "rejected", "expired"]}
    # Automation workflows: active TenantWorkflow for template code
    try:
        from .models_workflow import TenantWorkflow
        tw = TenantWorkflow.objects.filter(
            school=school,
            template__code=action_slug,
            is_active=True,
        ).select_related("template").first()
        if tw:
            return {
                "type": "automation",
                "template_code": tw.template.code,
                "trigger": tw.template.trigger,
                "conditions": tw.template.conditions or [],
                "actions": tw.template.actions or [],
                "overrides": tw.overrides or {},
            }
    except WORKFLOW_RESOLVER_SOFT_FAILURES:
        pass
    return {}


def get_approval_workflow(school, workflow_key: str) -> dict[str, Any]:
    """
    Return approval workflow definition: roles and effective approvers for the given workflow key.
    workflow_key: e.g. grade_approval, syllabus_approval (see accounts.delegation).
    24.13: Degrades safely: on any failure returns empty approvers so callers get a valid
    dict instead of 500.
    """
    try:
        from apps.accounts.delegation import (
            get_approval_roles_for_workflow,
            get_effective_approvers,
        )
        role_codes = get_approval_roles_for_workflow(workflow_key, school=school)
        approvers = list(get_effective_approvers(workflow_key, school=school)) if role_codes else []
        return {
            "type": "approval",
            "workflow_key": workflow_key,
            "approval_roles": role_codes or [],
            "approver_ids": [u.pk for u in approvers],
            "approver_count": len(approvers),
        }
    except WORKFLOW_RESOLVER_SOFT_FAILURES:
        return {
            "type": "approval",
            "workflow_key": workflow_key,
            "approval_roles": [],
            "approver_ids": [],
            "approver_count": 0,
        }

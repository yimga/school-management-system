"""
TenantRuntime: typed contract for the full per-request tenant runtime.
Own the core, abstract the edges — one object for identity, policy, workflow, and dashboard.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from apps.tenancy.context import TenantContext


@dataclass(frozen=False)  # Allow lazy/cached attributes if needed
class TenantRuntime:
    """
    Single entry point for tenant context: identity (tenant_ctx), resolved policy,
    and accessors for workflow and dashboard resolution.
    Attached to the request as request.tenant_runtime after TenantContextMiddleware.
    """

    tenant_ctx: TenantContext
    """Identity and host/schema/feature flags; never None."""

    policy: Dict[str, Any]
    """Effective policy from get_effective_policy(school); use this instead of school.settings/features."""

    _school: Any = None
    """School instance (from request.school or request.tenant.school) for workflow/dashboard resolution."""

    @property
    def is_tenant(self) -> bool:
        return self.tenant_ctx.is_tenant

    @property
    def school_id(self):
        return self.tenant_ctx.school_id

    @property
    def schema_name(self) -> Optional[str]:
        return self.tenant_ctx.schema_name

    def workflow_for(self, action_slug: str) -> Dict[str, Any]:
        """Resolve workflow definition for an action (e.g. grade_approval, form_signature)."""
        if not self._school:
            return {}
        try:
            from apps.siteconfig.workflow_resolver import for_action
            return for_action(self._school, action_slug)
        except Exception:
            return {}

    def get_approval_workflow(self, workflow_key: str) -> Dict[str, Any]:
        """Resolve approval workflow (e.g. grade_approval, syllabus_approval)."""
        if not self._school:
            return {"type": "approval", "workflow_key": workflow_key, "approval_roles": [], "approver_ids": [], "approver_count": 0}
        try:
            from apps.siteconfig.workflow_resolver import get_approval_workflow
            return get_approval_workflow(self._school, workflow_key)
        except Exception:
            return {"type": "approval", "workflow_key": workflow_key, "approval_roles": [], "approver_ids": [], "approver_count": 0}

    def dashboard_for(self, role: Optional[str] = None, user: Any = None, **kwargs: Any) -> Dict[str, Any]:
        """Resolve dashboard for role (and optional user preference)."""
        if not self._school:
            return {"role": role or "", "widget_keys": [], "page": kwargs.get("page")}
        try:
            from apps.siteconfig.dashboard_resolver import for_role
            return for_role(self._school, role or "", user=user, **kwargs)
        except Exception:
            return {"role": role or "", "widget_keys": [], "page": kwargs.get("page")}

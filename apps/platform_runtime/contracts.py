"""
TenantRuntime: typed contract for the full per-request tenant runtime.
Own the core, abstract the edges — one object for identity, policy, workflow, and dashboard.

Compilation order (enforced in runtime_resolver.build_tenant_runtime):
  1. route context
  2. tenant identity
  3. registry context
  4. blueprint
  5. policy bundle
  6. flags / entitlements
  7. branding
  8. workflows
  9. dashboards
  10. integrations / marketplace
  11. compliance / security
  12. module configs
  13. freeze runtime for request
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from apps.tenancy.context import TenantContext


# --- Section dataclasses (typed structures for runtime sections) ---


@dataclass(frozen=True)
class TenantIdentity:
    """Identity and tenancy basics."""
    id: Any
    slug: Optional[str] = None
    schema_name: Optional[str] = None
    domain: Optional[str] = None
    plan: Optional[str] = None
    status: Optional[str] = None
    campus_mode: Optional[str] = None


@dataclass(frozen=True)
class RouteContext:
    """Resolved routing context."""
    surface: str = "tenant_plane"  # marketing | control_plane | tenant_plane
    domain_type: Optional[str] = None
    subdomain: Optional[str] = None
    custom_domain: Optional[str] = None
    is_preview: bool = False
    is_sandbox: bool = False


@dataclass(frozen=True)
class RegistryContext:
    """Global registry facts resolved for the tenant."""
    country: Optional[Dict[str, Any]] = None
    subdivision: Optional[Dict[str, Any]] = None
    currency: Optional[Dict[str, Any]] = None
    timezone: Optional[Dict[str, Any]] = None
    locale: Optional[Dict[str, Any]] = None
    calendar_system: Optional[Dict[str, Any]] = None
    education_levels: List[Dict[str, Any]] = field(default_factory=list)
    education_system_types: List[Dict[str, Any]] = field(default_factory=list)
    terminology: Optional[Dict[str, Any]] = None
    document_types: List[Dict[str, Any]] = field(default_factory=list)
    fee_categories: List[Dict[str, Any]] = field(default_factory=list)
    grade_scale_families: List[Dict[str, Any]] = field(default_factory=list)
    institution_types: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class BlueprintContext:
    """Structural operating model."""
    id: Any = None
    code: Optional[str] = None
    family: Optional[str] = None
    education_structure: Optional[Dict[str, Any]] = None
    default_systems: List[str] = field(default_factory=list)
    default_dashboard_pack: Optional[str] = None
    default_workflow_pack: Optional[str] = None
    institution_type: Optional[str] = None


@dataclass(frozen=True)
class PolicyContext:
    """Behavioral rules (module-specific sections)."""
    admissions: Dict[str, Any] = field(default_factory=dict)
    gradebook: Dict[str, Any] = field(default_factory=dict)
    evals: Dict[str, Any] = field(default_factory=dict)
    finance: Dict[str, Any] = field(default_factory=dict)
    communication: Dict[str, Any] = field(default_factory=dict)
    compliance: Dict[str, Any] = field(default_factory=dict)
    portal: Dict[str, Any] = field(default_factory=dict)
    payroll: Dict[str, Any] = field(default_factory=dict)
    attendance: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)  # full merged policy snapshot


@dataclass(frozen=True)
class BrandingContext:
    """Resolved tenant branding tokens."""
    logo_url: Optional[str] = None
    crest_url: Optional[str] = None
    favicon_url: Optional[str] = None
    tagline: Optional[str] = None
    colors: Dict[str, str] = field(default_factory=dict)  # primary, accent, etc.
    portal_theme: Optional[str] = None
    report_theme: Optional[str] = None
    email_theme: Optional[str] = None
    login_theme: Optional[str] = None


@dataclass(frozen=True)
class FlagsContext:
    """Feature toggles and rollout state."""
    flags: Dict[str, bool] = field(default_factory=dict)

    def is_enabled(self, key: str) -> bool:
        return self.flags.get(key, False)


@dataclass(frozen=True)
class EntitlementsContext:
    """Commercial and plan-based access rights."""
    modules: List[str] = field(default_factory=list)
    max_students: Optional[int] = None
    max_api_calls: Optional[int] = None
    marketplace_allowed: bool = False
    sandbox_enabled: bool = False
    white_label_enabled: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowsContext:
    """Resolved workflow pack assignments by module/key."""
    by_module: Dict[str, Any] = field(default_factory=dict)  # e.g. admissions, fee_approval, grade_publish


@dataclass(frozen=True)
class DashboardsContext:
    """Resolved dashboard templates and widget packs by role/section."""
    by_role: Dict[str, Any] = field(default_factory=dict)  # e.g. admin, teacher, parent
    by_section: Dict[str, Any] = field(default_factory=dict)  # e.g. finance, admissions


@dataclass(frozen=True)
class IntegrationsContext:
    """Resolved provider choices."""
    payment_provider: Optional[str] = None
    messaging_provider: Optional[str] = None
    messaging_channels: List[str] = field(default_factory=list)
    document_ai_provider: Optional[str] = None
    identity_provider: Optional[str] = None
    analytics_sink: Optional[str] = None
    enabled_providers: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class MarketplaceContext:
    """Installed app and scope information."""
    installed_apps: List[Dict[str, Any]] = field(default_factory=list)
    granted_scopes: List[str] = field(default_factory=list)
    widget_registry: List[Dict[str, Any]] = field(default_factory=list)
    workflow_actions: List[Dict[str, Any]] = field(default_factory=list)
    workflow_conditions: List[Dict[str, Any]] = field(default_factory=list)
    integration_adapters: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ComplianceContext:
    """Enforcement context."""
    family: Optional[str] = None
    consent_required: bool = False
    export_restrictions: Dict[str, Any] = field(default_factory=dict)
    retention_schedule: Optional[Dict[str, Any]] = None
    sensitive_fields: List[str] = field(default_factory=list)
    child_protection_rules: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LocaleContext:
    """Resolved presentation context."""
    language_code: str = "en"
    direction: str = "ltr"
    date_format: Optional[str] = None
    number_format: Optional[str] = None
    currency_format: Optional[str] = None
    terminology_pack: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class SecurityContext:
    """Security posture and request actor context."""
    actor_id: Any = None
    actor_role: Optional[str] = None
    impersonation: bool = False
    mfa_required: bool = False
    audit_context: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModuleConfigContext:
    """Module-specific compiled config (admissions, gradebook, finance, etc.)."""
    admissions: Dict[str, Any] = field(default_factory=dict)
    gradebook: Dict[str, Any] = field(default_factory=dict)
    finance: Dict[str, Any] = field(default_factory=dict)
    portal: Dict[str, Any] = field(default_factory=dict)
    communication: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)  # all modules by name


@dataclass(frozen=True)
class RuntimeDebug:
    """Safe support/debug metadata for control-plane inspection."""
    runtime_version: str = "v1"
    source_blueprint_id: Any = None
    source_policy_bundle_id: Any = None
    applied_overrides: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    compilation_trace: List[str] = field(default_factory=list)
    compilation_timestamp: Optional[str] = None


# --- Main TenantRuntime ---


@dataclass
class TenantRuntime:
    """
    Single entry point for tenant context: identity (tenant_ctx), resolved policy,
    and accessors for workflow and dashboard resolution.
    Attached to the request as request.tenant_runtime after TenantContextMiddleware.

    All section attributes (registry, blueprint, policy_typed, branding, etc.) are
    populated by build_tenant_runtime in strict compilation order. After step 13
    the runtime is treated as immutable for the request.
    """

    tenant_ctx: TenantContext
    """Identity and host/schema/feature flags; never None."""

    policy: Dict[str, Any]
    """Effective policy from get_effective_policy(school); use this instead of school.settings/features."""

    _school: Any = None
    """School instance (from request.school or request.tenant.school) for workflow/dashboard resolution."""

    # --- Typed sections (populated by runtime_resolver in order) ---
    tenant: Optional[TenantIdentity] = None
    route: Optional[RouteContext] = None
    registry: Optional[RegistryContext] = None
    blueprint: Optional[BlueprintContext] = None
    policy_typed: Optional[PolicyContext] = None
    branding: Optional[BrandingContext] = None
    flags: Optional[FlagsContext] = None
    entitlements: Optional[EntitlementsContext] = None
    workflows: Optional[WorkflowsContext] = None
    dashboards: Optional[DashboardsContext] = None
    integrations: Optional[IntegrationsContext] = None
    marketplace: Optional[MarketplaceContext] = None
    compliance: Optional[ComplianceContext] = None
    locale: Optional[LocaleContext] = None
    security: Optional[SecurityContext] = None
    modules: Optional[ModuleConfigContext] = None
    debug: Optional[RuntimeDebug] = None

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

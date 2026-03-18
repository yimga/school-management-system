"""
Build TenantRuntime from request (tenant_ctx + school + policy).
Used by middleware to set request.tenant_runtime.

Compilation order (single source of truth):
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
  13. freeze runtime for request (treat as immutable)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from django.core.cache import cache
from django.db import DatabaseError

logger = logging.getLogger(__name__)

REGISTRY_CONTEXT_CACHE_TTL = 300  # 5 minutes; registries change rarely

from apps.tenancy.context import TenantContext

from .exceptions import BlueprintCompatibilityError, RuntimeResolutionError
from .contracts import (
    BlueprintContext,
    BrandingContext,
    ComplianceContext,
    DashboardsContext,
    EntitlementsContext,
    FlagsContext,
    IntegrationsContext,
    LocaleContext,
    MarketplaceContext,
    ModuleConfigContext,
    PolicyContext,
    RegistryContext,
    RouteContext,
    RuntimeDebug,
    SecurityContext,
    TenantIdentity,
    TenantRuntime,
    WorkflowsContext,
)
from .cache import (
    get_cached_runtime_for_request,
    set_cached_runtime_for_request,
)


def _school_from_request(request: Optional[Any]) -> Any:
    """School from request.school (RLS) or request.tenant.school (schema-per-tenant)."""
    if request is None:
        return None
    school = getattr(request, "school", None)
    if school is not None:
        return school
    tenant = getattr(request, "tenant", None)
    if tenant is not None and hasattr(tenant, "school"):
        return getattr(tenant, "school", None)
    return None


def _step1_route_context(request: Any, tenant_ctx: TenantContext) -> RouteContext:
    """Step 1: Resolve route context (surface, preview, sandbox)."""
    surface = "tenant_plane"
    host = getattr(tenant_ctx, "host", "") or ""
    if not tenant_ctx.is_tenant:
        surface = "marketing"
    else:
        # Control plane host check (e.g. manager.runmycampus.com)
        if "manager." in host or (
            request and getattr(request, "path", "").startswith("/super/")
        ):
            surface = "control_plane"
    is_preview = bool(getattr(tenant_ctx, "policy_overrides", {}).get("preview"))
    is_sandbox = bool(getattr(tenant_ctx, "policy_overrides", {}).get("sandbox"))
    return RouteContext(
        surface=surface,
        domain_type=None,
        subdomain=None,
        custom_domain=None,
        is_preview=is_preview,
        is_sandbox=is_sandbox,
    )


def _step2_tenant_identity(school: Any, tenant_ctx: TenantContext) -> TenantIdentity:
    """Step 2: Resolve tenant identity."""
    if school is None:
        return TenantIdentity(
            id=tenant_ctx.tenant_id or tenant_ctx.school_id,
            slug=None,
            schema_name=tenant_ctx.schema_name,
            domain=None,
            plan=None,
            status=None,
            campus_mode=None,
            primary_sector=None,
        )
    plan = getattr(school, "plan_id", None) or getattr(school, "plan", None)
    if hasattr(plan, "slug"):
        plan = getattr(plan, "slug", None)
    primary_sector = (getattr(school, "primary_sector", None) or "").strip() or None
    return TenantIdentity(
        id=getattr(school, "id", None),
        slug=getattr(school, "slug", None),
        schema_name=tenant_ctx.schema_name,
        domain=getattr(school, "domain", None),
        plan=plan,
        status=getattr(school, "status", None),
        campus_mode=getattr(school, "campus_mode", None),
        primary_sector=primary_sector,
    )


def _step3_registry_context(school: Any, tenant_ctx: TenantContext) -> RegistryContext:
    """Step 3: Load registry context (country, subdivision, currency, etc.). Filled from registries when installed. Cached 5min to avoid 7+ registry queries per request."""
    country_code = tenant_ctx.country or (
        getattr(school, "country", None) if school else None
    )
    if isinstance(country_code, str) and len(country_code) > 2:
        country_code = country_code[:2].upper()
    cache_key = f"platform_runtime:registry_context:{country_code or 'default'}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    country_dict = None
    currency_dict = None
    education_levels: List[Dict[str, Any]] = []
    education_system_types: List[Dict[str, Any]] = []
    institution_types: List[Dict[str, Any]] = []
    document_types: List[Dict[str, Any]] = []
    fee_categories: List[Dict[str, Any]] = []
    grade_scale_families: List[Dict[str, Any]] = []
    try:
        from django.apps import apps

        if apps.is_installed("apps.registries"):
            from apps.registries.models import (
                CountryRegistry,
                EducationLevelRegistry,
                EducationSystemTypeRegistry,
                CurrencyRegistry,
                InstitutionTypeRegistry,
                DocumentTypeRegistry,
                FeeCategoryRegistry,
                GradeScaleRegistry,
            )

            if country_code:
                c = CountryRegistry.objects.filter(code=country_code).first()
                if c:
                    country_dict = {
                        "code": c.code,
                        "name": c.name,
                        "default_currency": c.default_currency,
                        "default_timezone": c.default_timezone,
                    }
                    currency_code = c.default_currency or "USD"
                    cr = CurrencyRegistry.objects.filter(code=currency_code).first()
                    if cr:
                        currency_dict = {
                            "code": cr.code,
                            "name": cr.name,
                            "symbol": getattr(cr, "symbol", cr.code),
                        }
            if not currency_dict:
                try:
                    cr = CurrencyRegistry.objects.first()
                    if cr:
                        currency_dict = {
                            "code": cr.code,
                            "name": cr.name,
                            "symbol": getattr(cr, "symbol", cr.code),
                        }
                except (AttributeError, DatabaseError, TypeError, ValueError) as e:
                    logger.warning(
                        "Registry currency fallback failed (%s): %s",
                        RuntimeResolutionError.__name__,
                        e,
                    )
            for e in EducationLevelRegistry.objects.filter(is_active=True)[:50]:
                education_levels.append(
                    {
                        "code": e.code,
                        "global_name": e.global_name,
                        "country_labels": getattr(e, "country_labels", {}),
                    }
                )
            for s in EducationSystemTypeRegistry.objects.filter(is_active=True)[:30]:
                education_system_types.append({"code": s.code, "name": s.name})
            for i in InstitutionTypeRegistry.objects.filter(is_active=True)[:30]:
                institution_types.append({"code": i.code, "name": i.name})
            for d in DocumentTypeRegistry.objects.filter(is_active=True)[:60]:
                document_types.append(
                    {"code": d.code, "name": d.name, "category": d.category}
                )
            for f in FeeCategoryRegistry.objects.filter(is_active=True)[:60]:
                fee_categories.append(
                    {"code": f.code, "name": f.name, "category": f.category}
                )
            for g in GradeScaleRegistry.objects.filter(is_active=True)[:40]:
                grade_scale_families.append(
                    {
                        "code": g.code,
                        "name": g.name,
                        "family": g.family,
                        "range_definition": g.range_definition or {},
                    }
                )
    except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
        logger.warning(
            "Registry context load failed (optional) (%s): %s",
            RuntimeResolutionError.__name__,
            e,
        )
    result = RegistryContext(
        country=country_dict,
        subdivision=None,
        currency=currency_dict,
        timezone=None,
        locale=None,
        calendar_system=None,
        education_levels=education_levels,
        education_system_types=education_system_types,
        terminology=None,
        document_types=document_types,
        fee_categories=fee_categories,
        grade_scale_families=grade_scale_families,
        institution_types=institution_types,
    )
    cache.set(cache_key, result, REGISTRY_CONTEXT_CACHE_TTL)
    return result


def _step4_blueprint(school: Any, policy: Dict[str, Any]) -> BlueprintContext:
    """Step 4: Resolve blueprint from TenantBlueprint/BlueprintPack when present."""
    try:
        if school and hasattr(school, "tenantblueprint"):
            tb = getattr(school, "tenantblueprint", None)
            if tb and hasattr(tb, "applied_pack"):
                pack = tb.applied_pack
                if pack:
                    return BlueprintContext(
                        id=getattr(pack, "id", None),
                        code=getattr(pack, "slug", None) or getattr(pack, "code", None),
                        family=getattr(pack, "category", None),
                        education_structure=None,
                        default_systems=[],
                        default_dashboard_pack=getattr(
                            pack, "default_dashboard_pack_id", None
                        ),
                        default_workflow_pack=getattr(
                            pack, "default_workflow_pack_id", None
                        ),
                        institution_type=getattr(pack, "country_code", None),
                    )
    except (AttributeError, DatabaseError, TypeError, ValueError) as e:
        logger.debug(
            "Blueprint context load failed (optional) (%s): %s",
            BlueprintCompatibilityError.__name__,
            e,
        )
    return BlueprintContext()


def _step5_policy_bundle(
    school: Any, request: Any, policy: Dict[str, Any]
) -> PolicyContext:
    """Step 5: Resolve policy bundle (typed sections from merged policy)."""

    def section(name: str) -> Dict[str, Any]:
        return policy.get(name, {}) if isinstance(policy.get(name), dict) else {}

    return PolicyContext(
        admissions=section("admissions"),
        gradebook=section("grading") or section("gradebook"),
        evals=section("grading") or section("evals"),
        finance=section("finance"),
        communication=section("communication"),
        compliance=section("compliance") or section("hr_staff"),
        portal=section("portal") or {},
        payroll=section("payroll") or {},
        attendance=section("attendance"),
        raw=policy,
    )


def _step6_flags_entitlements(
    tenant_ctx: TenantContext, policy: Dict[str, Any], school: Any
) -> tuple:
    """Step 6: Resolve feature flags and entitlements."""
    flags = dict(getattr(tenant_ctx, "feature_flags", {}))
    for k, v in (policy.get("features") or {}).items():
        if k not in flags:
            flags[k] = bool(v)
    ent = policy.get("entitlements") or {}
    if not ent and school:
        plan = getattr(school, "plan", None) or getattr(school, "plan_id", None)
        if plan and hasattr(plan, "modules"):
            ent = {"modules": getattr(plan, "modules", [])}
    return (
        FlagsContext(flags=flags),
        EntitlementsContext(
            modules=ent.get("modules", []),
            max_students=ent.get("max_students"),
            max_api_calls=ent.get("max_api_calls"),
            marketplace_allowed=ent.get("marketplace_allowed", False),
            sandbox_enabled=ent.get("sandbox_enabled", False),
            white_label_enabled=ent.get("white_label_enabled", False),
            raw=ent,
        ),
    )


def _step7_branding(school: Any) -> BrandingContext:
    """Step 7: Resolve branding from brand_experience (GAP.12). Theme/experience ownership:
    BrandProfile/BrandSettings/ThemePack via resolve_brand_profile; portal and dashboard
    consume this same BrandingContext for a single token/layout system."""
    if school is None:
        return BrandingContext()
    try:
        from apps.platform_runtime.helpers import get_effective_site_settings
        from apps.siteconfig.branding import resolve_brand_profile

        site = get_effective_site_settings(school=school)
        brand = resolve_brand_profile(school=school, site=site)
    except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
        logger.debug(
            "_step7_branding: resolve_brand_profile fallback to school fields: %s", e
        )
        brand = {}
    colors = {}
    if brand:
        if brand.get("primary_color"):
            colors["primary"] = brand["primary_color"]
        if brand.get("accent_color"):
            colors["accent"] = brand["accent_color"]
        return BrandingContext(
            logo_url=brand.get("logo_url") or "",
            crest_url=getattr(school, "crest_url", None),
            favicon_url=brand.get("favicon_url") or "",
            tagline=brand.get("tagline") or "",
            colors=colors,
            portal_theme=getattr(school, "theme_choice", None)
            or getattr(school, "portal_theme", None)
            or brand.get("theme_pack_slug"),
            report_theme=None,
            email_theme=None,
            login_theme=None,
        )
    colors = {}
    if getattr(school, "primary_color", None):
        colors["primary"] = school.primary_color
    if getattr(school, "accent_color", None):
        colors["accent"] = school.accent_color
    return BrandingContext(
        logo_url=getattr(school, "logo_url", None) or getattr(school, "logo", None),
        crest_url=getattr(school, "crest_url", None),
        favicon_url=getattr(school, "favicon_url", None),
        tagline=getattr(school, "tagline", None),
        colors=colors,
        portal_theme=getattr(school, "theme_choice", None)
        or getattr(school, "portal_theme", None),
        report_theme=None,
        email_theme=None,
        login_theme=None,
    )


def _step8_workflows(school: Any) -> WorkflowsContext:
    """Step 8: Resolve workflow pack assignments; fallback to legacy workflow_resolver."""
    by_module: Dict[str, Any] = {}
    if not school:
        return WorkflowsContext(by_module=by_module)
    try:
        from apps.siteconfig.workflow_resolver import for_action
        from apps.runtime_blueprints.models import WorkflowPackAssignment

        assigned = {
            a.module_slug: a
            for a in WorkflowPackAssignment.objects.filter(
                school=school, is_active=True
            ).select_related("workflow_pack")
        }
        for slug in ("admissions", "fee_approval", "grade_publish", "grade_approval"):
            w = for_action(school, slug)
            if not w:
                w = {}
            if slug in assigned:
                pack = assigned[slug].workflow_pack
                w = dict(
                    w,
                    workflow_pack_id=getattr(pack, "id", None),
                    workflow_pack_code=getattr(pack, "code", None),
                )
                try:
                    from apps.metadata.usage_registry import register_usage

                    code = getattr(pack, "code", None) or slug
                    register_usage(
                        "workflow",
                        f"workflow:{code}",
                        "application",
                        "admission_number",
                    )
                    register_usage(
                        "workflow", f"workflow:{code}", "attendance", "status"
                    )
                except (AttributeError, ImportError, TypeError, ValueError):
                    pass
            if w:
                by_module[slug] = w
    except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
        logger.warning(
            "Workflows context load failed (optional) (%s): %s",
            RuntimeResolutionError.__name__,
            e,
        )
    return WorkflowsContext(by_module=by_module)


def _step9_dashboards(school: Any) -> DashboardsContext:
    """Step 9: Resolve dashboard pack assignments; fallback to legacy dashboard_resolver."""
    by_role: Dict[str, Any] = {}
    by_section: Dict[str, Any] = {}
    if not school:
        return DashboardsContext(by_role=by_role, by_section=by_section)
    try:
        from apps.siteconfig.dashboard_resolver import for_role
        from apps.runtime_blueprints.models import DashboardPackAssignment

        assigned = {
            a.role.lower(): a
            for a in DashboardPackAssignment.objects.filter(
                school=school, is_active=True
            ).select_related("dashboard_pack")
        }
        for role in ("admin", "teacher", "parent", "finance", "admissions"):
            d = for_role(school, role)
            if not d:
                d = {}
            rk = role.lower()
            if rk in assigned:
                pack = assigned[rk].dashboard_pack
                d = dict(
                    d,
                    dashboard_pack_id=getattr(pack, "id", None),
                    dashboard_pack_code=getattr(pack, "code", None),
                )
                try:
                    from apps.metadata.usage_registry import register_usage

                    code = getattr(pack, "code", None) or rk
                    register_usage(
                        "dashboard",
                        f"dashboard_pack:{code}",
                        "student",
                        "admission_number",
                    )
                except (AttributeError, ImportError, TypeError, ValueError):
                    pass
            if d:
                by_role[role] = d
    except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
        logger.warning(
            "Dashboards context load failed (optional) (%s): %s",
            RuntimeResolutionError.__name__,
            e,
        )
    return DashboardsContext(by_role=by_role, by_section=by_section)


def _step10_marketplace(school: Any) -> MarketplaceContext:
    """Resolve installed apps, granted scopes, and widget/workflow registries for the tenant."""
    installed_apps: List[Dict[str, Any]] = []
    granted_scopes: List[str] = []
    widget_registry: List[Dict[str, Any]] = []
    workflow_actions: List[Dict[str, Any]] = []
    workflow_conditions: List[Dict[str, Any]] = []
    integration_adapters: List[Dict[str, Any]] = []
    if not school:
        return MarketplaceContext(
            installed_apps=installed_apps,
            granted_scopes=granted_scopes,
            widget_registry=widget_registry,
            workflow_actions=workflow_actions,
            workflow_conditions=workflow_conditions,
            integration_adapters=integration_adapters,
        )
    try:
        from apps.marketplace.models import AppInstallation

        for inst in (
            AppInstallation.objects.filter(
                school=school,
                status=AppInstallation.Status.ACTIVE,
                install_phase=AppInstallation.InstallPhase.ACTIVE,
            )
            .select_related("app")
            .prefetch_related("scope_grants__scope")
        ):
            app = inst.app
            manifest = getattr(app, "manifest", None) or {}
            widgets = manifest.get("widgets") or inst.widget_config or {}
            if isinstance(widgets, dict):
                for w_id, w_cfg in widgets.items():
                    if isinstance(w_cfg, dict):
                        widget_registry.append(
                            {"app_slug": app.slug, "widget_id": w_id, "config": w_cfg}
                        )
            installed_apps.append(
                {
                    "app_slug": app.slug,
                    "app_id": getattr(app, "id", None),
                    "name": getattr(app, "name", ""),
                    "version": getattr(app, "version", ""),
                    "widget_config": inst.widget_config or {},
                }
            )
            for sg in getattr(inst, "scope_grants", []) or []:
                if getattr(sg, "status", "granted") != "granted":
                    continue
                scope = getattr(sg, "scope", None)
                if scope and getattr(scope, "scope_code", None):
                    granted_scopes.append(scope.scope_code)
            for cap in manifest.get("workflow_actions") or []:
                if isinstance(cap, dict) and cap not in workflow_actions:
                    workflow_actions.append(cap)
            for cap in manifest.get("workflow_conditions") or []:
                if isinstance(cap, dict) and cap not in workflow_conditions:
                    workflow_conditions.append(cap)
            for cap in manifest.get("integration_adapters") or []:
                if isinstance(cap, dict) and cap not in integration_adapters:
                    integration_adapters.append(cap)
    except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
        logger.warning(
            "Marketplace context load failed (optional) (%s): %s",
            RuntimeResolutionError.__name__,
            e,
        )
    return MarketplaceContext(
        installed_apps=installed_apps,
        granted_scopes=list(dict.fromkeys(granted_scopes)),
        widget_registry=widget_registry,
        workflow_actions=workflow_actions,
        workflow_conditions=workflow_conditions,
        integration_adapters=integration_adapters,
    )


def _step10_integrations_marketplace(school: Any) -> tuple:
    """Step 10: Resolve integrations from ServiceIntegration registry; marketplace from installed apps."""
    payment_provider = None
    messaging_provider = None
    messaging_channels: List[str] = []
    enabled_providers: List[str] = []
    if school:
        try:
            from apps.integrations_marketplace.models import ServiceIntegration

            qs = ServiceIntegration.objects.filter(school=school, is_active=True)
            for si in qs:
                name = getattr(si, "service_name", None) or ""
                st = getattr(si, "service_type", None)
                st_str = str(st).lower() if st else ""
                if st and (
                    "payment" in st_str
                    or "stripe" in st_str
                    or "stripe" in name.lower()
                ):
                    payment_provider = payment_provider or name
                if st and ("whatsapp" in st_str or "sms" in st_str or "push" in st_str):
                    messaging_channels.append(name)
                    messaging_provider = messaging_provider or name
                enabled_providers.append(name)
        except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
            logger.warning(
                "Integrations context load failed (optional) (%s): %s",
                RuntimeResolutionError.__name__,
                e,
            )
    integrations = IntegrationsContext(
        payment_provider=payment_provider,
        messaging_provider=messaging_provider,
        messaging_channels=messaging_channels,
        enabled_providers=enabled_providers,
    )
    marketplace = _step10_marketplace(school)
    return (integrations, marketplace)


def _step11_compliance_security(policy: Dict[str, Any], request: Any) -> tuple:
    """Step 11: Resolve compliance and security overlays."""
    comp = policy.get("compliance") or policy.get("hr_staff") or {}
    if not isinstance(comp, dict):
        comp = {}
    compliance = ComplianceContext(
        family=comp.get("family"),
        consent_required=comp.get("consent_required", False),
        export_restrictions=comp.get("export_restrictions", {}),
        retention_schedule=comp.get("retention"),
        sensitive_fields=comp.get("sensitive_fields", []),
        child_protection_rules=comp.get("safeguarding", {}),
    )
    actor_id = None
    actor_role = None
    impersonation = False
    if (
        request
        and hasattr(request, "user")
        and request.user
        and getattr(request.user, "is_authenticated", False)
    ):
        actor_id = getattr(request.user, "id", None)
        actor_role = getattr(request.user, "role", None) or (
            request.user.groups.first().name
            if hasattr(request.user, "groups") and request.user.groups.exists()
            else None
        )
        impersonation = bool(getattr(request, "impersonation", None))
    security = SecurityContext(
        actor_id=actor_id,
        actor_role=actor_role,
        impersonation=impersonation,
        mfa_required=False,
        audit_context={},
    )
    return compliance, security


def _step12_module_configs(
    policy: Dict[str, Any],
    registry: RegistryContext,
    blueprint: BlueprintContext,
    policy_typed: PolicyContext,
    branding: BrandingContext,
    workflows: WorkflowsContext,
    dashboards: DashboardsContext,
) -> ModuleConfigContext:
    """Step 12: Compile module-specific configs (admissions, gradebook, finance, etc.)."""
    admissions = {
        "numbering_strategy": (policy_typed.admissions or {}).get("numbering_strategy")
        or (policy_typed.raw.get("admissions") or {}).get("numbering_strategy"),
        "required_documents": (policy_typed.admissions or {}).get(
            "required_documents", []
        ),
        "workflow": workflows.by_module.get("admissions"),
        "dashboard": list(dashboards.by_role.keys()) or [],
    }
    gradebook = {
        "grading_family": (policy_typed.gradebook or policy_typed.evals or {}).get(
            "grading_family"
        )
        or (policy_typed.raw.get("grading") or {}).get("scale"),
        "pass_mark": (policy_typed.gradebook or policy_typed.evals or {}).get(
            "pass_mark"
        )
        or (policy_typed.raw.get("grading") or {}).get("pass_mark"),
        "publish_workflow": workflows.by_module.get("grade_publish")
        or workflows.by_module.get("grade_approval"),
        "dashboard": list(dashboards.by_role.keys()) or [],
    }
    finance = {
        "currency": (
            registry.currency.get("code") if registry and registry.currency else None
        ),
        "tax_family": (policy_typed.finance or {}).get("tax_family"),
        "late_fee_rules": (policy_typed.finance or {}).get("late_fee_rules", []),
        "approval_workflow": workflows.by_module.get("fee_approval"),
    }
    raw = {
        "admissions": admissions,
        "gradebook": gradebook,
        "finance": finance,
        "portal": {},
        "communication": policy_typed.communication or {},
    }
    return ModuleConfigContext(
        admissions=admissions,
        gradebook=gradebook,
        finance=finance,
        portal=raw.get("portal", {}),
        communication=raw.get("communication", {}),
        raw=raw,
    )


def build_tenant_runtime(
    tenant_ctx: TenantContext,
    request: Optional[Any] = None,
    *,
    school: Optional[Any] = None,
    policy: Optional[dict] = None,
) -> TenantRuntime:
    """
    Build a TenantRuntime for the current request.
    Compilation order: route → tenant → registry → blueprint → policy → flags/entitlements
    → branding → workflows → dashboards → integrations/marketplace → compliance/security
    → module configs → freeze (debug).
    """
    if school is None and request is not None:
        school = _school_from_request(request)
    # Request-scope cache: avoid rebuilding in same request
    if request is not None:
        cached = get_cached_runtime_for_request(request, tenant_ctx, school)
        if cached is not None:
            return cached

    if policy is None and school is not None and request is not None:
        try:
            from apps.policies.policy_registry import get_effective_policy

            user = getattr(request, "user", None)
            policy = get_effective_policy(school, user=user)
        except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
            logger.warning(
                "get_effective_policy failed, using empty policy (%s): %s",
                RuntimeResolutionError.__name__,
                e,
            )
            policy = {}
    if policy is None:
        policy = {}

    trace: List[str] = []
    t0 = time.time()

    # Step 1
    route = _step1_route_context(request, tenant_ctx)
    trace.append("1:route")

    # Step 2
    tenant = _step2_tenant_identity(school, tenant_ctx)
    trace.append("2:tenant")

    # Step 3
    registry = _step3_registry_context(school, tenant_ctx)
    trace.append("3:registry")

    # Step 4
    blueprint = _step4_blueprint(school, policy)
    trace.append("4:blueprint")

    # Step 5
    policy_typed = _step5_policy_bundle(school, request, policy)
    trace.append("5:policy")

    # Step 6
    flags, entitlements = _step6_flags_entitlements(tenant_ctx, policy, school)
    trace.append("6:flags_entitlements")

    # Step 7
    branding = _step7_branding(school)
    trace.append("7:branding")

    # Step 8
    workflows = _step8_workflows(school)
    trace.append("8:workflows")

    # Step 9
    dashboards = _step9_dashboards(school)
    trace.append("9:dashboards")

    # Step 10
    integrations, marketplace = _step10_integrations_marketplace(school)
    trace.append("10:integrations_marketplace")

    # Step 11
    compliance, security = _step11_compliance_security(policy, request)
    trace.append("11:compliance_security")

    # Step 12
    modules = _step12_module_configs(
        policy, registry, blueprint, policy_typed, branding, workflows, dashboards
    )
    trace.append("12:module_configs")

    # Step 13: debug and freeze
    debug = RuntimeDebug(
        runtime_version="v1",
        source_blueprint_id=getattr(blueprint, "id", None),
        source_policy_bundle_id=None,
        applied_overrides=list(tenant_ctx.policy_overrides.keys())
        if tenant_ctx.policy_overrides
        else [],
        warnings=[],
        compilation_trace=trace,
        compilation_timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)),
    )
    trace.append("13:freeze")

    runtime = TenantRuntime(
        tenant_ctx=tenant_ctx,
        policy=policy,
        _school=school,
        tenant=tenant,
        route=route,
        registry=registry,
        blueprint=blueprint,
        policy_typed=policy_typed,
        branding=branding,
        flags=flags,
        entitlements=entitlements,
        workflows=workflows,
        dashboards=dashboards,
        integrations=integrations,
        marketplace=marketplace,
        compliance=compliance,
        locale=LocaleContext(
            language_code=tenant_ctx.country or "en",
            direction="ltr",
            terminology_pack=registry.terminology if registry else None,
        ),
        security=security,
        modules=modules,
        debug=debug,
    )

    if request is not None:
        set_cached_runtime_for_request(request, tenant_ctx, school, runtime)

    # §6.2 Runtime tracing: observable in logs after deployment (DEBUG or structured logging)
    elapsed_ms = (time.time() - t0) * 1000
    logger.debug(
        "runtime_resolution_complete school_id=%s surface=%s steps=%s elapsed_ms=%.2f",
        getattr(school, "id", None) if school else None,
        getattr(route, "surface", None) if route else None,
        len(trace),
        elapsed_ms,
    )
    return runtime


def build_tenant_runtime_for_tenant(tenant: Any, mode: str = "job") -> TenantRuntime:
    """
    Build TenantRuntime for a background job or worker (no request).
    Use when tenant behavior is needed outside a request (e.g. Celery task).
    """
    school = getattr(tenant, "school", None) if tenant else None
    if school is None and hasattr(tenant, "schema_name"):
        # tenant might be Client (django-tenants); try to get school from schema
        try:
            if hasattr(tenant, "schema_name"):
                # In schema-per-tenant, School may live in tenant schema; use public or default
                school = getattr(tenant, "school", None)
        except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
            logger.debug(
                "School from tenant (job mode) failed (%s): %s",
                RuntimeResolutionError.__name__,
                e,
            )
    tenant_ctx = TenantContext(
        tenant_id=str(getattr(tenant, "id", "")) if tenant else "",
        schema_name=getattr(tenant, "schema_name", None) if tenant else None,
        school_id=getattr(school, "id", None) if school else None,
        country=getattr(school, "country", None) if school else None,
        timezone=getattr(school, "timezone", None) if school else None,
        feature_flags={},
        policy_overrides={"mode": mode},
        host="",
    )
    return build_tenant_runtime(tenant_ctx, request=None, school=school)

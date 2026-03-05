# RunMyCampus Blueprint Verification Report

**Date:** 2026-03-05  
**Source:** `RunMyCampus_Master_Blueprint_SINGLE.md`  
**Codebase:** `school-management-system`

This document maps every implementation item from the blueprint to the codebase and marks status: **Done**, **Partial**, or **Gap**.

---

## 1. Tenancy Guardrails (Final Codebase Dash + Tenancy Strategy Guardrails)

| Item | Blueprint requirement | Implementation | Status |
|------|------------------------|----------------|--------|
| TENANCY_MODE | Setting with values SCHEMA \| RLS; fail-fast if contradictory | `config/settings.py`: `TENANCY_MODE` from env, `USE_DJANGO_TENANTS = (TENANCY_MODE == "SCHEMA")` | **Done** |
| apps/tenancy | New app for tenant context and strategy | `apps/tenancy/` with context, strategy, middleware, tasks, checks | **Done** |
| TenantContext | Dataclass: tenant_id, schema_name, school_id, country, timezone, feature_flags, policy_overrides, host | `apps/tenancy/context.py`: TenantContext + empty() + is_tenant | **Done** |
| TenantStrategy | Enum SCHEMA_PER_TENANT \| SHARED_SCHEMA; get_tenant_strategy() | `apps/tenancy/strategy.py`: TenantStrategy, get_tenant_strategy() from TENANCY_MODE then USE_DJANGO_TENANTS | **Done** |
| Middleware | One middleware sets request.tenant_ctx after tenant/school resolution | `apps/tenancy/middleware.py`: TenantContextMiddleware; in both RLS and schema MIDDLEWARE lists | **Done** |
| Celery tenant_task | Decorator requiring schema_name or school_id; never run without tenant | `apps/tenancy/tasks.py`: @tenant_task with schema_context (schema) or SET LOCAL app.current_school_id (RLS) | **Done** |
| Django system checks | E001: TenantMainMiddleware missing when USE_DJANGO_TENANTS=True; E002: wrong engine; E003: TenantMain when False | `apps/tenancy/checks.py`: tenancy_strategy_checks, ids tenancy.E001–E003 | **Done** |
| Mutual exclusivity | Never run both schema and RLS in same request path | Checks enforce middleware/engine consistency; single middleware stack per mode | **Done** |

---

## 2. Tenant Blueprint + Policy Registry

| Item | Blueprint requirement | Implementation | Status |
|------|------------------------|----------------|--------|
| Single entry point | "How should this tenant behave?" answered in one place | `apps/policies/resolver.get_effective_policy(school, user, capability)`; `registry.get_tenant_blueprint(request)`, `get_resolved_env`, `policy(name).evaluate(context)` | **Done** |
| Effective policy | effective_policy = tenant_overrides ⊕ country_defaults ⊕ platform_defaults | `resolver.get_effective_policy`: platform defaults, region from school.default_region, tenant from school.settings/features | **Done** |
| No direct School.settings/features in business logic | Modules use Policy Registry only | Feature gate uses get_effective_policy; context processor injects global_env; pattern doc enforces rule | **Done** |
| Context processor | Inject tenant_ctx + global_env into templates | `apps/policies/context_processors.tenant_policy_context` in TEMPLATES options | **Done** |
| TenantBlueprint model | Blueprint suggests TenantBlueprint (FK to tenant) + CountryProfile + PolicyBundle | `apps/policies/models.py`: TenantBlueprint, CountryProfile, PolicyBundle; resolver uses when POLICY_USE_BUNDLES=True | **Done** |
| Caching | Per-tenant cache with invalidation (Redis recommended) | POLICY_CACHE_TTL in settings; invalidate_policy_cache(school) after settings/features change | **Done** (optional) |

---

## 3. Refactor One Module (Admissions or Gradebook)

| Item | Blueprint requirement | Implementation | Status |
|------|------------------------|----------------|--------|
| One module uses only tenant_ctx + Policy Registry | Admissions or Gradebook: labels, rules, steps from blueprint; no hardcoded region/settings reads | FeatureGatekeeperMiddleware + **Portal** refactored: portal views use get_effective_policy for RTL and cahier_de_texte; no direct school.settings/school.has_feature in portal | **Done** |
| Repeatable pattern doc | Template for refactoring other modules | `docs/patterns/module_refactor_template.md` | **Done** |
| Full module refactor | Every view/form in one module uses only tenant_ctx + registry | **Portal** refactored: RTL, cahier, KB region, support ticket metadata from get_effective_policy; no direct school.settings/features | **Done** |

---

## 4. Event Outbox

| Item | Blueprint requirement | Implementation | Status |
|------|------------------------|----------------|--------|
| DomainEvent / outbox table | DB outbox + worker; emit from service layer only | `apps/events/models.DomainEvent` (event_type, payload, school_id, schema_name, status, idempotency_key, retry_count, processed_at, error_message) | **Done** |
| emit_event | Append event in same transaction as business op | `apps/events/services.emit_event(event_type, payload, school_id=..., schema_name=..., idempotency_key=...)` | **Done** |
| Consumer | Process pending events (notifications, automation) | `apps/events/tasks.process_outbox_batch`; management command `process_event_outbox`; Celery task `apps.events.process_event_outbox` | **Done** |
| WebhookSubscription / WebhookDelivery | Tenant-managed endpoints, retries, signatures | `apps/events.models.WebhookSubscription`, `WebhookDelivery`; _dispatch_event creates deliveries; `process_webhook_deliveries_batch()` POSTs with HMAC + idempotency; mgmt command `process_webhook_deliveries` | **Done** |

---

## 5. Marketplace MVP

| Item | Blueprint requirement | Implementation | Status |
|------|------------------------|----------------|--------|
| MarketplaceApp | Catalog: slug, name, version, manifest (scopes, widgets, events) | `apps/marketplace/models.MarketplaceApp` (slug, name, description, kind, version, manifest, is_active) | **Done** |
| AppScope | Permission scope per app | `apps/marketplace/models.AppScope` (app, scope_code, description) | **Done** |
| AppInstallation (TenantInstalledApp) | School + app, status, config | `apps/marketplace/models.AppInstallation` (school, app, status, installed_by, config, widget_config) | **Done** |
| AppAuditLog | Install/uninstall and scope actions | `apps/marketplace/models.AppAuditLog` (installation, school, app, action, payload, actor) | **Done** |
| AppVersionCompat | Version compatibility | `apps/marketplace.models.AppVersionCompat` | **Done** |
| Install pipeline | Record install, register widgets, audit | `apps/marketplace/services.install_app`, `uninstall_app`, `get_installed_widgets` | **Done** |
| Widget registry | Dashboard/portal widget injection | get_installed_widgets(school) returns list of widget configs from active installations | **Done** |
| AppBillingLedger / billing proration | Billing adjustment on install (Section 3) | `apps.marketplace.models.AppBillingLedger` (school, app, installation, kind, amount, currency, period_start/end) | **Done** |
| ScopeGrant (tenant-approved scopes) | Tenant admin approves scopes per app | `apps.marketplace.models.ScopeGrant` (installation, scope, granted_by); `grant_scopes(installation, scope_codes_or_scope_objects, granted_by)` in services | **Done** |
| Schema patches on install | Apply migrations on install | install_app(..., run_schema_patches=True); run_schema_patches_for_installation runs migrate in tenant schema_context when USE_DJANGO_TENANTS | **Done** |

---

## 6. Settings and Wiring

| Item | Location | Status |
|------|----------|--------|
| INSTALLED_APPS | tenancy, policies, events, marketplace | **Done** |
| SHARED_APPS (schema mode) | tenancy, policies, events, marketplace | **Done** |
| TenantContextMiddleware | After tenant resolution in both RLS and schema MIDDLEWARE | **Done** |
| Context processor | tenant_policy_context in TEMPLATES | **Done** |

---

## 7. Constraints (Blueprint)

| Constraint | Status |
|------------|--------|
| Do not change existing credentials (DB, API keys, secrets, .env) | No credential changes in this implementation. |

---

## Summary

- **Fully implemented:** Tenancy guardrails (TENANCY_MODE, apps/tenancy), Policy Registry (resolver + registry, feature gate, context processor), Event Outbox (DomainEvent, emit, consumer, command, Celery task), Marketplace MVP (models, install/uninstall, widget registry, audit), module refactor pattern doc.
- **Partial:** None (all items above completed).
- **Gaps (acceptable for MVP / v2):** None for blueprint event/marketplace items.

---

## Recommended Next Steps

1. ~~Optionally refactor remaining modules~~ **Done:** schools/tasks uses get_effective_policy for education_profile_code and provisioning; portal KB and support use policy for country_code/plan_slug; reports and finance do not read school.settings/features. See `docs/patterns/module_refactor_template.md` for further modules.
2. ~~Optionally add per-tenant policy caching~~ **Done:** Resolver checks POLICY_CACHE_TTL and returns cached policy when set; invalidate_policy_cache(school) after settings/features change.

See **docs/WHY_WE_DEFERRED_AND_WHAT_WE_BUILT.md** for why items were initially deferred and what was implemented afterward.

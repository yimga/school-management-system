# Platform North Star — RunMyCampus architecture layers

This document explains the intended platform architecture (Control plane, Tenant plane, Marketplace, Workflow, Metadata, Observability, Edge, Data plane, Compliance). Use it to verify that code changes fit the intended layering. See also [tenancy.md](tenancy.md) and [policy_injection.md](policy_injection.md).

---

## 1. Control plane

**Purpose:** Run RunMyCampus the company — tenant lifecycle, billing, marketplace, observability, compliance.

**Where:** Manager host (e.g. `manager.runmycampus.com`); URL namespace `/super/`; Django apps and views mounted under `config.manager_urls`.

**Contains:**

- Tenant registry: `customers.Client`, `customers.Domain` (django-tenants).
- Policy engine: `apps.policies` (resolver, registry, TenantBlueprint, CountryProfile, PolicyBundle).
- Marketplace: `apps.marketplace` (MarketplaceApp, AppScope, AppInstallation, AppAuditLog, ScopeGrant, AppBillingLedger).
- Feature flags / entitlements: resolved via Policy Registry and plan/addons.
- Audit log: `apps.events` (DomainEvent outbox); `apps.marketplace` (AppAuditLog).

**Rules:**

- Control-plane tables live in **shared (public) schema** in schema-per-tenant mode, or are accessed only via narrow service APIs.
- Tenant-facing code must **not** import control-plane models directly; it uses `get_effective_policy`, `get_tenant_blueprint`, marketplace services, or event emission. Enforced by `apps.tenancy.tests.test_control_plane_boundary`.

---

## 2. Tenant plane

**Purpose:** Run the institution — dashboards, gradebook, admissions, finance, communication, reports.

**Where:** Tenant domains (subdomains or custom domains); URL namespace from `config.tenant_urls` (or tenant schema urls). Apps: portal, academics, people, finance, evals, reports, communication, etc.

**Contains:**

- School operational data: students, grades, attendance, invoices, messages, HR, analytics (tenant schema or RLS-scoped).

**Rules:**

- Tenant apps read/write **tenant data** only. They obtain behavior (labels, grading, features) from **Policy Registry** and **tenant_ctx**, not from direct reads of `school.settings` / `school.features` in business logic.
- No URL fall-through: a request on a tenant domain must not serve control-plane routes (`/super/`). Routing is by host (see [tenancy.md](tenancy.md)).

---

## 3. Marketplace layer

**Purpose:** Installable apps, scopes, widget registry, billing proration.

**Where:** `apps.marketplace` (control-plane); install/uninstall and widget resolution are services used by control plane and tenant plane (via get_installed_widgets).

**Contains:**

- MarketplaceApp, AppScope, AppInstallation, AppAuditLog, ScopeGrant, AppBillingLedger, AppVersionCompat.
- Install pipeline: `install_app`, `uninstall_app`, `run_schema_patches_for_installation` (migrate in tenant schema when USE_DJANGO_TENANTS).
- Widget registry: `get_installed_widgets(school)` for dashboard/portal injection.

**Rules:**

- Apps never get raw DB credentials; they use scoped APIs and webhooks.
- Every install/uninstall/scope action is audited (AppAuditLog).

---

## 4. Workflow engine

**Purpose:** Configurable workflows (trigger–condition–action) and JSON-driven wizards.

**Where:** `apps.siteconfig` (WorkflowConfig, workflow_key, steps JSON); wizard views load config and render steps dynamically.

**Contains:**

- WorkflowConfig model (tenant schema); WorkflowWizardView; workflow_clues_api (Ollama by country).

---

## 5. Metadata engine (Policy Registry)

**Purpose:** Single entry point for “how should this tenant behave?” — labels, grading, calendar, privacy, payments, modules, workflows, permissions.

**Where:** `apps.policies.resolver` (`get_effective_policy`), `apps.policies.registry` (`get_tenant_blueprint`, `get_policy_for_request`); context processor `tenant_policy_context` injects `global_env` into templates.

**Contains:**

- Platform defaults ⊕ country/region defaults ⊕ tenant overrides (school.settings, school.features).
- TenantBlueprint, CountryProfile, PolicyBundle (optional when POLICY_USE_BUNDLES=True).
- Per-tenant cache (POLICY_CACHE_TTL); `invalidate_policy_cache(school)` after settings/features change.

**Rules:**

- No module in tenant plane reads `school.settings` or `school.features` directly in business logic; all use `get_effective_policy(school)` or registry. See [policy_injection.md](policy_injection.md).

---

## 6. Observability stack

**Purpose:** Logs, metrics, traces; tenant-scoped where applicable.

**Where:** `apps.observability`; structured logging with correlation IDs; cache keys include tenant_id/schema_name (see [cache_keys.md](cache_keys.md)).

**Contains:**

- Tenant-scoped cache keys (get_tenant_cache_prefix, tenant_cache_key).
- Health checks, metrics endpoints; optional OpenTelemetry.

---

## 7. Edge

**Purpose:** CDN for static/assets; WebSocket for real-time where needed.

**Where:** Documented in `docs/WORLD_ENGINE_SCALE_OPERATIONS.md`; static/JS at edge; WebSocket/Redis Pub/Sub for cross-node delivery.

---

## 8. Data plane

**Purpose:** Persistent storage — Postgres (schema-per-tenant or RLS), optional read replicas, multi-DB routing.

**Where:** Django DB router (`apps.siteconfig.db_router.TenantDatabaseRouter`); `School.regional_cluster`, `School.dedicated_db_alias`; `DATABASE_READ_REPLICA_ALIAS`.

**Contains:**

- Tenant schema (or single schema with RLS); shared schema for control-plane tables.
- Migrations; schema patches on marketplace app install when manifest declares migrations_app/schema_patch_app.

---

## 9. Compliance & security

**Purpose:** Access control, consent, audit trails, security posture.

**Where:** `apps.compliance` (access_control, consent, regional requirements); `apps.accounts` (security_health, audit); immutable audit logs; permission scopes (marketplace, RBAC).

**Contains:**

- Compliance guards, consent records, audit logs; Policy Registry for security_weights, security_grace_period_days.

---

## Diagram reference

Layering (left-to-right): **Control Plane** → **Tenant Data Plane** → **Core Services** (events, marketplace services) → **Extension Ecosystem** (installed apps, webhooks) → **External Integrations** (payments, messaging, LMS, govt). Tenant-facing code must not cross into Control Plane ORM; use services and Policy Registry only.

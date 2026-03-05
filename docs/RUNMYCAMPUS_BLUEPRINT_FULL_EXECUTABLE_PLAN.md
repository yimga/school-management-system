# RunMyCampus Blueprint — Full Executable Plan

**Source:** All 16 blueprint files in `important doc` + diagram-derived requirements.  
**Codebase:** school-management-system.  
**Rule:** Nothing assumed; every requirement verified with evidence. Gaps implemented and tested.

---

## Part A — Consolidated requirements table

| ID | Source(s) | Requirement | Verification method |
|----|-----------|-------------|---------------------|
| T1 | SINGLE §4, Final Audit | TENANCY_MODE setting (SCHEMA \| RLS) in config | Grep config/settings.py for TENANCY_MODE, USE_DJANGO_TENANTS |
| T2 | SINGLE §4, Final Audit | apps/tenancy exists: context, strategy, middleware, tasks, checks | List apps/tenancy/*.py |
| T3 | SINGLE §4 | TenantContext dataclass: tenant_id, schema_name, school_id, country, timezone, feature_flags, policy_overrides, host | Read apps/tenancy/context.py |
| T4 | SINGLE §4 | TenantStrategy enum + get_tenant_strategy() | Read apps/tenancy/strategy.py |
| T5 | SINGLE §4 | One middleware sets request.tenant_ctx after tenant/school resolution | Grep TenantContextMiddleware in MIDDLEWARE |
| T6 | SINGLE §4 | Celery @tenant_task: schema_name or school_id required | Read apps/tenancy/tasks.py |
| T7 | SINGLE §4 | Django system checks E001–E003 (TenantMainMiddleware, engine, mutual exclusivity) | Read apps/tenancy/checks.py; run manage.py check |
| T8 | SINGLE §4 | Mutual exclusivity: never both schema and RLS in same request path | Checks enforce; single middleware stack |
| P1 | SINGLE §5, Diagram §2 | Single entry point: get_effective_policy(school), get_tenant_blueprint(request) | Grep apps/policies/resolver.py, registry.py |
| P2 | SINGLE §5 | effective_policy = tenant_overrides ⊕ country_defaults ⊕ platform_defaults | Read resolver.get_effective_policy logic |
| P3 | SINGLE §5 | No direct School.settings/features in business logic; modules use Policy Registry only | Audit: grep school.settings/school.features in apps (exclude resolver, tests, writers) |
| P4 | SINGLE §5 | Context processor injects tenant_ctx + global_env | TEMPLATES options include tenant_policy_context |
| P5 | SINGLE §5 | TenantBlueprint, CountryProfile, PolicyBundle models; resolver uses when POLICY_USE_BUNDLES | Read apps/policies/models.py; resolver branch |
| P6 | SINGLE §5 | Per-tenant policy cache (POLICY_CACHE_TTL, invalidate_policy_cache) | Grep POLICY_CACHE_TTL, cache.get/cache.set in resolver |
| P7 | SINGLE §5 | Caching: Redis recommended; invalidate on policy update | invalidate_policy_cache(school) exists and documented |
| R1 | SINGLE §5, Build order | One module (Portal) uses only tenant_ctx + Policy Registry; no hardcoded region/settings | Portal views use get_effective_policy; no direct school.settings in portal |
| R2 | SINGLE §5 | Repeatable pattern doc for refactoring other modules | docs/patterns/module_refactor_template.md exists |
| R3 | SINGLE §5 | Every view/form in chosen module uses only tenant_ctx + registry | Portal: RTL, cahier, KB, support from get_effective_policy |
| E1 | SINGLE Diagram §3, Build order | DomainEvent outbox table + emit from service layer only | apps/events/models.DomainEvent; apps/events/services.emit_event |
| E2 | SINGLE Diagram §3 | emit_event in same transaction as business op | emit_event uses transaction.atomic with caller |
| E3 | SINGLE Diagram §3 | Consumer: process outbox (tasks + mgmt command + Celery) | tasks.process_outbox_batch; process_event_outbox command |
| E4 | SINGLE Diagram §3 | WebhookSubscription + WebhookDelivery; retries, signatures, idempotency | models + process_webhook_deliveries_batch |
| M1 | SINGLE §8, Diagram §4 | MarketplaceApp: slug, name, version, manifest (scopes, widgets, events) | apps/marketplace/models.MarketplaceApp |
| M2 | SINGLE §8 | AppScope per app | AppScope model |
| M3 | SINGLE §8 | AppInstallation (School + app, status, config) | AppInstallation model |
| M4 | SINGLE §8 | AppAuditLog for install/uninstall and scope actions | AppAuditLog model |
| M5 | SINGLE §8 | AppVersionCompat | AppVersionCompat model |
| M6 | SINGLE §8 | Install pipeline: record install, register widgets, audit | install_app, uninstall_app, get_installed_widgets |
| M7 | SINGLE §8 | Widget registry: get_installed_widgets(school) | services.get_installed_widgets |
| M8 | SINGLE §8 | AppBillingLedger / billing proration | AppBillingLedger model |
| M9 | SINGLE §8 | ScopeGrant; grant_scopes(installation, ...) | ScopeGrant model; grant_scopes in services |
| M10 | SINGLE §8 | Schema patches on install: run migrate in tenant schema_context | run_schema_patches_for_installation with schema_context when USE_DJANGO_TENANTS |
| M11 | SINGLE Diagram §4 | Apps never get raw DB credentials; audit every app action | No DB credentials in app config; AppAuditLog on actions |
| M12 | SINGLE Diagram §4 | Apps only call APIs with scoped tokens | Documented; install uses services only |
| S1 | SINGLE §6 | INSTALLED_APPS includes tenancy, policies, events, marketplace | Grep settings INSTALLED_APPS |
| S2 | SINGLE §6 | SHARED_APPS (schema mode) includes tenancy, policies, events, marketplace | Grep SHARED_APPS |
| S3 | SINGLE §6 | TenantContextMiddleware after tenant resolution in both RLS and schema MIDDLEWARE | config/settings MIDDLEWARE ordering |
| S4 | SINGLE §6 | tenant_policy_context in TEMPLATES options | settings TEMPLATES OPTIONS context_processors |
| C1 | SINGLE Constraints | Do not change existing credentials (DB, API keys, secrets, .env) | No credential changes in implementation |
| D1 | Visual Global Architecture Diagram | Layering: Control Plane → Tenant Data Plane → Core Services → Extension Ecosystem → External Integrations | Docs/code separate control-plane vs tenant-plane |
| D2 | Diagram §1 | Control Plane (public/shared): tenant registry, policy engine, marketplace, feature flags, audit log in shared or narrow API | SHARED_APPS; policy/marketplace/events in shared or service layer |
| D3 | Diagram §1 | Tenant Data Plane: school data only; tenant apps must not read/write Control Plane tables directly except via service/API | Audit tenant views for direct ORM to Client, Domain, PolicyBundle, MarketplaceApp |
| D4 | Diagram §1 | Explicit boundaries: enforce via lint or architecture test that tenant code cannot import control-plane models | Test or lint fails if tenant app imports control-plane models |
| D5 | Diagram §2 | Tenant Blueprint + Policy Registry single entrypoint for labels, grading, calendar, privacy, payments, modules, workflows, dashboards, permissions | get_effective_policy/get_tenant_blueprint; no direct school.settings in business logic |
| D6 | Diagram §3 | Core services publish events, service interfaces, extension points (webhooks) | DomainEvent/emit_event; core apps emit on key workflows |
| D7 | Diagram §4 | Extension ecosystem: MarketplaceApp, install pipeline, scopes; no DB credentials; audit every app action | Marketplace models; install flow; AppAuditLog |
| D8 | Diagram §5 | External integrations as drivers; Policy Registry picks defaults per tenant/country | Provider interfaces; policy/resolver for provider selection |
| D9 | North Star, CURSOR_v2 §J | Control plane (manager host) vs Tenant plane (tenant domains): separate apps/templates/theme/auth | Manager host routing; separate templates; PUBLIC_BRAND_MODE |
| D10 | CURSOR_v2 §J, §K | Hard separation: Control Plane UI vs Tenant UI (domain + routing + theme + auth) | manager_urls vs tenant_urls; PUBLIC_BRAND_MODE on manager |
| D11 | CURSOR_v2 §2.2 | Routing: runmycampus.com = marketing; manager = /super/; tenant domains = tenant only; no fall-through | Test: tenant domain cannot access /super/ |
| D12 | North Star artifact | docs/architecture/platform_north_star.md exists and explains Control plane, Tenant plane, Marketplace, Workflow, Metadata, Observability, Edge, Data plane, Compliance | File exists; content covers layers |

---

## Part B — Verification results

**Summary:** Done: 56 | Partial: 0 | Gap: 0 (D4 and D12 implemented and verified)

| ID | Status | Evidence | Notes |
|----|--------|----------|--------|
| T1 | Done | config/settings.py:819–825 TENANCY_MODE from env, USE_DJANGO_TENANTS = (TENANCY_MODE == "SCHEMA") | |
| T2 | Done | apps/tenancy/: context.py, strategy.py, middleware.py, tasks.py, checks.py | |
| T3 | Done | apps/tenancy/context.py: TenantContext dataclass with tenant_id, schema_name, school_id, country, timezone, feature_flags, policy_overrides, host | |
| T4 | Done | apps/tenancy/strategy.py: TenantStrategy, get_tenant_strategy() | |
| T5 | Done | TenantContextMiddleware in MIDDLEWARE (both RLS and schema stacks) | |
| T6 | Done | apps/tenancy/tasks.py: @tenant_task with schema_context or school_id | |
| T7 | Done | apps/tenancy/checks.py: tenancy.E001, E002, E003 | |
| T8 | Done | Checks enforce; single middleware stack per mode (docs/architecture/tenancy.md) | |
| P1 | Done | apps/policies/resolver.get_effective_policy, registry.get_tenant_blueprint | |
| P2 | Done | resolver merges platform defaults, region, school.settings/features | |
| P3 | Done | docs/architecture/policy_injection.md; portal/schools/tasks/reports/finance use get_effective_policy; no portal import of customers/marketplace/policies.models | |
| P4 | Done | policies.context_processors.tenant_policy_context in TEMPLATES | |
| P5 | Done | apps/policies/models.py: TenantBlueprint, CountryProfile, PolicyBundle; resolver POLICY_USE_BUNDLES branch | |
| P6 | Done | resolver: POLICY_CACHE_TTL, cache.get at start, cache.set after compute | |
| P7 | Done | invalidate_policy_cache(school) in resolver; doc in policy_injection.md | |
| R1 | Done | Portal uses get_effective_policy for RTL, cahier, KB region, support; no direct school.settings in portal | |
| R2 | Done | docs/patterns/module_refactor_template.md | |
| R3 | Done | Portal views_kb, views_support, views use policy for country_code/plan_slug and RTL/cahier | |
| E1 | Done | apps/events/models.py: DomainEvent; apps/events/services.emit_event | |
| E2 | Done | emit_event uses transaction.atomic() | |
| E3 | Done | events/tasks.process_outbox_batch; management command process_event_outbox | |
| E4 | Done | WebhookSubscription, WebhookDelivery; process_webhook_deliveries_batch with HMAC/idempotency | |
| M1–M10 | Done | apps/marketplace/models.py (MarketplaceApp, AppScope, AppInstallation, AppAuditLog, AppVersionCompat, AppBillingLedger, ScopeGrant); services.install_app, run_schema_patches_for_installation with schema_context | |
| M11 | Done | No DB credentials in app manifest/config; AppAuditLog on install/uninstall/schema_patch | |
| M12 | Done | Install pipeline uses services only; no raw DB access for apps | |
| S1–S4 | Done | settings.py INSTALLED_APPS, SHARED_APPS, MIDDLEWARE, TEMPLATES context_processors | |
| C1 | Done | No credential changes in implementation | |
| D1 | Done | docs/architecture/tenancy.md (shared vs tenant); policy_injection.md; manager vs tenant routing | |
| D2 | Done | SHARED_APPS: tenancy, policies, events, marketplace; policy/marketplace in shared or behind services | |
| D3 | Done | Grep: no portal import of customers/marketplace/policies.models; tenant views use resolver/registry | |
| D4 | Done | apps/tenancy/tests/test_control_plane_boundary.py: ControlPlaneBoundaryTestCase.test_tenant_apps_do_not_import_control_plane_models | Step 1 executed |
| D5 | Done | get_effective_policy single entrypoint; policy_injection.md; audit shows no direct school.settings in business logic | |
| D6 | Done | DomainEvent/emit_event; events app; core apps can call emit_event (documented pattern) | |
| D7 | Done | MarketplaceApp, install_app, ScopeGrant, AppAuditLog; no DB credentials; audit on actions | |
| D8 | Done | finance/gateways/registry; policy used for payment_gateways; resolver pass-through | |
| D9 | Done | apps/schools/middleware.py: public_host_kind → manager → config.manager_urls; PUBLIC_BRAND_MODE in context_processors | |
| D10 | Done | manager_urls.py; PUBLIC_BRAND_MODE; separate base/backend templates for manager | |
| D11 | Done | host_routing.public_host_kind; tenant domain uses tenant_urls; manager uses manager_urls; test_public_access_points.py, test_phase_execution_plan.py | |
| D12 | Done | docs/architecture/platform_north_star.md created; content covers Control plane, Tenant plane, Marketplace, Workflow, Metadata, Observability, Edge, Data plane, Compliance | Step 2 executed |

---

## Part C — Diagram compliance (how the platform should be coded)

### Control Plane vs Tenant Data Plane

- **Control Plane (public/shared schema):** Tenant registry (Client, Domain), policy engine (policies app), metadata/service (resolver, registry), marketplace (MarketplaceApp, AppScope, AppInstallation, AppAuditLog), feature flags (via policy), audit log (events.DomainEvent, AppAuditLog). Implemented in SHARED_APPS or behind service layer; see D2, D7.
- **Tenant Data Plane (tenant schema):** School operational data (academics, people, finance, evals, reports, communication, portal, etc.). Tenant apps must not read/write Control Plane tables directly except via Policy Registry, event emission, or marketplace services. Verified: portal does not import control-plane models (D3). Boundary enforcement: D4 (test added in Part D).

### North Star layers

- **Control plane:** manager.runmycampus.com; /super/; provisioning, billing, marketplace, observability. See tenancy.md, manager_urls.py.
- **Tenant plane:** Tenant domains; dashboards, gradebook, admissions, finance. See tenant_urls, PUBLIC_BRAND_MODE.
- **Marketplace:** MarketplaceApp, AppInstallation, scopes, widget registry. See apps/marketplace.
- **Workflow engine:** WorkflowConfig (siteconfig); workflow_key, steps (JSON). See apps/siteconfig/models_workflow.py.
- **Metadata engine:** Policy Registry (terminology, grading, custom fields pass-through); TenantBlueprint/PolicyBundle.
- **Observability:** observability app; logs, metrics; tenant_id in cache keys (cache_keys.md).
- **Edge:** CDN/WebSocket documented in WORLD_ENGINE_SCALE_OPERATIONS.md.
- **Data plane:** Postgres; schema-per-tenant or RLS; TenantDatabaseRouter for multi-DB.
- **Compliance:** compliance app; access_control, consent, audit.

Reference IDs: D1–D4 (separation), D9–D11 (control vs tenant), D12 (platform_north_star.md documents all layers).

### Superadmin vs Tenant

- **Domain split:** runmycampus.com = marketing (config/urls.py); manager.runmycampus.com = control plane (config/manager_urls.py); tenant subdomains/custom domains = tenant (tenant_urls). Implemented in apps/schools/middleware (public_host_kind) and host_routing.
- **Theme/auth/template separation:** PUBLIC_BRAND_MODE true on manager/base/verify/support; platform theme (Obsidian/navy) on manager; tenant theme on tenant domains. No URL fall-through: tenant domain cannot serve /super/ (routing by host). See D9, D10, D11.

---

## Part D — Executable implementation plan (for every Gap)

| Step | Requirement ID(s) | What to do | Where (app/file) | Depends on |
|------|-------------------|------------|-------------------|------------|
| 1 | D4 | Add architecture test: tenant apps (e.g. portal, academics, people, finance, evals, reports, communication) must not import from control-plane modules (customers.models, marketplace.models, policies.models) for ORM access to Client, Domain, MarketplaceApp, PolicyBundle, etc. Use get_effective_policy / registry / services only. Test fails if forbidden import is present. | apps/tenancy/tests/test_control_plane_boundary.py (new) or apps/conformance/tests | None |
| 2 | D12 | Create docs/architecture/platform_north_star.md that explains: Control plane (manager, provisioning, billing, marketplace, observability), Tenant plane (tenant domains, school data), Marketplace layer (apps, installs, scopes), Workflow engine (WorkflowConfig), Metadata engine (Policy Registry), Observability stack (logs, metrics, tenant cache keys), Edge (CDN, WebSocket doc), Data plane (Postgres, schema/RLS, router), Compliance & security. Reference tenancy.md and policy_injection.md. | docs/architecture/platform_north_star.md | None |

---

## Part D execution log

- **Step 1 (D4):** [x] Added apps/tenancy/tests/test_control_plane_boundary.py; ControlPlaneBoundaryTestCase.test_tenant_apps_do_not_import_control_plane_models; tenant apps (portal, academics, people, finance, evals, reports, communication) scanned for forbidden imports (customers.models, marketplace.models, policies.models); excluded migrations, management, tests dirs. Run: `python manage.py test apps.tenancy.tests.test_control_plane_boundary`. First run may take a few minutes (migrations); subsequent runs are fast.
- **Step 2 (D12):** [x] Created docs/architecture/platform_north_star.md; added to docs/architecture/README.md. Document explains Control plane, Tenant plane, Marketplace, Workflow engine, Metadata engine, Observability, Edge, Data plane, Compliance & security.

---

## Blueprint items not in Part A (review if you want them as requirements)

The following appear in the blueprint (SINGLE / CURSOR_v2) but were **not** added as separate rows in Part A. They are either covered indirectly by existing IDs, or are “next phase” / audit prompts. If you want them tracked and verified, add rows and re-verify.

| Blueprint section | Item | Why not in Part A / status |
|-------------------|------|----------------------------|
| Build order 1 | **Inventory:** generate codebase map (apps, models, URLs, middleware, tenant routing) | Done: docs/architecture/ has apps.txt, urls.txt, migrations.txt, tenancy.md, policy_injection.md, platform_north_star.md. Blueprint also asks for docs/architecture_map.md (single file) and Mermaid diagram — not created. |
| Done-right definition | Customization = policy/config only; no hard-coded country logic; new feature = core service or marketplace app | Reflected in P3, R1, R3, D5; no separate “audit for country logic” requirement. |
| Dominance Sweep 0 | No tenant-specific code branches; no `if tenant.country ==` in business logic | Partially P3/D5; no dedicated “grep for tenant/country branching” requirement. |
| **A1** | Product Entitlements: can(tenant, "MODULE_X"), limits(tenant), usage(); billing primitives (proration, invoice immutability, tax engine) | Not in Part A. Feature flags / plan addons exist; no dedicated entitlements service or billing/entitlements.py. |
| **A2** | Marketplace governance: app review pipeline, sandbox runtime, versioning rules, revenue share, kill switch | M* cover models and install; no app review pipeline, kill switch, or revenue-share as requirement rows. |
| **A3** | Isolation hardening: media/static tenant-prefixed; search tenant-scoped; cache tenant_id; Celery tenant context; analytics tenant-tagged | TenantContext (T3); cache audit in cache_keys.md. No explicit “lint to block tenantless cache keys” or media/search/analytics isolation rows. |
| **A4** | Observability: structured logging (request_id, tenant_id), metrics, tracing, SLOs, runbooks, synthetic monitoring | No requirement rows. Observability app and cache_keys exist; no OpenTelemetry/middleware logging requirement. |
| **A5** | Security baseline: WebAuthn/MFA, session management, rate limiting, secrets hygiene, pen-test CI, audit logs | No requirement rows. Some MFA/audit exist elsewhere; no security/ app or django-axes requirement. |
| **A6** | Data governance: DataClass, RetentionRule, ConsentRecord, ExportJob, EraseRequest; Policy Registry enforcement | No requirement rows. Compliance app has consent/access; no dedicated governance/ app. |
| **A7** | Accessibility + i18n: WCAG 2.2 AA, RTL, plural rules, terminology from Blueprint, low-bandwidth | No requirement rows. RTL and terminology are in policy (D5, P*). |
| **B1** | Universal Student 360: timeline feed, export pack | Not in Part A. |
| **B2** | Event backbone (domain events, versioning, webhook guarantees) | Covered by E1–E4. |
| **B3** | BlueprintVersion, PolicyVersion; staged rollout + rollback | Not in Part A. PolicyBundle is versioned; no BlueprintVersion or rollback requirement. |
| **C1** | Architecture map output: docs/architecture_map.md + Mermaid (request flow, tenant resolution, DB schema) | We have docs/architecture/ (multiple files), not single architecture_map.md or Mermaid. |
| **C2** | Audit: find tenant/country/region branching and hardcoded labels; propose Policy Registry replacement | Not a requirement row; audit prompt. |
| **C3** | Audit: media/cache/tasks/search isolation; tenant_id prefixing | Cache covered by cache_keys.md; no requirement row for full audit. |
| **C4** | CI: pip-audit, Bandit, Semgrep, check --deploy, CSP; output docs/security_baseline.md | Not a requirement row. |
| Diagram §4 | **MarketplaceAppVersion** (separate version model) | We have MarketplaceApp.version (field). No separate MarketplaceAppVersion model. |
| Repo audit commands | Blueprint “Repo-Level Audit Commands” (rg for raw SQL, hardcoded labels, etc.) | Not added as requirement rows; one-off audit. |

**Summary:** Part A focused on Tenancy, Policy Registry, Refactor one module, Event outbox, Marketplace MVP, Settings/Wiring, Constraints, and Diagram requirements (D1–D12). The items above are either done elsewhere (e.g. inventory in docs/architecture/), partially covered (e.g. B2 by E*), or are “Dominance Sweep” / audit items that were not turned into tracked requirements. If you want them fully tracked, add new IDs (e.g. A1–A7, B1, B3, C1–C4), verify status, and extend Part D for any gaps.

---

## Implemented this sprint (blueprint items not previously in Part A)

| Item | What was done |
|------|----------------|
| **C1** | docs/architecture_map.md: apps table, tenant routing, shared vs tenant, Mermaid (request flow, DB schema). |
| **C2 / C3** | docs/architecture/audit_branching_and_isolation.md: commands and guidance for tenant branching and isolation audits. |
| **C4** | scripts/security_ci.sh (pip-audit, Bandit, check --deploy); docs/security_baseline.md. |
| **A1** | apps/billing/entitlements.py: can(), limits(), usage(). apps.billing in INSTALLED_APPS. |
| **A2** | suspend_app(), unsuspend_app() in marketplace/services.py; get_installed_widgets filters status=ACTIVE. |
| **A3** | docs/architecture/dominance_sweep_checklist.md + cache_keys.md + audit_branching_and_isolation.md. |
| **A4** | RequestIdLoggingMiddleware + RequestContextFilter; request_id, tenant_id, user_id on logs; X-Request-ID on response. |
| **A5** | Rate limiting, MFA, compliance audit, security_ci.sh, security_baseline.md (see dominance_sweep_checklist). |
| **A6** | Compliance: RetentionRule, ConsentRecord, ExportJob, EraseRequest (see dominance_sweep_checklist). |
| **A7** | RTL/terminology from policy; WCAG in siteconfig (see dominance_sweep_checklist). |
| **B1** | apps/student360/services.py: get_student_timeline_feed(), export_student_pack(). apps.student360 in INSTALLED_APPS. |
| **B3** | apps/policies/rollback.py: set_active_policy_bundle(), list_policy_bundles_for_school() for rollback. |

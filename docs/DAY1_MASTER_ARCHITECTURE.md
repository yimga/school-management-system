# Day 1 / Master architecture (world-class baseline)

Part 5 step 8. The "three-layer shield" and Day 1 development checklist.

## Three-layer shield

1. **Global Gateway (public)**  
   Public schema: tenant registry (Client, Domain), identity (User), School, SiteSettings, RegionConfig, compliance, observability. Marketing and signup live here. No tenant data.

2. **Isolated Tenant Fortress (per-schema)**  
   One PostgreSQL schema per school. All tenant-scoped tables (academics, people, finance, evals, reports, communication, analytics, payroll) live in that schema. Middleware sets `search_path` per request. **Never rely on tenant_id or RLS for isolation** — schema is the single source of truth.

3. **Intelligence/Analytics Mesh**  
   De-identified aggregate analytics; optional cross-tenant reporting with strict governance. Not implemented in full; document as roadmap.

## Day 1 components

| Component | Description | Status |
|-----------|-------------|--------|
| **Master Control** | Public schema for tenant registry, auth, subscription | ✅ (Client, Domain, School, SiteSettings) |
| **Tenant Provisioner** | OnboardingService creates schema and runs Master Table List per school | ✅ [apps/schools/onboarding_service.py](../apps/schools/onboarding_service.py) |
| **Schema-aware middleware** | Subdomain/slug → set search_path to tenant schema | ✅ TenantMainMiddleware, TenantSchemaSchoolBridgeMiddleware |
| **Security Sentinel** | Immutable audit trail (trigger-based) in each tenant schema | ✅ [AUDIT_TRAIL_TRIGGER_BASED.md](AUDIT_TRAIL_TRIGGER_BASED.md); TenantAuditLog + migration 0037 + attach_audit_triggers; PII masking in trigger |
| **Command Center UI** | Superadmin dashboard for health, toggles, tenant lifecycle | Partial (super_views, feature control); full GSOC God-View in roadmap |

## Three platform layers (plan 4.8)

| Layer | Description | Codebase refs |
|-------|-------------|----------------|
| **Marketing Engine** | Internet-facing site: hero, demo, trust signals, /discover/, /find/, signup | apps/schools/marketing_views.py, section8_views.py, config/public_urls.py |
| **Superadmin / Ecosystem Controller** | Global health, tenant lifecycle, financial command, shadow support, feature control | apps/siteconfig/views_feature_control.py, super_views, /super/, /siteconfig/ |
| **Tenant / White-Label Views** | School command center, localized workflows, tenant autonomy hub (backend + portal) | Tenant host routing; apps/portal, apps/backend; per-school branding |

Document and extend per blueprint; see RUNMYCAMPUS_SINGLE_PLAN_COMPLETE Part 4.8.

---

## Tie to existing docs

- **THREE_PLANS_EXECUTION_GUIDE** — execution order and dependencies.
- **KEY_MODULES_REFERENCE** — module map.
- **ALL_MODULES_DEPENDENCIES_AUTOMATION_GAPS** — automation and jobs.
- **MODULE_AUDIT_AND_IMPROVEMENT_PLAN** — checklist for audits.
- **RUNMYCAMPUS_SINGLE_PLAN_COMPLETE** — single source of truth for the roadmap.

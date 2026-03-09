# Prompt 6 — Final Platform Truth Audit Report

**Date:** 2026-03-06  
**Scope:** Brutal assessment — platform vs single-school vs hybrid  
**Non-negotiable:** Architectural risks must be addressed.

---

## 1. Verdict

**C) Hybrid transitional architecture.**

The codebase is not a single-school system extended with a second school; it has real multi-tenant structures (schema-per-tenant/RLS, host-based separation, control-plane decorators, tenant context in middleware and tasks). It is not yet a full Shopify/Salesforce/AWS-style platform: residual hardcoding (CMR/XAF/0-20), some governance gaps (pack versioning, regional config at scale), and the need to enforce tenant context in every new feature remain.

---

## 2. Platform maturity rating: 6–6.5 / 10

- **Identity:** RunMyCampus as platform brand; control plane (manager, /super/) and tenant plane (schools) are separated in code and URLconf.
- **Tenancy:** Real (schema or RLS); provisioning and lifecycle exist.
- **Governance:** Control-plane views, marketplace, migration cloud, registries, blueprints, policies, packs; gaps in versioning and regional scale.
- **Configuration:** Registries and runtime exist; hardcoding remains in finance, reports, evals, siteconfig (see Prompt 4).
- **Isolation:** Remediated (reports, evals task); get_solo blocked in tenant code.

---

## 3. Top architectural risks

1. **Hardcoded region/currency/grading** in tenant apps — blocks true global deployment.
2. **New code** — any new tenant view or task must enforce school/schema scope and avoid get_solo.
3. **Pack versioning and rollback** — needed for safe blueprint/policy updates at scale.
4. **Regional configuration** — 195-country support requires registry-driven behavior, not code defaults.

---

## 4. Top platform strengths

1. Host-based separation and `require_super_access_with_host` on all /super/ routes.
2. Schema-per-tenant (or RLS) and TenantContext; provisioning and tests.
3. Control-plane templates and docs (CONTROL_PLANE_TEMPLATES.md, GOVERNANCE_*).
4. Celery tasks use `_run_with_tenant_context` or schema_context; evals task fixed to support tenant context.
5. get_solo restricted to allowlist; tenant code uses get_effective_site_settings / tenant_runtime.

---

## 5. Roadmap to world-class platform

1. **Eliminate hardcoding:** Move CMR/XAF/0-20/Africa/Douala to registry/blueprint/env (Prompt 4 plan).
2. **Enforce tenant context:** All new tenant-app queries and tasks must be school/schema-scoped; keep lint/tests.
3. **Governance:** Pack versioning, runbooks, regional config from registry.
4. **Observability:** SLO/health dashboards if required for production.
5. **Global education:** Grading, calendar, compliance, reporting configurable per region (Prompt 7).

---

**Next:** Proceed to Prompt 7 (Global Education Compatibility).

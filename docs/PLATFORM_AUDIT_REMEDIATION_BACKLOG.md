# Platform Audit Remediation Backlog

**Date:** 2026-03-08  
**Source:** PLATFORM_TRANSITION_AUDIT_REPORT.md, MODEL_TO_CANONICAL_MAPPING_REPORT.md

Items that cannot be fully remediated in one pass are listed here with severity and next step. All items are non-negotiable for full platform alignment; ownership and priority should be assigned.

---

## Critical

| Issue | Severity | Next step |
|-------|----------|-----------|
| Tenant-facing code uses `SiteSettings.get_solo()` (50+ call sites) | Critical | Classify SiteSettings fields; migrate tenant reads to request.tenant_runtime / policy / blueprint; add lint to block new tenant-facing get_solo(). |
| Tenant-app background tasks run without tenant context | Critical | Wrap analytics, communication, and other tenant-app tasks with tenant schema/context; add tests. |

---

## High

| Issue | Severity | Next step |
|-------|----------|-----------|
| Superadmin vs tenant boundary: shared layouts and weak permission checks | High | Enforce host/surface in decorators; use control-plane role for manager views; split control-plane vs tenant templates. |
| Hardcoded sidebar, dashboard widgets, provider lists | High | Move to registries, dashboard packs, provider registry; document target layer per item. |
| Queries in tenant apps may lack tenant filter | High | Audit all tenant-app ORM usage; add tenant/school filter where missing; document. |
| School vs Tenant vs Campus not clearly separated per canonical map | High | Refactor per MODEL_TO_CANONICAL_MAPPING_REPORT; rename/split as needed. |

---

## Medium

| Issue | Severity | Next step |
|-------|----------|-----------|
| Analytics/reporting may aggregate across tenants | Medium | Audit analytics and reporting code; enforce tenant scope; add tests. |
| Search/export may leak cross-tenant data | Medium | Audit search and export paths; enforce tenant isolation. |
| Missing canonical objects (Migration Profile, Provider Registry Entry, Workflow Run, etc.) | Medium | Implement or extend per Canonical Data Object Map; see Part 3 of model report. |
| Pack versioning and rollback for blueprints/policies | Medium | Design and implement versioning; add rollback. |
| Platform-wide feature toggles (control-plane) | Medium | Add feature toggle layer for platform (not tenant) flags. |

---

## Lower

| Issue | Severity | Next step |
|-------|----------|-----------|
| Regional configuration for 195 countries from registry | Lower | Ensure all country/region behavior is registry-driven; remove hardcoding. |
| Migration cloud UI and runbooks | Lower | Implement migration cloud UI; document runbooks. |
| Observability/SLO for platform health | Lower | Add SLO dashboards and platform health monitoring. |
| Tenant lifecycle (suspend, archive) automated | Lower | Document and automate tenant lifecycle beyond provision. |

---

## Remediation completed in this pass (Phase 7)

- **Marketing platform refactor (Phases 1–6):** Dedicated marketing shell, content system, SEO, performance, conversion CTAs. Marketing does not rely on tenant SiteSettings for content; uses file-based content and brand registry where applicable.
- **Audit reports persisted:** PLATFORM_TRANSITION_AUDIT_REPORT.md, MODEL_TO_CANONICAL_MAPPING_REPORT.md, and this backlog created.

---

## Ownership and review

Assign owner and target sprint for each backlog item. Review after each major refactor; re-run transition and model audits to update reports and this backlog.

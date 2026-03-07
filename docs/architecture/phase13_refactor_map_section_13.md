# Phase 13 — Technical Refactor Map (Section 13)

Verification that the refactor map and architecture map pack are produced and present. Section 13 checklist is already satisfied; this doc records where each deliverable lives.

---

## 13.1 — Full refactor map

**Requirement:** Every Django app, key models, model dependencies, routing and tenancy flow, config/policy/workflow/dashboard injection points, hardcoding hotspots, where to refactor first, what stays, what must split.

| Deliverable | Location |
|-------------|----------|
| Refactor map / checklist | `docs/architecture/RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md` (Sections 1–31, Part F directive) |
| Findings / hotspots | `docs/architecture/FINDINGS_REPO_AUDIT.md` |
| Policy injection points | `docs/architecture/policy_injection.md`; `section_23_injection_verification.md` |
| Module architecture | `docs/architecture/phase11_module_architecture_section_9.md` |
| Configurability by module | `docs/architecture/phase12_platform_configurability_section_10.md` |

---

## 13.2 — Architecture map pack

| Item | Location |
|------|----------|
| apps.txt | `docs/architecture/apps.txt` (or equivalent in docs) |
| urls.txt | `docs/architecture/urls.txt` |
| migrations.txt | `docs/architecture/migrations.txt` |
| models.png | Optional by decision; not required for checklist. See RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md “Deferred and optional items register”. |
| tenancy.md | `docs/architecture/tenancy.md` |
| policy_injection.md | `docs/architecture/policy_injection.md` |

---

## 13.3 — Repo inventory commands and tenant routing doc

| Item | Location |
|------|----------|
| Tenant routing | `docs/architecture/tenancy.md`; `phase9_domain_and_routing.md`; `request_flow_tenant_resolution.mmd` |
| Repo inventory | Documented in main doc / FINDINGS_REPO_AUDIT; commands as needed |

---

## 13.4 — Mermaid diagram: request flow + tenant resolution + DB schema

| Item | Location |
|------|----------|
| Mermaid diagram | `docs/architecture/request_flow_tenant_resolution.mmd` |

---

## Checklist summary (Section 13)

| Id | Status |
|----|--------|
| 13.1 | [x] (this doc + main doc + FINDINGS_REPO_AUDIT.md) |
| 13.2 | [x] (apps.txt, urls.txt, migrations.txt, tenancy.md, policy_injection.md; models.png optional) |
| 13.3 | [x] |
| 13.4 | [x] (request_flow_tenant_resolution.mmd) |

**Reference:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md Section 13 checklist.

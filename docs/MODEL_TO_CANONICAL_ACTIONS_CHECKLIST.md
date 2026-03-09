# Model-to-Canonical mapping — actions checklist

**Purpose:** Track completion of actions from MODEL_TO_CANONICAL_MAPPING_REPORT and CANONICAL_OBJECTS_MAPPING. Updated as part of Platform Hardening remediation.

**Closure:** All actions are either Done, Verify (in runbooks), or Ongoing; "Deferred" and "Optional/future" entries are explicitly closed with reason per plan item 15 (no unassigned backlog).

**Non-negotiable:** Every item in this checklist is required. "Deferred" and "Optional/future" mean required with an explicit trigger (e.g. when refactoring people app); nothing is abandoned or "save for later."

---

## Refactor plan (from report)

| # | Action | Status | Notes |
|---|--------|--------|--------|
| 1 | Classify and split SiteSettings; stop tenant-facing get_solo(); route to tenant_runtime | **Done** | Items 1–2: runtime as authority; get_solo() reduced and allowlisted; tenant code uses get_effective_site_settings(request) / runtime. |
| 2 | Ensure all tenant-app tasks run with tenant context | **Verify** | Audit tasks/jobs for school/tenant context; fix where missing. Document in runbooks. |
| 3 | Rename/split School vs Tenant vs Campus per canonical map | **Done** | Item 4: SCHOOL_FIELD_RESPONSIBILITY_MAP.md; School identity vs config documented; Campus optional/future. |
| 4 | Align people models to Person + Role Assignment | **Required (trigger: people refactor)** | Single Person identity root and explicit Role Assignment — implement when refactoring people app. See CANONICAL_OBJECTS_MAPPING. |
| 5 | Add missing canonical objects (Migration Profile, Provider Registry Entry, Workflow Run) | **Done** | MigrationProfile, MigrationRun, WorkflowRunLog exist. Provider registry: INTEGRATION_CATALOG + ServiceIntegration + resolve_active_integration; governance in item 13. |
| 6 | Extract configurable behavior into registries/blueprints/policies; mark legacy | **Ongoing** | Items 1–5, 8, 13: runtime, blueprint, policy, provider registry are single path; legacy marked where needed. |

---

## Part 2 mapping table — status

| Current model / area | Action | Status |
|----------------------|--------|--------|
| Client, Domain | KEEP | Aligned. |
| School | KEEP BUT RENAME/SPLIT | Documented; settings/features read only via resolver/runtime. |
| SiteSettings | SPLIT/EXTRACT | Tenant-facing use removed from tenant path; allowlist documented. |
| people (Student, Staff…) | KEEP; align to Person | Required; Person as identity root when refactoring people app. |
| academics, finance, evals, PolicyBundle, Blueprint, marketplace | KEEP | Aligned. |
| SiteSettings (tenant use) | EXTRACT CONFIGURABLE | Done via runtime/blueprint. |

---

## Missing canonical objects (from report Part 3)

| Object | Status |
|--------|--------|
| Person (identity root) | Deferred; people app has StudentProfile, Staff, etc. |
| Campus | Optional/future; doc in SCHOOL_TENANT_CAMPUS_CANONICAL.md. |
| Role Assignment | Implicit in memberships; explicit model deferred. |
| App Installation with scopes | marketplace has installations; verify scopes in code. |
| Migration Profile | Implemented — MigrationProfile, MigrationRun. |
| Provider Registry Entry | Implemented — ServiceIntegration + INTEGRATION_CATALOG; governance doc. |
| Document Version / Generated Artifact | Required (future); clarify in reports if needed. |
| Custom Field Definition/Value | Required when productised. |
| Workflow Run | Implemented — WorkflowRunLog. |
| Guardian–Student Link normalization | Domain logic; no canonical model change required. |

---

## References

- `docs/MODEL_TO_CANONICAL_MAPPING_REPORT.md`
- `docs/CANONICAL_OBJECTS_MAPPING.md`
- `docs/SCHOOL_FIELD_RESPONSIBILITY_MAP.md`
- `docs/SITESETTINGS_GET_SOLO_ALLOWLIST.md`
- `docs/PROVIDER_REGISTRY_GOVERNANCE.md`

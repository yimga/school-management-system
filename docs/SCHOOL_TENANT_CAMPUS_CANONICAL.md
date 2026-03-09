# School, Tenant, and Campus — Canonical Mapping

**Purpose:** Clarify the canonical separation between **Tenant**, **School**, and **Campus** per the Model-to-Canonical Mapping Report. This doc is the single source of truth for naming and refactors.

---

## Canonical definitions

| Term | Definition | RunMyCampus mapping |
|------|------------|---------------------|
| **Tenant** | The organization that holds a contract with the platform; the unit of isolation and billing. | In RunMyCampus, **one School row = one Tenant**. The `School` model is the tenant entity (schema-per-tenant or RLS scoped by `school_id`). |
| **School** | The primary institution identity (name, slug, region, settings). May be the same as Tenant in single-school-per-tenant deployments. | **`schools.School`** — same as Tenant in current design. Use "School" in UI and APIs; "Tenant" in platform/control-plane and docs where isolation or billing is discussed. |
| **Campus** | A physical or logical branch of a Tenant (multi-campus). Optional; not all tenants have multiple campuses. | **Future:** When multi-campus is required, introduce a **Campus** model (FK to School) and scope branch-specific data (e.g. some reports, locations) by Campus. Today, all data is School-scoped; no Campus model yet. |

---

## Current codebase

- **`schools.School`** is the **Tenant** and the **School** (single institution per tenant). Docstring and control-plane code may refer to "tenant" (e.g. `request.school` = current tenant).
- **No separate Campus model.** If a school has multiple physical sites, they are not first-class entities; use `School.settings` or custom fields if needed until Campus is introduced.
- **Renames / splits:** No mandatory rename of `School` → `Tenant` in the DB; the canonical *concept* is "School = Tenant for RunMyCampus." New code and docs should use "School" for the entity and "tenant" when referring to isolation/billing/control-plane.

---

## Refactor checklist (from MODEL_TO_CANONICAL_MAPPING_REPORT)

- [x] Document School = Tenant; Campus = future.
- [ ] When adding multi-campus: add `Campus` model, FK to `School`; scope branch-specific features by Campus.
- [ ] Keep `School` as the main model name; use "tenant" in control-plane and isolation contexts only where it adds clarity.

---

**See also:** `MODEL_TO_CANONICAL_MAPPING_REPORT.md`, `PLATFORM_AUDIT_REMEDIATION_BACKLOG.md`.

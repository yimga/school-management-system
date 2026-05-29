# School, Tenant, and Campus — Canonical Mapping

**Purpose:** Clarify the canonical separation between **Tenant**, **School**, and **Campus** per the Model-to-Canonical Mapping Report. This doc is the single source of truth for naming and refactors.

---

## Canonical definitions

| Term | Definition | RunMyCampus mapping |
|------|------------|---------------------|
| **Tenant** | The organization that holds a contract with the platform; the unit of isolation and billing. | In RunMyCampus, **one School row = one Tenant**. The `School` model is the tenant entity (schema-per-tenant or RLS scoped by `school_id`). |
| **School** | The primary institution identity (name, slug, region, settings). May be the same as Tenant in single-school-per-tenant deployments. | **`schools.School`** — same as Tenant in current design. Use "School" in UI and APIs; "Tenant" in platform/control-plane and docs where isolation or billing is discussed. |
| **Campus** | A physical or logical branch within one Tenant (multi-campus). Optional; not all tenants have multiple campuses. | **`schoolops.Campus`** — FK to `School`; branch-scoped ops (transport, hostel, cafeteria assignments). Academics remain primarily School-scoped; campus features grow behind flags. **Organization overlay** (Phase 2) sits above Tenant, not replacing Campus. |

---

## Current codebase

- **`schools.School`** is the **Tenant** and the **School** (single institution per tenant). Docstring and control-plane code may refer to "tenant" (e.g. `request.school` = current tenant).
- **`schoolops.Campus`** exists — physical/logical branch under a School. See `apps/schoolops/models.py::Campus`.
- **Optional Organization** (Phase 2) groups multiple Schools for rollups; standalone schools keep `organization=null`.
- **Renames / splits:** No mandatory rename of `School` → `Tenant` in the DB; the canonical *concept* is "School = Tenant for RunMyCampus." New code and docs should use "School" for the entity and "tenant" when referring to isolation/billing/control-plane.

---

## Refactor checklist (from MODEL_TO_CANONICAL_MAPPING_REPORT)

- [x] Document School = Tenant; Campus = `schoolops.Campus` (implemented).
- [x] Organization overlay documented as Phase 2 optional layer above School.
- [ ] When deepening multi-campus: scope additional academics by Campus where product requires it.
- [ ] Keep `School` as the main model name; use "tenant" in control-plane and isolation contexts only where it adds clarity.

---

**See also:** `MODEL_TO_CANONICAL_MAPPING_REPORT.md`, `PLATFORM_AUDIT_REMEDIATION_BACKLOG.md`.

# Global Governance Mandate Crosswalk

Maps external global-governance audit prompts to RunMyCampus repo truth. **School = Tenant** remains the isolation boundary; optional `Organization` overlay ships Phase 2.

## Schema mapping

| External concept | RunMyCampus mapping | Status | Phase |
|------------------|---------------------|--------|-------|
| `organizations` (holding entity) | `apps/governance.Organization` + `OrgMembership` + `GovernanceNode` | **Implemented** | 2A–2C |
| `campus_nodes` + school tier | `School` tenant + `schoolops.Campus` + multicampus wedge surfaces | **Implemented** | 2–3 |
| `global_users` | `accounts.User` | **Implemented** | — |
| `user_context_profiles` | `SchoolContextProfile` + `SchoolMembership` + fast switch | **Implemented** | 3C |
| `staff_compliance_registry` | `apps/people/staff_compliance.py` + `StaffComplianceRecord` | **Implemented** | 4F |
| `class_schedules` + EXCLUDE | `ScheduleEntry` partial unique constraints + `instruction_day_ledger` | **Implemented** (discrete slots; gist EXCLUDE deferred) | 4E |

## Five vulnerability mandate (Phase 1 audit)

| # | Mandate | Evidence | Status | Phase |
|---|---------|----------|--------|-------|
| 1 | Polymorphic org hierarchy | `Organization`, `parent_school`, `mat_groups_sync`, MAT hub wedge 22 | **Implemented** | 2–6 |
| 2 | Multi-currency rollups | `regional_payment_profiles.json`, PSP dispatchers | Partial | 3C |
| 3 | Multi-context permissions | `SchoolMembership`, tenant switcher | Partial | 3C |
| 4 | Localized academic matrix | `terminology_service`, institution packs | Partial | 3–4 |
| 5 | Data sovereignty | `data_residency_onboarding`, `middleware_residency` | Partial | 3 + deploy |

## Seven global blind spots

| # | Blind spot | Repo today | Phase |
|---|------------|------------|-------|
| 1 | Non-linear calendars | Per-country `calendar_system` in seed packs | 3 |
| 2 | Polymorphic family graph | `StudentGuardian` + ReBAC | 3–4 |
| 3 | Offline-first PWA | `service-worker.js`, `OfflineSyncViewSet` | Extend (strong) |
| 4 | Multi-script names | `country_formats_service.py` name order | 3 |
| 5 | Geographic sovereignty | Residency middleware (enforce off by default) | 3 |
| 6 | Double-entry / mobile money | PSP scaffolds; no full school GL | 4 |
| 7 | Normalized grading | `GradeScaleRegistry`, `bulk_gradebook` | 3 |

## Anti-patterns (do not adopt)

- Replacing `School` tenant with `campus_nodes` as isolation boundary
- Mandatory org membership for standalone schools
- Single-database district models that collapse legal separation

## Proof

- Completion register: `docs/generated/global_governance_completion_register.json`
- Blind-spot verifier: `python scripts/verify_global_operational_blind_spots.py --allow-pending --write`

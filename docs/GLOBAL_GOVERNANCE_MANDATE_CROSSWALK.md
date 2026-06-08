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

## PROTOCOL SOVEREIGN-MAPPING-2026 (architecture overhaul prompt)

External “Sovereign Mapping” briefs map to **repo-owned programs** — not a single markdown plan file.

| Pasted target | Canonical plan / ledger | Primary artifacts | Status |
|---------------|-------------------------|-------------------|--------|
| Multi-click noise / attendance drudgery | **Zero-Friction OS** phases 1–2, 6 | `docs/generated/zero_friction_phase_completion_register.json`, `verify_zero_friction_journeys.py`, codemod waves 3–12 | **PARTIAL** (1627 templates still above friction threshold) |
| 44px header + `100dvh` shells | SOT batches **1623**, **1551**; Sovereign **P6** | `rmc-nav-sidebar.css`, `layout_personality_matrix.py`, `LAYOUT_OBSERVABILITY.md` | **DONE** (repo-scope) |
| 5-column grids + row drawer | Zero-Friction **phase 1** | `truncate_table_columns`, `rmc-portal-row-detail-drawer.js`, `data-rmc-table-5col` | **DONE** (161 templates adopted; burndown continues) |
| Cloud → Ollama → browser AI | Sovereign **P0–P2, P7**; `AI_DEPLOYMENT_POSTURE.md` | `services.ai_helpers`, `config/sovereign_platform_contract.json`, batches **1661–1670** | **DONE** (repo); browser SLM **blocked** until evidence |
| Postgres RLS + overflow sentinel | Sovereign **P4–P6**; tenant scanners | `app.current_school_id`, `scan_tenant_queryset_safety.py`, `rmc-layout-health-sentinel.js` | **PARTIAL** (RLS live CI deploy-gated) |
| **Comprehension / info tags (500X + 50X routes)** | SOT batch **1254** + commit `d5ac435d` + **50X routes** | `ui_field_help_platform_500x.py` (676 keys), `ui_route_help_sovereign_50x.py` (≥50 routes), `rmc_page_explain_strip.html`, `verify_info_tag_coverage.py` | **DONE** (repo-scope) |

**Cursor plans (supporting, not duplicate SOT):**

- [`.cursor/plans/global_governance_audit_582fd47d.plan.md`](../.cursor/plans/global_governance_audit_582fd47d.plan.md) — 249-country governance (Phase 0 todos pending)
- [`.cursor/plans/world_engine_execution_directive_26f59778.plan.md`](../.cursor/plans/world_engine_execution_directive_26f59778.plan.md) — scalability / three realms
- [`config/sovereign_platform_contract.json`](../config/sovereign_platform_contract.json) — reject list for anti-patterns in the pasted prompt

**Anti-patterns from the pasted prompt (rejected per batch 1662):** global ResizeObserver font compression, parallel `glocal_kernel`, autonomous AI grading, universal LWW merge, transaction pooling without session endpoint.

## Proof

- Completion register: `docs/generated/global_governance_completion_register.json`
- Blind-spot verifier: `python scripts/verify_global_operational_blind_spots.py --allow-pending --write`
- Info-tag gate: `python scripts/verify_info_tag_coverage.py` → `INFO_TAG_COVERAGE_PASS`
- Zero-Friction bundle: `python scripts/verify_zero_friction_phases_0_8.py`

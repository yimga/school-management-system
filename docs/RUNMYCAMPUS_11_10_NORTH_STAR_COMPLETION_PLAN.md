# RunMyCampus 11/10 North-Star Completion Plan

This is the canonical implementation plan for the current platform-hardening and platform-productization workstream.

## STATUS: COMPLETE (2026-03-12)

This plan is closed. Implementation and verification evidence is tracked in code plus the audit/closure artifacts below; no backlog remains tracked in this file.

**For all agents:** This is the **named North Star plan**; the **single execution source of truth** for ongoing work is [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Before starting any work, check [docs_truth_ledger.md](docs_truth_ledger.md) and [NEXT_50_EXECUTION_STEPS.md](NEXT_50_EXECUTION_STEPS.md); backlog and closure: [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md). Do not create new overlapping strategy or roadmap files.

- Canonical execution ledger + final scoring gate: `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` (Satisfied: 2026-03-12)
- Closure (no-backlog): `docs/RUNMYCAMPUS_AUDIT_PLAN_COMPLETE_NO_BACKLOG.md` (2026-03-08)
- Roadmap/optional closure: `docs/architecture/ROADMAP_AND_OPTIONAL_CLOSURE.md`
- Roadmap due-today evidence: `docs/architecture/ROADMAP_DUE_TODAY.md` and `/api/roadmap/*`
- Final gap closure checklist: `docs/RUNMYCAMPUS_FINAL_UNADDRESSED_GAPS_CHECKLIST.md`

## Authoritative target

- Working repo: `beta/school-management-system`
- Goal: move RunMyCampus from transitional multi-tenant platform to 9.5+/10 across architecture, runtime, security, UX, onboarding, marketplace, packs, and control plane
- Rule: no deferred placeholders, no half-complete migrations, no permanent dual-path legacy ownership
- Architecture law + Studio/toolsets (see `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` sections 3-5): bounded contexts, runtime-as-law, metadata-first

## Active execution phases (closed)

### Phase 1. Hard freeze, ownership map, deletion rules
- [x] Freeze new tenant-facing business logic in `siteconfig`
- [x] Inventory `SiteSettings`, `get_solo()`, `except Exception`, `cursor.execute()`, `csrf_exempt`, `AllowAny`, `print()`, `gilead` residue, management commands, and outdated docs
- [x] Assign each legacy config behavior to one bounded-context owner or delete it

### Phase 2. Security, hygiene, and trust hardening
- [x] Remove client-facing AI secret exposure
- [x] Review all public/exempt endpoints
- [x] Reduce blanket exception handling in sensitive modules
- [x] Audit non-migration raw SQL
- [x] Remove runtime-visible Gilead residue
- [x] Replace `print()` with structured logging and correct outdated documentation

### Phase 3. Make runtime the only legal tenant behavior engine
- [x] Standardize runtime precedence
- [x] Route tenant behavior through runtime resolvers
- [x] Expand runtime inspection
- [x] Enforce control-plane vs application-plane boundaries
- [x] Add CI/lint gates against legacy regressions

### Phase 4. Complete the core toolsets
- [x] Theme & Experience
- [x] Feature Control
- [x] Report Library
- [x] Document Library
- [x] Design Studio
- [x] Live Previews
- [x] Workflows
- [x] AI and API usage
- [x] System Configuration / SiteSettings
- [x] Studio OS + toolset unification (single Studio shell + redirects)

### Phase 5. Productization and market-gap closure
- [x] Setup Studio as the mandatory onboarding spine
- [x] Premium marketplace listing/install model
- [x] First-party ecosystem seeding
- [x] Distinct role homes and dashboards
- [x] Stronger family/mobile and district control plane
- [x] Proof-rich marketing front

### Phase 6. Verification, release gates, and re-audit
- [x] Test gates
- [x] Operational gates
- [x] Codebase gates
- [x] Re-score all platform areas to 9.5+/10
- [x] Final benchmark delta report

## Operational sources of truth

The implementation is being driven alongside these generated and audited artifacts:

- `docs/generated/platform_inventory.md`
- `docs/generated/platform_inventory.json`
- `apps/siteconfig/domain_ownership.py`
- `docs/security/SITESETTINGS_INVENTORY.md`
- `docs/SITECONFIG_OWNERSHIP_MIGRATION.md`
- `docs/SITECONFIG_DECOMPOSITION_PLAN.md`
- `scripts/generate_platform_inventory.py`
- `scripts/lint_tenant_settings.py`
- `scripts/lint_csrf_exempt_usage.py`
- `scripts/lint_allow_any_usage.py`
- `scripts/lint_gilead_residue.py`

## Current execution note

This file is the canonical named plan. Progress is implemented directly in code plus the inventories and audit artifacts listed above.

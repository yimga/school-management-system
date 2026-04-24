# N/A Register — Path to 100%

**Purpose:** Items from [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md) that are not implemented in the initial run are documented here with owner and date. No item remains without a decision. **Consolidated status and "what's left" tracking:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11.4.

**Default N/A:** owner: **product**; date: **2026-03-12**; reason: **Deferred to backlog; implement per PATH_TO_100_PERCENT_EXECUTION_PLAN when prioritized.**

---

## Phase III — App-by-app (§6)

| SOT ref | Item | N/A |
|---------|------|-----|
| §6.1 | Migrate ownership | DONE — next batch in domain_ownership §5; incremental. |
| §6.1 | Delete legacy behavior paths | DONE — LEGACY_PATH_INVENTORY + SUBTRACTIVE_CLEANUP; `ensure_superadmin` = thin alias to `ensure_superuser` (inventory §2). |
| §6.1 | Replace giant admin pages with bounded consoles | DONE — Configuration Control Center console (studio_os:system_config_console) + Control rail. |
| §6.2 | Enforce runtime everywhere | DONE — lint_tenant_settings pass; runtime-only in tenant paths. |
| §6.2 | Add runtime tracing | DONE — runtime_resolution_complete in runtime_resolver (DEBUG log). |
| §6.2 | Eliminate fallback bypasses | DONE — no get_solo in tenant apps; allowlist documented. |
| §6.3 | Add pack provenance | **DONE** — EntityCatalogEntry.source_pack_id, source_pack_version; migration 0008; search API exposes. |
| §6.4 | Partial failure handling | DONE — mid-apply exception → atomic rollback + changelog failed; package_engine_ledger. |
| §6.5 | Complete Launch Studio flow | DONE — launch_studio_checklist all 10 items; staging verification optional. |
| §6.6 | Absorb real ownership from siteconfig | product 2026-03-12 — N/A; see N/A_BLOCKERS_AND_RESOLUTION.md. |
| §6.6 | Add previews/compare/rollback | **DONE** — studio_os:experience_compare + studio_os:rollback; SOT §6.6 [x]; **§11.4 batch 949** — PATH §6.6 III.11 inventory + `test_batch949_path_iii11_compare_contract`, `test_batch949_experience_compare_view` (+ `test_experience_rollback`, `packages.tests.test_experience_packs`). |
| §6.6 | Purge Gilead theme defaults | DONE — 0155; lint_gilead_residue. |
| §6.12 | Reduce raw SQL; Harden routes; Clarify school vs platform | DONE — raw SQL in repos only; public_endpoint_audit; schools_control_plane_boundary.md. |
| §6.7 | Blueprint owner; Connect setup/registries; preview/sandbox | DONE (owner+connect); N/A preview/sandbox product. |
| §6.8 | Hard registry; Runtime consumption; Why-enabled; Marketplace | DONE (runtime + why-enabled); N/A registry + marketplace product. |
| §6.9 | Central to setup; Registry UI | DONE (central); N/A registry UI product. |
| §6.10 | Richer metadata; Previews; Trust; Scope | DONE (richer metadata); N/A rest product. |
| §6.11–§6.24 | Policies (diff/impact/sandbox/graph), accounts onboarding, portal (Experience Studio done; doc/action N/A), finance (raw SQL done; workflows/analytics N/A), academics/people/student360/reports/automation/communication/analytics/observability/api | All addressed: DONE where implemented; N/A product 2026-03-12 where deferred; see SOT §6.11–6.24. |

---

## Phase IV — Toolset (§4.5, §5)

| SOT ref | Item | N/A |
|---------|------|-----|
| §4.5 | select plan (when productized) | product 2026-03-12 — N/A until plans productized |
| §5.1 | Move ownership; Unify visual systems | product 2026-03-12 |
| §5.2 | Convert toggles to registry; owner/expiry/source/scope | **DONE** — owner/source/scope/expiry on Definition/State; migration 0158; see N/A_BLOCKERS_AND_RESOLUTION.md "Resolved". |
| §5.3 | Report Platform; style inheritance/versioning | product 2026-03-12 |
| §5.4 | Document & Compliance Platform | product 2026-03-12 |
| §5.5 | Design Studio split, layout, section/block, preview, versioning, publish/rollback | product 2026-03-12 |
| §5.7 | Workflows simulation, visual builder, AI, dependency, conflict, staged, replay, health | product 2026-03-12 |
| §5.8 | AI permissions/audit, Use AI, API Center governance, contract tests | product 2026-03-12 |
| §5.9 | Total decomposition; Reclassify; preview/diff/rollback | product 2026-03-12 |

---

## Phase V — §7 seeding, Phase H manual

| SOT ref | Item | N/A |
|---------|------|-----|
| §7 | Minimum targets + completion gate | **DONE** — MARKETPLACE_SEED_TARGETS §2–§3; 27/25/30/21/15; test_marketplace_catalog_minimums; marketplace UI Install/Preview/Rollback |
| §11 Phase H | Go through entire codebase (links, UX, responsive, framing) | product 2026-03-12 — phase_h_audit + run_phase_h_verification.sh automate slice |
| §11 Phase H | Ensure after deployment changes visibly seen | product 2026-03-12 — RELEASE_CHECKLIST staging when deploying |
| §11 Phase H | Run full test suite and smoke/E2E | product 2026-03-12 — pre_deploy_gate + run_phase_h_verification in place |

---

*Cross-reference: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11.2.*

# Remaining Work — Track and Assign

**Purpose:** Single list of work still open after 9.5/10 completion. Every row is **Done** or **Closed (Phase 10 backlog)**. Nothing is left open on the table.

**9.5 bar:** All phases 0–8 and Final Gaps are Done in this ledger. Items below were Path-to-10 or siteconfig migration; each is either completed (Done) or closed and tracked in `docs/PHASE_10_BACKLOG.md`.

**§12 authority:** **§12 engineering gate MET** per [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) **§0** / **§11.4**; see [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) §6.3. This file tracks **residual** / Phase 10 items—not gate re-proofs.

---

## 1. Siteconfig ownership migration

**Source:** `docs/SITECONFIG_OWNERSHIP_MIGRATION.md`

| # | Task | Owner | Status | Note |
|---|------|--------|--------|------|
| 1.1 | Identify owned models: for each model still in siteconfig, assign target bounded context | — | Closed (Phase 10) | See PHASE_10_BACKLOG.md |
| 1.2 | State-safe migrations: Django migrations; backfill; switch reads to resolver; deprecate direct SiteSettings | — | Closed (Phase 10) | See PHASE_10_BACKLOG.md |
| 1.3 | Delete legacy paths: remove deprecated accessors and old tables/columns; enforce via CI | — | Closed (Phase 10) | See PHASE_10_BACKLOG.md |
| 1.4 | Deprecation markers: add `# DEPRECATED: use …` and removal date on remaining legacy access paths | — | **Done** | SiteSettings class and migration plan doc have deprecation; Phase 2 note in siteconfig/models.py |

---

## 2. Path-to-10 — Architecture

| # | Task | Owner | Status | Note |
|---|------|--------|--------|------|
| 2.1 | Giant-file decomposition: split six target files by bounded domain; enforce file-line thresholds in CI | — | Closed (Phase 10) | See PHASE_10_BACKLOG.md |

---

## 3. Path-to-10 — Runtime & multitenancy

| # | Task | Owner | Status | Note |
|---|------|--------|--------|------|
| 3.1 | Governor limits enforcement: wire real usage counters; enforce limits; expose in runtime inspector | — | Closed (Phase 10) | Limits defined and visible in inspector; enforcement in PHASE_10_BACKLOG.md |

---

## 4. Path-to-10 — Event & orchestration

| # | Task | Owner | Status | Note |
|---|------|--------|--------|------|
| 4.1 | Orchestration layer: long-running process support with state, retries, compensation, operator workbench | — | Closed (Phase 10) | See PHASE_10_BACKLOG.md |

---

## 5. Path-to-10 — UX

| # | Task | Owner | Status | Note |
|---|------|--------|--------|------|
| 5.1 | Apply empty-state component everywhere: catalog, workbench, list pages | — | **Done** | Component enhanced (purpose, primary + secondary CTA, demo_url); used on list/catalog pages; control-plane minimal cp-empty-state retained for operator panels |

---

## 6. Path-to-10 — Performance

| # | Task | Owner | Status | Note |
|---|------|--------|--------|------|
| 6.1 | Performance budget enforcement: script to run smoke requests and fail/warn when budgets exceeded | — | **Done** | scripts/check_performance_budgets.py added; PERF_BUDGET_STRICT=1 or --warn-only; see docs/PERFORMANCE_BUDGETS.md |

---

## 7. Path-to-10 — Marketing

| # | Task | Owner | Status | Note |
|---|------|--------|--------|------|
| 7.1 | Category-grade AI visuals: ship AI-generated hero/videos; integrate into marketing | — | Closed (Phase 10) | See PHASE_10_BACKLOG.md |

---

## 8. Path-to-10 — Developer platform

| # | Task | Owner | Status | Note |
|---|------|--------|--------|------|
| 8.1 | External dev platform: API portal, webhooks, SDKs, certification, partner sandbox | — | Closed (Phase 10) | See PHASE_10_BACKLOG.md |

---

## 9. Path-to-10 — Governance

| # | Task | Owner | Status | Note |
|---|------|--------|--------|------|
| 9.1 | Management command rationalization: classify commands; delete obsolete; document; expose ops in UI | — | **Done** | docs/management_commands_index.md added (all commands classified by app/category); delete obsolete and control-plane UI in PHASE_10_BACKLOG |

---

## 10. Path-to-10 — Toolsets

| # | Task | Owner | Status | Note |
|---|------|--------|--------|------|
| 10.1 | Theme & Experience: ExperiencePack; runtime-only resolution; compare/rollback | — | Closed (Phase 10) | See PHASE_10_BACKLOG.md |
| 10.2 | Feature Control: single registry with expiry; "why this feature is on" in inspector | — | Closed (Phase 10) | See PHASE_10_BACKLOG.md |
| 10.3 | Report Library: ReportPack; preview with sample data; dependency mapping | — | Closed (Phase 10) | See PHASE_10_BACKLOG.md |
| 10.4 | Document Library: lifecycle states; retention; document packs; search | — | Closed (Phase 10) | See PHASE_10_BACKLOG.md |
| 10.5 | Design Studio: split document vs experience; layout metadata and builder | — | Closed (Phase 10) | See PHASE_10_BACKLOG.md |
| 10.6 | Live Previews: central preview service; side-by-side; preview by role/device/tenant | — | Closed (Phase 10) | See PHASE_10_BACKLOG.md |
| 10.7 | Workflows: simulation with impact counts; marketplace cards; versioning and replay | — | Closed (Phase 10) | See PHASE_10_BACKLOG.md |
| 10.8 | AI & API: API contracts and contract tests; AI action audit trail | — | Closed (Phase 10) | See PHASE_10_BACKLOG.md |
| 10.9 | Configuration Control Center: migrate get_solo to runtime; shrink allowlist to zero | — | Closed (Phase 10) | See PHASE_10_BACKLOG.md |

---

## Summary

- **Done (completed in this pass):** 1.4 (deprecation markers), 5.1 (empty-state component), 6.1 (performance budget script), 9.1 (management commands index).
- **Closed (Phase 10 backlog):** All other rows. Implementation tracked in **`docs/PHASE_10_BACKLOG.md`**.
- **Nothing left open:** Every row has Status = Done or Closed (Phase 10).

---

## How to use this file

- **When implementing a Phase 10 item:** Move it from PHASE_10_BACKLOG to a "Done" row here (or add a completion note in PHASE_10_BACKLOG and reference it here).
- **Single source of truth for completion:** `docs/MASTER_PLATFORM_CHECKLIST.md`.

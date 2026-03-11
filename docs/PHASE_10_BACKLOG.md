# Phase 10 Backlog

**Purpose:** Work closed from the REMAINING_WORK table and tracked here for future implementation. Nothing in this file is required for 9.5/10; all items are Path-to-10 (to reach 10/10) or siteconfig migration completion.

**Rule:** When an item is implemented, move it to "Done" in this file and add a one-line note; optionally remove from this backlog once shipped.

---

## Siteconfig ownership migration

- **1.1** Identify owned models: assign each siteconfig model (SiteSettings, ThemePack, FeatureControlAudit, etc.) to target bounded context.
- **1.2** State-safe migrations: Django migrations to move tables/FKs; backfill; switch reads to resolver; deprecate direct SiteSettings for tenant behavior.
- **1.3** Delete legacy paths: remove deprecated accessors and old tables/columns; enforce via CI.

## Architecture

- **2.1** Giant-file decomposition: split siteconfig/models.py, accounts/views.py, schools/super_views.py, portal/views.py, finance/views.py, api/views_v1.py; enforce file-line thresholds in CI.

## Runtime & multitenancy

- **3.1** Governor limits enforcement: wire real usage counters; enforce limits in code; expose in runtime inspector.

## Event & orchestration

- **4.1** Orchestration layer: long-running process support (admissions, re-enrollment, migration, fee follow-up, approval chains) with state, retries, compensation, SLA visibility, operator workbench.

## UX

- **5.1** Apply empty-state component to all catalog/workbench/list pages (component done; rollout incremental).

## Marketing

- **7.1** Category-grade AI visuals: ship AI-generated hero images/videos; migration/setup/ecosystem visuals; integrate into marketing; keep asset governance.

## Developer platform

- **8.1** External dev platform: public API portal (docs, keys, quotas); webhook docs and subscription UI; SDKs; app certification; partner sandbox and scope review.

## Governance

- **9.1** Management command rationalization: delete obsolete commands; document and own operational commands; expose critical ops via control-plane UI (index done: docs/management_commands_index.md).

## Toolsets

- **10.1** Theme & Experience: ExperiencePack as packageable unit; runtime-only theme resolution; compare/rollback.
- **10.2** Feature Control: single capability registry with expiry; surface "why this feature is on" in runtime inspector.
- **10.3** Report Library: ReportPack model; preview with seeded sample data; dependency mapping.
- **10.4** Document Library: lifecycle states; retention rules; document packs; search/indexing.
- **10.5** Design Studio: split document vs experience design; layout metadata and layout builder.
- **10.6** Live Previews: central preview service; side-by-side before/after; preview by role/device/tenant.
- **10.7** Workflows: simulation with impact counts; workflow marketplace cards; versioning and replay.
- **10.8** AI & API: API contracts and contract tests; AI action audit trail.
- **10.9** System Config: migrate remaining get_solo() to runtime; shrink allowlist toward zero; CI fails on new tenant-facing get_solo.

---

**Single source of truth for completion:** `docs/MASTER_PLATFORM_CHECKLIST.md`. This backlog is for tracking only.

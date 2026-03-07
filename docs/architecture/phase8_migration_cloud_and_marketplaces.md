# Phase 8 — Migration Cloud and Marketplaces

Consolidated status for Section 12 Phases 5–6, Section 11 (migration cloud, blueprint marketplace), Section 29.6, 29.10. **Migration cloud and marketplaces are implemented;** deferred sub-items are documented below.

---

## Migration cloud (11.1, 12.5, 29.6)

| Requirement | Status | Where |
|-------------|--------|--------|
| **Import studio** | Done | `accounts.migration_wizard`: upload CSV → map columns → preview → run. Backed by student bulk-commit and `evals.importers.apply_import` (grades). |
| **Field mapping engine** | Done | Session-stored mapping in wizard; POST sends mapping JSON; rows transformed before backend. |
| **Dry-run validator** | Done | "Validate only (dry run)" runs validation/simulation (no DB writes); returns scorecard (would create, would update, errors). `run_dry_run()` in accounts.migration_services; evals.dry_run_grade_import. |
| **Migration scorecard** | Done | MigrationRun stores row_count, created_count, updated_count, error_count, status, execution_summary, started_at, completed_at. Displayed in wizard. |
| **Parity checker** | Done | `compute_parity(migration_run)` compares row_count to created + updated + error; surfaced in scorecard/admin. |
| **Rollback** | Deferred | Store enough info to revert last run; UI to trigger rollback (later). |
| **Legacy data cleaner** | Deferred | Broader tooling for legacy schema migration; backfill commands used where needed. |
| **Read-only legacy view** | Deferred | Separate feature for viewing legacy data read-only. |
| **Rollback-safe cutover / post-migration exception queue** (29.6) | Deferred | Document when cutover and exception queue are added. |

**Touchpoints:** `apps/accounts/views.migration_wizard`, `apps/accounts/migration_services`, `apps/automation/models.MigrationRun`, `apps/evals/importers`.  
**Reference:** `docs/architecture/phase5_migration_cloud.md`.

---

## Blueprint marketplace (11.2, 12.6)

| Requirement | Status | Where |
|-------------|--------|--------|
| **Blueprint packs (by country/region/level)** | Done | BlueprintPack: slug, name, description, category, policy_snapshot, version, is_active, country_code, metadata. Manager UI lists active packs. |
| **Selection/apply for tenants** | Done | Manager route `super:blueprint_marketplace`; form select school + pack; POST apply. `apply_blueprint_pack(school, pack, applied_by)` creates PolicyBundle, sets TenantBlueprint.active_bundle, invalidate_policy_cache. |
| **Preview** | Done | `preview_blueprint_pack(school, pack)` in blueprint_services; used in marketplace view. |
| **Versioning and compatibility** | Partial | BlueprintPack has version field; tenant-facing "Update bundle" and compatibility matrix deferred (phase6_marketplace.md). |
| **Tenant-facing "Get blueprints"** | Deferred | Currently manager-only; optional tenant backend entry later. |

**Touchpoints:** `apps.policies.models.BlueprintPack`, `apps.policies.blueprint_services.apply_blueprint_pack`, `apps.marketplace.views.blueprint_marketplace`, `super:marketplace/blueprints/`.  
**Reference:** `docs/architecture/phase6_marketplace.md`.

---

## App marketplace (12.6, 25.2)

| Requirement | Status | Where |
|-------------|--------|--------|
| **App showcase / catalog** | Done | Manager route `super:app_catalog`; lists installable listings (approved, not kill-switched). Public page `/app-marketplace/` (Section 11.5). |
| **Install pipeline** | Done | `install_app(school, app, installed_by=..., config=..., run_schema_patches=True)`: creates AppInstallation, runs schema patches when manifest has migrations_app/schema_patch_app, logs audit. |
| **Schema patch** | Done | `run_schema_patches_for_installation(installation)`: runs migrate for app_label from manifest; tenant schema context in schema-per-tenant; THIRD_PARTY_SCHEMA_PATCH_ALLOWLIST for third-party. |
| **Widgets** | Done | AppInstallation.widget_config from app.manifest["widgets"]; get_installed_widgets filters by school and ACTIVE status. |
| **Billing** | Partial | Revenue share: `schedule_publisher_revenue_share_payout`; tenant app billing (per-school charge for app) can be wired to billing module. |
| **Permission model** | Done | Listing status (APPROVED, etc.); security/certification review; kill_switch_active; install checks via _assert_app_installable. |
| **Audit** | Done | AppAuditLog: install, uninstall, suspend, unsuspend, schema_patch; actor and payload. |
| **Governance (25.2)** | Done | MarketplaceReview (listing, security, certification, version); governance console; AppAuditLog. |

**Touchpoints:** `apps.marketplace.services` (install_app, uninstall_app, run_schema_patches_for_installation, AppAuditLog), `apps.marketplace.views` (app_catalog, governance_console), `super:marketplace/apps/`, `super:marketplace/`.  
**Reference:** `docs/architecture/section_25_current_state.md` (25.2), `docs/architecture/phase6_marketplace.md`.

---

## Checklist updates (Phase 8)

- **11.1 (Migration cloud):** Implemented; rollback, legacy cleaner, read-only legacy view deferred (phase5_migration_cloud.md, this doc).
- **11.2 (Blueprint marketplace):** Implemented; pack versioning/tenant-facing optional (phase6_marketplace.md, this doc).
- **12.5 (Phase 5):** Implemented (phase5_migration_cloud.md).
- **12.6 (Phase 6):** Implemented (phase6_marketplace.md, this doc).
- **25.2 (Marketplace governance):** App review, permission scopes, data access logs (AppAuditLog), kill switch (suspend_app); section_25_current_state.md.
- **29.6 (Migration engine):** Import cockpit, mapping, dry run, parity done; rollback-safe cutover and post-migration exception queue deferred (this doc).
- **29.10 (Commercial platform):** Self-serve trials, quote-to-contract, partner tooling, migration sales calculator, in-app upgrade — separate roadmap; marketplace install/billing support present.

---

## Implementation note

**Migration cloud and marketplaces are no longer "deferred" as a whole.** Core migration cloud (import studio, field mapping, dry-run, scorecard, parity) and core marketplaces (blueprint packs + apply, app catalog + install pipeline with schema patch, widgets, audit, governance) are in place. Deferred items: migration rollback UI, legacy data cleaner, read-only legacy view; blueprint pack versioning/upgrade UX; optional tenant-facing blueprint/app discovery; full tenant app billing wiring and 29.10 commercial features.

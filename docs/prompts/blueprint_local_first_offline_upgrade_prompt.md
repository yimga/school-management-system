# RunMyCampus Blueprint Local-First Offline Upgrade Prompt

## Objective

Upgrade Blueprint modules into the tenant-safe local-first operating plan for each school. Preserve the existing Blueprint contracts, preview/apply/rollback engines, audit trail, idempotency, package integration, and tenant/operator separation. Do not rebuild the system. Adapt the current platform so every tenant-safe Blueprint can prove what works online, offline, during degraded connectivity, and after rollback.

Blueprints must support real school nuance. A tenant may need a base school model plus regional, curriculum, bilingual, boarding, vocational/technical, and low-connectivity overlays. The implementation must make those combinations explicit, previewable, tenant-safe, and reversible.

## Non-Negotiables

- Audit before code changes. Do not assume coverage.
- Tenant pages must only show tenant-safe Blueprint controls. Operator-only Blueprint controls remain hidden.
- No tenant Blueprint path may redirect to `/super/` or operator `/admin/`.
- No tenant Launch or Studio CTA may route school/region configuration to the backend dashboard when a tenant configuration destination exists.
- Offline-first claims must be backed by a manifest and proof, not marketing copy.
- Keep local/dev and school LAN profiles free of mandatory proprietary SaaS.
- Preserve existing package preview/apply/rollback behavior and idempotency.
- External dependencies must be visible as blockers or manual fallback states.
- App catalog recommendations must remain tenant-scoped and must never expose platform-only install controls.

## Current Reality To Start From

- Runtime Blueprint contracts live in `apps/platform_runtime/blueprint_contract.py`.
- Tenant Blueprint UI lives in `templates/platform_runtime/tenant_blueprint_setup.html`.
- Preview/apply/impact/rollback live in:
  - `apps/platform_runtime/blueprint_preview.py`
  - `apps/platform_runtime/blueprint_apply.py`
  - `apps/platform_runtime/blueprint_impact.py`
  - `apps/platform_runtime/blueprint_rollback.py`
- Package contracts and package apply behavior live under `apps/platform_runtime/pack_contract.py` and `apps/packages/`.
- Offline rails exist through `OfflineAction`, offline workflow apply verification, and seven-day server-side endurance tests.
- Current Blueprint `offline_defaults` are shallow metadata. They do not yet enforce cached surfaces, device roles, sync cadence, conflict policies, rollback invalidation, browser storage proof, or survival proof per Blueprint.
- Current composition support is explicit metadata, not yet a full multi-select planner. Build on the existing metadata before adding a larger planner.

## Audit First

Run and inspect:

```powershell
python scripts\audit_blueprint_local_first_offline.py
```

Then manually verify:

- Every tenant-safe Blueprint in `BASELINE_BLUEPRINTS`.
- Every referenced package in Blueprint preview output.
- Every tenant Blueprint route and link target.
- Every platform-only Blueprint or pack action is hidden on tenant surfaces.
- Every Blueprint preview shows honest local-first/offline readiness.
- Every Blueprint preview shows composition role, compatible Blueprints, supported education tracks, local constraints, and tenant app catalog recommendations.
- Every apply path persists tenant-scoped state only.
- Every rollback path restores settings and invalidates local/offline manifests.
- Studio Launch `Open school & region settings` routes to `/school/configuration/`.
- `/school/apps/` and `/settings/app-catalog/` resolve to tenant-safe catalog surfaces.

## Implementation Waves

### Wave 0: Truth Ledger

- Keep `docs/generated/blueprint_local_first_offline_audit.md` and `.json` as the accepted audit ledger.
- Update the audit script as implementation improves so stale claims cannot survive.

### Wave 1: Local-First Manifest Contract

Add a first-class local-first manifest shape for each tenant-safe Blueprint. Required fields:

- `offline_survival_target_days`
- `cached_surfaces`
- `offline_actions`
- `device_roles`
- `indexeddb_stores`
- `service_worker_assets`
- `sync_cadence`
- `conflict_policies`
- `manual_fallbacks`
- `external_dependencies`
- `proof_tests`
- `browser_proof_status`
- `server_proof_status`
- `rollback_invalidation`

Start with code-level contract fields before migrations. Use JSON-compatible structures so the manifest can be saved in `BlueprintInstallation.preview_snapshot` and `School.settings`.

### Wave 2: Preview Engine

Extend `preview_blueprint` to emit:

- `local_first_manifest`
- `offline_readiness`
- `outage_survival_matrix`
- `device_role_impacts`
- `conflict_policy_by_domain`
- `manual_fallbacks`
- `external_blockers`
- `proof_status`

Preview must never mutate tenant settings. Missing proof must render as `PARTIAL` or `UNPROVEN`, not `READY`.

### Wave 3: Apply Engine

Extend `apply_blueprint` to:

- Persist the selected Blueprint manifest under tenant-scoped `school.settings`.
- Store the preview manifest in `BlueprintInstallation.preview_snapshot`.
- Maintain idempotency for repeated apply requests.
- Keep package apply failures from leaving false readiness claims.
- Emit audit events for manifest activation.

### Wave 4: Rollback And Revocation

Extend rollback to:

- Restore school settings snapshot.
- Mark active local-first Blueprint manifest as rolled back.
- Invalidate or version-bump offline cache manifests.
- Queue tenant-scoped device refresh guidance where supported.
- Keep rollback evidence in the audit trail.

### Wave 5: Tenant UI

Upgrade tenant Blueprint UI so each row has:

- Blueprint name and school fit.
- Offline readiness status.
- Local-first coverage summary.
- Device-role impact.
- External blockers.
- Preview action.
- Apply action when safe.
- Request approval state when policy requires it.
- Rollback availability when already applied.
- Composition role: base, regional overlay, offline overlay, specialty overlay, or operator network.
- Compatible Blueprints.
- Supported education tracks such as general, technical/vocational, science, arts, commercial, bilingual, boarding, or international.
- Local constraints such as exam calendar, grading variant, manual payment fallback, sync owner, or language review.
- Tenant app catalog recommendations.

Use the approved warm tenant command workspace style. Keep it full width, balanced, and bounded. Long Blueprint details should use side panels, modals, or expandable zones instead of endless pages.

### Wave 5B: Composition Planner

Add a tenant-safe composition planner after the single-Blueprint UI is stable:

- Let a tenant preview one base Blueprint plus multiple overlays.
- Block incompatible combinations before apply.
- Explain conflicts and precedence in plain language.
- Merge modules, roles, report templates, packs, local-first manifests, and conflict policies deterministically.
- Keep region and curriculum overlays additive unless they explicitly override a base setting.
- Require confirmation for any override that changes grading, academic year, report format, payment posture, or offline conflict policy.
- Persist the composed plan as a single tenant-scoped snapshot so rollback is straightforward.

### Wave 6: Pack And Offline Integration

Every Blueprint package reference must declare:

- Whether it supports offline use.
- Which offline actions it enables.
- Which conflicts it can create.
- Which tenant roles can use it offline.
- Which local assets or IndexedDB stores it requires.
- How it rolls back or invalidates cached data.

Every tenant app recommendation must declare:

- Tenant route or catalog key.
- Whether it can run offline.
- Required roles and permissions.
- External dependency posture.
- Preview/install state: preview, apply, request approval, installed, rollback.

### Wave 7: Tests And Gates

Add or update focused tests:

- Every tenant-safe Blueprint has a complete local-first manifest.
- Operator-only Blueprints never appear on tenant surfaces.
- Blueprint preview includes local-first manifest and does not mutate settings.
- Blueprint apply persists the manifest and remains idempotent.
- Blueprint rollback invalidates or restores local-first state.
- Referenced packages resolve without `pack_not_found`.
- Tenant Blueprint links never target `/super/` or operator `/admin/`.
- Launch school/region links target `/school/configuration/`.
- Tenant app catalog links resolve on tenant hosts and do not expose platform-only app controls.
- Seven-day offline server proof is represented honestly.
- Browser/client storage proof remains `PARTIAL` until a real browser harness exists.

## Validation Commands

Run at minimum:

```powershell
python scripts\audit_blueprint_local_first_offline.py
python manage.py test apps.platform_runtime.tests.test_blueprint_preview_engine apps.platform_runtime.tests.test_blueprint_apply_engine
python manage.py test apps.platform_runtime.tests.test_seven_day_offline_endurance
python manage.py check
python manage.py makemigrations --check --dry-run
python -m compileall -q apps config scripts
```

If local database drift blocks a test, document the exact blocker in the generated audit and run the remaining non-database checks.

## Done Criteria

- Generated audit reports no tenant-safe Blueprint missing required manifest fields.
- Tenant Blueprint page shows preview/apply/request/rollback states accurately.
- Preview and apply output includes local-first/offline evidence.
- Rollback handles local/offline manifest state.
- No tenant route redirects to operator-only surfaces.
- Tests and audit scripts pass, or every environment-only proof gap is explicitly documented.

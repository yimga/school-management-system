# Phase 10 — Next Steps (Path-to-10)

**Purpose:** Concrete next steps for executing the Phase 10 backlog. See **`docs/PHASE_10_BACKLOG.md`** for full status.

---

## 1. Siteconfig (1.2, 1.3)

- **1.2** Continue state-safe migrations: ensure `RuntimeDefaults` backfill covers all tenants; switch more reads to resolver overlay; add deprecation markers to remaining direct `SiteSettings` access in tenant code.
  - **Run after deploy:** `python manage.py backfill_runtime_defaults` (run once per environment after deploying RuntimeDefaults migration). `get_effective_site_settings()` overlays RuntimeDefaults.payload on base SiteSettings; prefer it over `SiteSettings.get_solo()` in tenant read paths.
- **1.3** Delete legacy paths: remove deprecated accessors and columns per SITECONFIG_OWNED_MODELS; run `lint_tenant_settings --check-get-solo-only` in CI and fix any new get_solo.
  - **CI:** Already enforced in `scripts/pre_deploy_gate.sh` (lint_tenant_settings --check-get-solo-only and --check-school-settings-features).

---

## 2. Architecture (2.1)

- Continue giant-file decomposition: split `accounts/views.py`, `schools/super_views.py`, `portal/views.py`, `finance/views.py`, `api/views_v1.py` by bounded domain (see `docs/GIANT_FILE_DECOMPOSITION.md` if present).
- Add CI step to fail when any target file exceeds agreed line threshold.

---

## 3. Orchestration (4.1)

- Extend `apps/orchestration`: add runners for ProcessDefinition types; wire `process_orchestration_runs` to operator workbench; add retries/compensation and SLA visibility.

---

## 4. Toolsets (10.2–10.8)

- **10.2** Feature Control: add `FeatureToggleState.expires_at` (or equivalent) and surface “why this feature is on” in runtime inspector.
- **10.4–10.8** Document Library lifecycle, Design Studio layout builder, Live Previews central service, Workflows simulation/marketplace, AI & API contract tests — implement in phases per product priority.

---

## 5. Done this pass

- **1.2** Documented: run `backfill_runtime_defaults` after deploy; CI already in pre_deploy_gate for get_solo.
- **2.1** Added `docs/GIANT_FILE_DECOMPOSITION.md` (target files + thresholds); `lint_mega_files.py` already in gate.
- **4.1** Orchestration workbench: SLA column + overdue badge; Retry action for failed runs (`super:orchestration_retry_run`); `OrchestrationRun.sla_overdue` property.
- **10.2** Runtime inspector: "Feature toggles (why on)" card with key, is_enabled, source (school|global), expires_at; `get_feature_toggle_inspection(school)` in `platform_runtime.runtime_inspector`.
- **10.4–10.8** Added `docs/TOOLSETS_PHASE_10_STUBS.md` and `apps/portal/document_lifecycle.py` (lifecycle constants stub).

---

## 6. Reference

- **Backlog:** `docs/PHASE_10_BACKLOG.md`
- **Master checklist:** `docs/MASTER_PLATFORM_CHECKLIST.md`
- **What’s left / deferred:** `docs/WHATS_LEFT_COMPLETE_BACKLOG_DEFERRED.md`
- **Toolsets stubs:** `docs/TOOLSETS_PHASE_10_STUBS.md`

# Phase 6 — Siteconfig / SiteSettings dismantling — checklist

**SOT:** ZIP Phase 5 — **COMPLETE** (repository behavioral gate). Phase B batches 0–13 — **COMPLETE** in-repo (`SITECONFIG_OWNERSHIP_MIGRATION.md`; migration files in `verify_phase_5_siteconfig.py`; DB proof via `verify_phase_b_execution.py` after migrate).

**Cursor Phase 6 mandatory audit:** [PHASE_06_SITECONFIG_SITESETTINGS_AUDIT.md](../phase_audit/PHASE_06_SITECONFIG_SITESETTINGS_AUDIT.md) — **CLOSED** 2026-03-24.

**Mechanical gates:** `python scripts/verify_cursor_phase6_siteconfig_sitesettings.py` (ZIP verify + tenant lints + Batch3 FK lint + **`audit_sitesettings_python_surface.py`** JSON + ORM allowlist). **Granular (full Phase 6 proof):** `python scripts/verify_cursor_phase6_granular.py`. **Post-migrate:** `python scripts/verify_phase_b_execution.py`.

## Inventory / guardrails

- [x] `docs/site_settings_usage_inventory.md` — current reads classified (**DONE** per doc header)
- [x] `docs/SITECONFIG_OWNERSHIP_MIGRATION.md` — ownership moves (referenced in audit + verify_phase_5_siteconfig)
- [x] Grep `get_solo()` / `SiteSettings` on **new** features — `lint_tenant_settings.py` + CI `test_tenant_settings_lint.py`

## Python hot spots (audit when touching)

- [x] `apps/siteconfig/` — models slim + `domain_ownership`; views remain bounded UI entry points
- [x] `apps/brand_experience/` — `PlatformGlobalBranding` (migrations 0002, 0163)
- [x] `apps/platform_runtime/` — `RuntimeDefaults.payload`, `get_effective_site_settings`

## Validation

- [x] `scripts/verify_phase_5_siteconfig.py` — inside Phase 6 bundle
- [x] `scripts/audit_sitesettings_python_surface.py` — product-Python surface JSON (schema v2, **`per_file`**, **violation** kinds); class-level allowlist: **`siteconfig/models`**, **`platform_runtime/helpers`**; approved reads: **`site_settings_read_access`**
- [x] `scripts/lint_tenant_settings.py` — get_solo / school.settings / SiteSettings.objects (tenant apps)
- [x] `scripts/lint_phase_b_batch3_sitesettings_fk_writes.py` — no removed FK writes on SiteSettings
- [x] `scripts/verify_phase_b_execution.py` — post-migrate / deploy DB (tables + snapshot rows when `SiteSettings` exists)
- [x] `apps/platform_runtime/tests/test_phase_b_execution_gate.py` — E2E same checks on migrated **test** DB (CI)

## Acceptance

- [x] SOT gate: tenant behavior not driven by SiteSettings as sole truth on migrated paths
- [x] Ongoing discipline: no expansion of siteconfig mega-domain without ownership classification — enforced by inventory + `domain_ownership` + lints; Phase B batch tracker complete; optional deeper extraction is SOT forward cadence only

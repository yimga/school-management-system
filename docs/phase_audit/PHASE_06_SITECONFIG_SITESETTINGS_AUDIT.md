# Phase 6 — Siteconfig / SiteSettings dismantling — mandatory audit

**Authority:** Cursor **Phase 6** (SiteSettings no longer tenant behavior truth; `siteconfig` not a mega-domain on **touched** paths). **ZIP Phase 5** (SiteSettings / siteconfig repository gate) remains `scripts/verify_phase_5_siteconfig.py` — this audit **adds** Cursor Phase 6 traceability and bundles lints via `scripts/verify_cursor_phase6_siteconfig_sitesettings.py`.

**Canonical SOT:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](../RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.1 / ZIP Phase 5 rows. **Execution log:** [RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md](../RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md). **Checklist:** [phase_06_siteconfig_sitesettings.md](../phase_checklists/phase_06_siteconfig_sitesettings.md).

**Updated:** 2026-03-24 — Phase 6 **CLOSED** for in-repo mechanical + documented acceptance. Phase B batches 0–13 are **complete** in-repo (see `SITECONFIG_OWNERSHIP_MIGRATION.md`); optional deeper table extraction remains **SOT product cadence**, not an open Phase B backlog against the Phase 6 bar.

---

## 1. SiteSettings physical model (slim singleton + RuntimeDefaults)

| Aspect | Implementation | Evidence |
|--------|----------------|----------|
| ORM columns on `SiteSettings` | **Slim:** `maintenance_mode`, `updated_at` (+ `pk`) | `apps/siteconfig/models.py` class docstring + fields; **CI:** `apps/siteconfig/sitesettings_slim_contract.py` — ORM + **DB introspection** when `siteconfig_sitesettings` exists (`sitesettings_slim_db_errors`), enforced by `scripts/verify_phase_b_execution.py` |
| Legacy behavioral fields | **Not** on `SiteSettings` row; read via `__getattr__` → `RuntimeDefaults.payload` merge | `SiteSettings.__getattr__`, `_persist_runtime_payload_updates` |
| Branding / theme pack FKs | **PlatformGlobalBranding** (`brand_experience`); Batch 3 dropped mirrored columns | Migration `0163_phase_b_batch3_drop_sitesettings_branding_columns` |
| Payload backfill | **0162** slim + `RuntimeDefaults` | `0162_phase_b_slim_sitesettings.py` |

**Conclusion:** `SiteSettings` is **platform-default / maintenance shell** plus virtual reads; **not** the authoritative wide row for tenant product behavior.

---

## 2. Field ownership classification (required implementation)

| Mechanism | Location |
|-----------|----------|
| Exact field → owner | `EXACT_FIELD_OWNERS` in `apps/siteconfig/domain_ownership.py` |
| Prefix → owner | `PREFIX_FIELD_OWNERS` |
| Resolver API | `classify_site_settings_field(name)` |
| Runtime shadow keys | `is_runtime_payload_shadow_key(name)` |

**Domains:** `safe_platform_default`, `brand_experience`, `runtime_blueprints`, `policies_rules`, `plans_entitlements`, `global_registries`, `metadata_governance`, `marketplace_integrations`, `reports`, `documents`, `design_studio`, `preview_platform`, `delete`.

**Inventory (human-readable):** [site_settings_usage_inventory.md](../site_settings_usage_inventory.md) — field list + usage sites + completion criteria.

**Migration plan:** [SITECONFIG_OWNERSHIP_MIGRATION.md](../SITECONFIG_OWNERSHIP_MIGRATION.md).

---

## 3. `get_solo()` and tenant-app guardrails

| Guardrail | Script / test | Rule |
|-----------|---------------|------|
| No `SiteSettings.get_solo()` in tenant app trees | `scripts/lint_tenant_settings.py --check-get-solo-only` | `TENANT_APPS` vs `ALLOWED_GET_SOLO_PREFIXES` |
| No `SiteSettings.objects.*` in tenant apps | `--check-sitesettings-orm-in-tenant-apps` | Use `get_platform_site_settings_record` / runtime helpers |
| No raw `school.settings` / `school.features` in tenant apps | `--check-school-settings-features` | Allowlist for canonical readers only |
| CI | `apps/platform_runtime/tests/test_tenant_settings_lint.py` | Subprocess runs above + `verify_phase_5_siteconfig.py` |
| Batch 3 FK writes | `scripts/lint_phase_b_batch3_sitesettings_fk_writes.py` | No assign/save/create of removed theme/report FKs on `SiteSettings` |
| Singleton ORM choke point | `scripts/lint_sitesettings_orm_singleton.py` | `SiteSettings.objects.*` only in `siteconfig/models.py` + `platform_runtime/helpers.py` (else use `get_platform_site_settings_record`) |

**Allowlisted `get_solo()` (platform / commands):** `apps/siteconfig/models.py`, `apps/platform_runtime/helpers.py`, selected `management/` trees — see `lint_tenant_settings.py`.

---

## 4. Mandatory audit (Phase 6 spec checklist)

| Audit item | Result | How verified |
|------------|--------|--------------|
| All **touched** `SiteSettings` reads on tenant paths | **PASS** | Lint: no `get_solo` / `objects` / forbidden `school.settings` in `TENANT_APPS`; runtime path `get_effective_site_settings` documented in inventory |
| `siteconfig` domain shrinkage on touched flows | **PASS** | Slim model + branding on `PlatformGlobalBranding` + console hubs; no re-adding `customizer`/`workflow_hub`/`report_library` as primary `siteconfig` **named** routes (Studio OS owns those product surfaces) |
| Moved ownership coverage | **PASS** | `domain_ownership.py` + `brand_experience` + `platform_runtime` migrations; inventory §2 |
| Singleton misuse remaining on **touched** flows | **PASS** | Mechanical script + tenant lint suite; any new violation fails CI |

---

## 5. `siteconfig` surfaces inventory (touched — not mega-domain expansion)

**Still in `siteconfig` by design (bounded):** theme colors, feature control, workflow gallery, blueprint getters, console domains hub, preview-from-form, report builder **views** — these are **UI entry points**, not proof that tenant **behavior truth** lives on `SiteSettings`.

**Truth path for tenant behavior:** `apps/platform_runtime/helpers.py` — `get_effective_site_settings(request=..., school=...)` merges school, runtime payload, platform defaults, branding resolvers per SOT.

**Coupling documented:** `site_settings_usage_inventory.md` §1 (usage sites by file).

---

## 6. Acceptance criteria (Phase 6 mission)

| Criterion | Result | Evidence |
|-----------|--------|----------|
| Touched tenant behavior **not** depending on `SiteSettings` as business truth | **PASS** | Virtual attrs served from `RuntimeDefaults.payload` + resolvers; tenant code lint clean |
| `SiteSettings` reduced toward safe platform-default storage | **PASS** | Slim columns; maintenance + timestamps; `__getattr__` bridge |
| `siteconfig` stops expanding as mega-domain on **touched** areas | **PASS** | Ownership map + lints + Studio OS redirects for former mega-pages; new features must use `domain_ownership` / bounded apps per inventory |

---

## 7. Mechanical re-audit (run before claiming Phase 6)

```bash
python scripts/verify_cursor_phase6_siteconfig_sitesettings.py
```

Also run (already inside the bundle above, listed for transparency):

```bash
python scripts/verify_phase_5_siteconfig.py
python scripts/lint_tenant_settings.py --check-get-solo-only --base .
python scripts/lint_tenant_settings.py --check-school-settings-features --base .
python scripts/lint_tenant_settings.py --check-sitesettings-orm-in-tenant-apps --base .
python scripts/lint_phase_b_batch3_sitesettings_fk_writes.py
python scripts/lint_sitesettings_orm_singleton.py --base .
python -m pytest apps/platform_runtime/tests/test_tenant_settings_lint.py apps/platform_runtime/tests/test_phase_b_execution_gate.py -q
```

**End-to-end (migrated DB) in CI:** `apps/platform_runtime/tests/test_phase_b_execution_gate.py` runs the same checks as `scripts/verify_phase_b_execution.py` in-process against Django’s migrated test database (tables + `SiteSettings` → PGB pk=1 + snapshot rows).

**After migrate** (local deploy / staging): `python scripts/verify_phase_b_execution.py` — same logic; optional `DJANGO_TEST_DB_FILE` for a specific sqlite path. The subprocess Phase 6 bundle (`verify_cursor_phase6_siteconfig_sitesettings.py`) intentionally skips this so unmigrated dev DBs still pass lint/doc gates; E2E proof is the test above + this CLI on real databases.

---

## 8. Phase B repository closure (no backlog waiver)

**Phase B batches 0–13** are **COMPLETE** in this repository (slim `SiteSettings`, `RuntimeDefaults` payload, `PlatformGlobalBranding`, dropped mirrored branding FKs on `SiteSettings`, `PlatformPhaseBDomainSnapshot` rows per domain). Evidence: tracker table in [SITECONFIG_OWNERSHIP_MIGRATION.md](../SITECONFIG_OWNERSHIP_MIGRATION.md); required migration files asserted by `verify_phase_5_siteconfig.py` (inside the Phase 6 bundle); **after migrate**, `scripts/verify_phase_b_execution.py` proves tables and snapshot/singleton consistency on a real database.

**Phase 6’s closure bar** — touched tenant paths + guardrails + slim singleton + ownership map + no mega-domain regression on those surfaces — is **fully met** in-repo. That is **not** conditional on an “incremental Phase B backlog”; unfinished Batch 0–13 work would have **failed** the gate above.

Optional work (more first-class tables per payload key, richer console UX, environment-specific staging checks) is **SOT forward cadence** (see single source of truth section 11.4), tracked as product roadmap — **not** as Phase 6 or Phase B debt against the closed bar.

---

## 9. Granular verification (nothing missed — executable)

Beyond the standard bundle, run:

```bash
python scripts/verify_cursor_phase6_granular.py
```

This enforces: Phase 6 mechanical bundle; audit + inventory anchors; `EXACT_FIELD_OWNERS` size; migrations **0162** / **0163** on disk; pytest **tenant lints** + **Phase B E2E gate** + **domain snapshot** save/row tests. Use before claiming Phase 6 is “only documented.”

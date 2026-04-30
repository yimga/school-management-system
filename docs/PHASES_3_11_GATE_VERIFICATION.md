# Phases 3–11 — gate verification (audit trail)

**Purpose:** Record how Phases **3–11** map to **repo-deliverable evidence** without duplicating strategy. **Authoritative execution state** remains **`RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`** and **`BACKLOG_AND_DEFERRED_CLOSURE.md`**.

**Status:** **Gates MET** for repo engineering — each phase has identifiable code, docs, or scripts; **no PARTIAL** rows below (each line is **DONE** with pointer).

| Phase | Theme | Evidence in repo | Gate / command |
|-------|--------|------------------|----------------|
| **3** | Control-plane UX | `siteconfig:console_domains_hub`, `studio_os:system_config_console`, `super:trust_center`, `super:*` views; Control Studio rail | Templates + URLs exist; `apps/studio_os/views.py`, `apps/schools/super_views_trust_surface.py` |
| **4** | Studio OS | Five modes, `templates/studio_os/shell.html`, redirects in `LEGACY_PATH_INVENTORY.md` | SOT §4; redirects for customizer / workflow-hub / report-library |
| **5** | Siteconfig / SiteSettings | Tenant behavior via runtime; no tenant `get_solo()` | `python scripts/lint_tenant_settings.py --check-get-solo-only` → **PASS** |
| **6** | Runtime-first | `get_effective_site_settings`, `build_tenant_runtime`, precedence | `docs/runtime_precedence.md`, `apps/platform_runtime/tests/test_runtime_contract.py` (run with full DB per `TEST_DATABASE.md`) |
| **7** | Dashboards / role-home | `role_home_engine.py`, `build_role_home_context` | `apps/dashboard/services/role_home_service.py`, SOT N7/N8 depth |
| **8** | Security / trust | Pre-deploy discipline, Phase H | `python scripts/lint_secret_exposure.py` → **PASS**; `python scripts/phase_h_audit.py` → **PASS** (static) |
| **9** | Marketplace / packs | Engine + seed targets + UI | `apps/packages/engine.py`, `apps/platform_runtime/tests/test_marketplace_catalog_minimums.py`, `MARKETPLACE_SEED_TARGETS` |
| **10** | Marketing | Canonical marketing shell | `templates/marketing/base_marketing.html`, `docs/MARKETING_*` |
| **11** | Gilead + docs | Neutral naming; single SOT | Migration **0155**; `python scripts/lint_gilead_residue.py` → **PASS**; docs per SOT §0 |

## One-shot non-DB verification

```bash
python scripts/verify_phases_3_11_gates.py
```

**Exact run order:** `main()` in `scripts/verify_phases_3_11_gates.py` (do not duplicate a partial list here — it drifts). **Maintainer-facing subset table:** Appendix below, generated from `docs/gate_map_appendix_config.json` via `python scripts/generate_gate_map_appendix.py --write` (CI checks with `--check`). End-of-bundle steps still include wedge/marketplace/program/ecosystem/static Phase H/UI wiring audits as implemented in that script.

**Operator Phase 10 + 11 (ecosystem + marketing) — DB-backed end-to-end slice** (pytest + migrated gate SQLite + `verify_ux_completion.py`):

```bash
python scripts/verify_operator_phase10_11_e2e.py
```

Static + pytest only (skip UX audit and gate migrate):

```bash
python scripts/verify_operator_phase10_11_e2e.py --skip-ux-completion
```

## DB-backed tests (full gate)

See **`scripts/pre_deploy_gate.sh`** and **`docs/TEST_DATABASE.md`**. Includes `test_runtime_contract`, marketplace minimums, Phase H URL tests, etc.

## Gaps — **closed**

- **Phase 3 “operator UX”:** Bounded consoles + Studio Control + trust center **shipped**; mega-CRUD remains in Django admin by **design** (`SHELL_ARCHITECTURE_MATRIX.md` — admin is separate surface).
- **Phase 5–6:** Tenant **lint** passes; runtime contract tests require **migrated DB** — not a product gap.
- **Phase 7:** Role-home engine **shipped**; N7/N8 “depth” is **continuous improvement** in SOT, not a blocking **PARTIAL** gate.
- **Phase 9:** Marketplace **productized** per §12 / seed targets; certification graph depth = **BEYOND_REACH** in SOT, not Phase 9 failure.
- **Phase 10–11:** Marketing shell + Gilead lint **green**; external assets / SOC2 = **SOT_REMAINING_ITEMS_BACKLOG.md** (external-only).

**Last verified:** script + linters executed in CI/local with exit code 0 when `verify_phases_3_11_gates.py` passes.

<!-- GATE_MAP_APPENDIX:START -->
## Appendix — new gate map (2026-03-26)

Gate-map appendix generated from a single config list.

| Verifier / check | Purpose | Entry points |
|------------------|---------|--------------|
| `scripts/check_no_committed_env.py` | Git must not track `.env` / `.env.local` (secrets hygiene); shell wrapper calls same script | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/check_repo_hygiene.py` | Repo hygiene: conflict markers and backup/debug debris | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/check_root_clutter.py` | Tracked files at repo root must stay within `tracked_root_allowlist.json` | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `manage.py check` | Django system check (settings, apps, URLs load) — no DB migration apply | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `manage.py makemigrations --check --dry-run` | Fail when model changes would require new migration files | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/lint_bounded_context_imports.py --strict` | Tenant vs control-plane import boundaries | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/lint_siteconfig_legacy_imports.py` | Block legacy `siteconfig.models` imports for domain-owned types | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/scan_repo_secrets.py` | High-risk token patterns in `apps/`, `config/`, `services/` | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/lint_no_print_in_apps.py` | No `print()` in application trees (code hygiene) | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `ruff check apps --select F401,F841` | Unused imports / unused variables in `apps/` | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/check_no_hardcoding.py --allow-tests` | Architecture no-hardcoding gate (tests may be exempt) | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/lint_phase_b_batch3_sitesettings_fk_writes.py` | Phase B batch 3 burn-in: no forbidden SiteSettings branding FK writes | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/lint_broad_except.py --strict + broad_except_allowlist.json` | Broad `except` non-growth with allowlist | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/generate_platform_inventory.py --check` | Inventory JSON/MD committed = live code scan (—write stays full train to refresh) | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_shell_architecture_matrix.py` | Shell triad contracts (`/admin`, `/super`, `/studio`, tenant base) stay boundary-safe | `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/generate_gate_map_appendix.py --check` | PHASES_3_11 gate-map appendix stays synced to `docs/gate_map_appendix_config.json` | `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_phase_5_siteconfig.py` | ZIP Phase 5 siteconfig dismantling (docs + `domain_ownership` + mechanical checks) | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_phase5_studio_os_conformance.py` | Studio OS: five canonical modes, URL routes, legacy redirect coverage, output canvas contracts | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/lint_sitesettings_orm_singleton.py --base .` | `SiteSettings.objects` usage confined to approved modules | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_siteconfig_decomposition_depth.py` | `domain_ownership` ↔ Phase B snapshot-domain alignment + slim/first-class artifacts; SITECONFIG_OWNERSHIP_MIGRATION.md wires inventory `site_settings_refs_*` + `generate_platform_inventory.py` | `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_gilead_full_tree_classification.py` | Full-tree `gilead` references restricted to classified historical/tooling buckets | `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_doc_plan_density_discipline.py` | Single-source docs discipline + non-growth cap on plan/roadmap/remediation/master density | `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_path_to_100_plan_discipline.py` | PATH_TO_100_PERCENT_EXECUTION_PLAN.md: SOT pointers + Phase III §6.1–6.24 per-app spine | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_pre_deploy_gate_record.py` | Committed docs/generated/pre_deploy_gate_run.txt ends with successful pre_deploy (§11.4 evidence) | `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_migration_safety_doc_discipline.py` | NORTH_STAR_TRUST_AND_OPS.md migration safety operator contract (§0.4) | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_performance_targets_doc_discipline.py` | NORTH_STAR_TRUST_AND_OPS.md performance targets N9/N10 operator contract (§0.4) | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_lms_sso_doc_discipline.py` | NORTH_STAR_TRUST_AND_OPS.md LMS/SSO & federation operator contract (§0.4) | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_uk_international_packs_doc_discipline.py` | NORTH_STAR_TRUST_AND_OPS.md UK/international packs operator contract (§0.4) | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_advancement_crm_doc_discipline.py` | NORTH_STAR_TRUST_AND_OPS.md advancement CRM operator contract (§0.4) | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_ai_blueprint_completion.py` | AI/provider wiring completeness (gateway, endpoints, prompt families, docs) | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/lint_csrf_exempt_usage.py` | `csrf_exempt` usage allowlist drift guard | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/lint_allow_any_usage.py` | `AllowAny` usage allowlist drift guard | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/lint_raw_sql_usage.py` | Raw SQL `cursor.execute` usage allowlist drift guard | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_security_allowlists.py` | Classified allowlists: `manifest_last_reviewed`, per-file `last_reviewed`, broad_except + tracked_root policy dates | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_security_allowlist_density.py` | Non-growth caps for allowlists; embedded raw_sql/csrf/AllowAny lints; ledger summary parity | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/build_phase8_security_ledger.py --check` | Phase 8/9 merged security ledger parity with allowlists | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_operating_discipline_docs.py` | §10.5 doc refs in `role_home_engine` (`*_DOC` → existing `docs/` paths) | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_design_system_phase2.py` | ZIP Phase 2 shell/CSS contract + nested `verify_section10_5_layers` (10.5.7) | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/audit_luxury_ui_surface.py` | Luxury UI surface: major templates, seven UX dimensions, score >= 13/15, severe integration | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps.platform_runtime.tests.test_tenant_settings_lint.LuxuryUiGateTests`; `scripts/run_northstar_audit.py`; `scripts/run_northstar_self_heal.py` |
| `scripts/lint_marketing_nav_no_overflow.py` | Marketing navbar primary items and overflow handling (§8 / Phase 11) | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/validate_wedge_super_premium_phases.py --phase all` | SOT §0.2.1.5–§0.2.1.6 wedge super-premium phased proof + packs + URL reverse | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_phase7_dashboard_markers.py` | Phase 7 decision-surface + Phase 8 declaration tags on registered dashboard templates | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_control_plane_hub_registry_drift.py` | Control-plane extends closure: `PHASE7_DASHBOARD_TEMPLATES` + exempt list covers all CP hubs | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/lint_north_star_a11y.py --strict` | North star N3/N4: base shells reference `accessibility.css` (strict; no optional touch scan) | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/lint_north_star_i18n.py --strict` | North star N21: key templates declare i18n load / `trans` | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/verify_i18n_catalog_fresh.py` | `locale/en/LC_MESSAGES/django.po` covers translatable strings found by the i18n scanner | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |
| `scripts/generate_gate_map_appendix.py --check` | `docs/PHASES_3_11_GATE_VERIFICATION.md` gate-map appendix matches this config (`--write` after edits) | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py` |
| `scripts/verify_api_v1_named_routes_snapshot.py --check` | `apps.api.urls_v1` named routes match `scripts/generated/api_v1_named_routes.json` (`--write` after URL changes) | `scripts/pre_deploy_gate.sh`; `scripts/verify_phases_3_11_gates.py`; `apps/platform_runtime/tests/test_tenant_settings_lint.py` |

**Note:** `scripts/pre_deploy_gate.sh` executes the consolidated module (`apps.platform_runtime.tests.test_tenant_settings_lint`) and no longer duplicates `scripts/verify_phases_3_11_gates.py` in sequence.

<!-- GATE_MAP_APPENDIX:END -->

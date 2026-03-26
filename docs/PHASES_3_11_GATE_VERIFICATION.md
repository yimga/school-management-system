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

Runs: `lint_tenant_settings`, `lint_gilead_residue`, `lint_secret_exposure`, `verify_sot_pillar_evidence`, wedge scripts, `phase_h_audit` (static), `verify_program_phase10_phase11_gates.py`, **`verify_repo_wide_ecosystem_marketing_audit.py`**, **`verify_ui_wiring_audit.py`** (every template `{% url %}` literal vs union of root/tenant/manager/public urlconfs + HTML href hazard scan; report `docs/phase_audit/UI_WIRING_AUDIT_LATEST.md`).

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

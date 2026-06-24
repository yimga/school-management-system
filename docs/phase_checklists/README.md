# Phase checklists (autonomous execution)

**Agent contract:** [AGENTS.md](../../AGENTS.md) (root) — use repo gates, SOT, and this folder; choose the next slice without asking unless blocked.

Each `phase_XX_*.md` file lists files, routes, templates, and validation steps for that Cursor phase. Mark items `[x]` only after validation.

**Master program (12-phase) crosswalk:** Checklist filenames follow the **Cursor/Studio ZIP** order, not the same numbers as some runbooks. Map runbook “Phase N (topic)” → file + gate:

| Runbook phase (topic) | Checklist | Primary gate |
| --- | --- | --- |
| 1 — SiteSettings / `siteconfig` / singletons | [phase_06_siteconfig_sitesettings.md](phase_06_siteconfig_sitesettings.md) | `python scripts/verify_phase1_settings_gravity.py` (plus `verify_phase_5_siteconfig.py`, `lint_tenant_settings.py`) |
| 2 — Authenticated shell | [phase_01_authenticated_shell.md](phase_01_authenticated_shell.md) | `python scripts/verify_phase2_authenticated_shell_conformance.py` |
| 3 — Design system / tokens | [phase_02_design_system_tokens.md](phase_02_design_system_tokens.md) | `verify_phases_3_11_gates.py` (bundle) + shell matrix |
| 4 — Navigation / command palette / archetypes | [phase_03_navigation_command_archetypes.md](phase_03_navigation_command_archetypes.md) | `python scripts/verify_phase3_navigation_command_conformance.py` |
| 5 — Control plane | [phase_04_control_plane.md](phase_04_control_plane.md) | `python scripts/verify_phase4_control_plane_decision_console.py` |
| 6 — Studio OS | [phase_05_studio_os.md](phase_05_studio_os.md) | `python scripts/verify_phase5_studio_os_conformance.py` |
| 7 — Runtime-first | [phase_07_runtime_first.md](phase_07_runtime_first.md) | `python scripts/verify_phase6_runtime_first_conformance.py` + `verify_phase6_runtime_first_extension.py` |
| 8 — Dashboards / role homes | [phase_08_dashboards_role_homes.md](phase_08_dashboards_role_homes.md) | `python scripts/verify_phase8_dashboard_role_homes_conformance.py` |
| 9 — Security / trust / endpoints / raw SQL | [phase_09_security_trust.md](phase_09_security_trust.md) | `python scripts/verify_phase9_security_trust_conformance.py` + `build_phase8_security_ledger.py --check` + allowlist lints |
| 10 — Marketplace / packs / migration | [phase_10_marketplace_packs_migration.md](phase_10_marketplace_packs_migration.md) | Bundle steps in `verify_phases_3_11_gates.py` + marketplace parity |
| 11 — Marketing front | [phase_11_marketing_front.md](phase_11_marketing_front.md) | Marketing static gates in `verify_phases_3_11_gates.py` |
| 12 — Gilead / docs discipline | [phase_12_gilead_docs_discipline.md](phase_12_gilead_docs_discipline.md) | `lint_gilead_residue` + `verify_gilead_full_tree_classification` (bundle) |

**Full multi-phase bar (long run):** `python scripts/verify_phases_3_11_gates.py`.

**Status of record:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](../RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) (**§0** 12-phase map, **§11**, **§11.4**, **§12**). The SOT is the **index**; granular rows live in this folder—not duplicate “master status” tables here.

Execution log: [RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md](../RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md).

**Tenant exception handoff (batch 1728):** [TENANT_SURFACE_EXCEPTION_HANDOFF.md](TENANT_SURFACE_EXCEPTION_HANDOFF.md) — Good → Exception menu + inner-page program after Cycle 8 / batch 1727. Previews: `docs/generated/preview_tenant_elevation_hub.html`.

**2026-04-25 (batch 966, PATH III.39):** Teacher syllabus **builder** and **preview** HTTP contract coverage — **`apps/academics/tests/test_academics_critical_paths.py`**; primary gate is **`manage.py test`** for that module (academics has no separate phase file in this folder).

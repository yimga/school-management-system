# Phase 5 — Studio OS consolidation — checklist

**SOT:** §4 Studio OS parent statuses **DONE**; depth (billing SKUs, simulation productization, etc.) tracked under §5 / §11.4.

**Mandatory audit (route→mode matrix, acceptance):** [PHASE_05_STUDIO_OS_AUDIT.md](../phase_audit/PHASE_05_STUDIO_OS_AUDIT.md) — **CLOSED** 2026-03-24.

## Granular required work (spec — all traced in audit §0)

- [x] **Customizer** — Studio Experience + redirects
- [x] **Theme colors** — Experience in-page + siteconfig deep links
- [x] **Feature control panel** — Control Studio + native partial when permitted
- [x] **Workflow hub** — Automation Studio + legacy redirect
- [x] **Report library** — Output `pane=reports` + legacy redirects
- [x] **Document library** — Output `pane=documents` native
- [x] **Setup simulators** — Launch/Automation in-product + public `setup_simulator` (marketing host)
- [x] **Preview fragments** — `studio_os:preview`, publish/save-draft, shell bottom bar, `preview_from_form`
- [x] **Output builders** — Report card builder native pane
- [x] **Launch / setup flows** — Launch mode rail + overview + wizard iframes per `views.py` (**2026-04-25** — **PATH III.9 depth:** **Migration path** rail pane (`?pane=migration` → `accounts:migration_wizard` embed) + **Preview by role** native pane (`?pane=role_preview` + `launch_studio_role_preview_pane.html`); `deep_links` **`accounts:migration_wizard`**; tests in **`test_launch_and_automation_rails`**) (**2026-04-25** — **PATH III.33 / batch 963:** **accounts** first-login checklist + **customersuccess** guided onboarding + **`get_studio_command_palette_entries`** link operators/teachers into the same **Launch Studio** panes; tests **961–963**) (**2026-04-25** — **batch 967:** **`get_setup_studio_payload`** step links + **`launch_studio_overview_body`** checklist/migration CTAs + **guided onboarding** hero pane links; **`verify_phase5_studio_os_conformance`**) (**2026-04-25** — **batch 968:** **`plan_choice` → `?pane=plan`**, **`registry_alignment`**, **phase1** `portal_base` /studio/ marker) (**2026-04-25** — **batch 969:** **`TimeZoneRegistry`** on **`registry_alignment`**; shared **`shell-data-dashboard-page.js`** across portal/cp/admin bases; **siteconfig** bulk letters + report library on **`backend_base`**) (**2026-04-25** — **batch 970–971:** **`CurrencyRegistry`** on **`registry_alignment`** + **`summary_lines`**; Launch overview **registry** list UI) (**2026-04-25** — **batch 972–973:** **`LocaleRegistry`** + **`CalendarSystemRegistry`** on **`registry_alignment`**; setup tests) (**2026-04-25** — **batch 974–975:** full **`key_rows`/`mismatch`/`settings_cta`**, additional registries, Launch table UX) (**2026-04-25** — **batch 976 (shell):** **`siteconfig`/`metadata`/`marketplace`** **`data-dashboard-page`** classes)

## Required implementation (five modes)

- [x] **Experience** — 3-pane workbench + subpages
- [x] **Automation** — rail, native overview/graph/health, simulation + conflict awareness, iframe only for heavy panes
- [x] **Outputs** — native panes for all rail targets; tests for `data-studio-output-native`
- [x] **Launch** — guided rail + native overview/plan
- [x] **Control** — governance spine (outcomes, operator model, feature panel, rail)

## Mandatory audit (before completion)

- [x] Tool-to-studio route mapping — audit **§0 + §1**
- [x] Fragmented identity survival — audit **§6** + redirect tests
- [x] Studio mode completeness — audit **§0 + §1**
- [x] Native output behavior — audit **§2.2** + pytest
- [x] Launch flow coherence — audit **§2.3 + §0**

## Core templates (modes)

- [x] `templates/studio_os/shell.html` — tenant (mode rail + canvas + right impact rail; audited 2026-03-24)
- [x] `templates/studio_os/shell_control_plane.html` — manager (inherits same mode contract via Phase 1 subpage wrap)
- [x] `templates/studio_os/partials/*mode*canvas*.html` — Experience, Automation, Outputs, Launch, Control (Experience workbench + Automation conflict CTA touched this pass)
- [x] Output Studio: native paths vs iframe — `output_mode_canvas.html` documents native panes; iframe only fallback + builder preview by design (verified 2026-03-24)

## Python

- [x] `apps/studio_os/views.py` — mode routing, context (`experience_context_tool_links`, `automation_conflict_pane_url`)
- [x] `apps/studio_os/services.py` — publish, rollback, deep links (unchanged this pass; existing contracts)
- [x] `apps/studio_os/tests/` — `test_experience_workbench.py`, `test_phase_05_legacy_redirects.py`, `test_phase_05_granular_taskers.py`, extended `test_output_native_builder.py`; full suite green

## Validation

- [x] `python -m pytest apps/studio_os/tests/` — **PASS** (includes `test_phase5_mechanical_gate` → subprocess `verify_cursor_phase5_studio_os.py`)
- [x] `python scripts/verify_cursor_phase5_studio_os.py` — **PASS** mechanical re-audit (every `studio_os:*` reverses; legacy 302s; no `customizer`/`workflow_hub`/`report_library` in `siteconfig/urls.py`; admin redirect order)
- [x] `python scripts/verify_design_system_phase2.py` — **PASS** (studio-shell-layout.css extended)

## Acceptance

- [x] Studio OS is primary spine for creation/configuration on touched flows (legacy keys map via `deep_links.studio_legacy_urls_map`; hubs linked from shell overview)
- [x] Output Studio reliable on touched paths (native panes for dependency, reports, documents, credentials, branding, policy; iframe fallback explicit)

## Definition of done (no partial closure)

- [x] All Phase 5 acceptance criteria **PASS** with **zero waivers** — see [PHASE_05_STUDIO_OS_AUDIT.md](../phase_audit/PHASE_05_STUDIO_OS_AUDIT.md) §5 and §8.
- [x] Automated gates green: `pytest apps/studio_os/tests/`, `verify_design_system_phase2.py`.

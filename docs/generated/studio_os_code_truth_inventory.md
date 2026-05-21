# Studio OS — Code-Truth Inventory (v3.54.0)

**Generated:** 2026-05-21 from the filesystem after the v3.54.0 wave.

This is what physically exists, not what's documented as planned.

## App module

[`apps/studio_os/`](../../apps/studio_os/)

| File | Purpose |
|---|---|
| `apps.py` | Django `AppConfig` |
| `urls.py` | 39 URL patterns under the `studio_os` namespace |
| `views.py` | ~2440 lines; `studio_shell` entrypoint + 30+ mode-specific views |
| `services.py` | ~1430 lines after v3.54.0 cockpit-helper additions |
| `studio_guidance.py` | Studio guidance panel service |
| `school_infrastructure.py` | Infra preview / validate / apply |
| `deep_links.py` | URL resolver helpers |
| `embed_render.py` | Iframe canvas embed helper |
| `navigation.py` | `STUDIO_MODES` + nav config |
| `copilot_rail_service.py` | v3.53.1 persistent AI rail (preserved) |
| `views_copilot_rail.py` | v3.53.1 rail context + insights endpoints |

## URL namespace

Namespace: `studio_os` · 39 routes total.

Modes: `overview` (shell root), `experience`, `automation`, `output`, `launch`, `control`.

API endpoints: `studio_os:{preview, publish, save_draft, version_history, global_search, recommendations, audit, rollback, school_infrastructure_{preview,validate,apply}_api, copilot_rail_{context,insights}}`.

## Templates

[`templates/studio_os/`](../../templates/studio_os/)

**Shell templates:** `shell.html` · `shell_control_plane.html` · `shell_subpage_wrap.html` · `studio_embed_body_shell.html` · `studio_embed_minimal.html` · `studio_subpage_embed.html`

**Mode templates:** `modes/{experience,automation,output,launch,control}.html`

**Total partial count:** ~40 (including 6 new v3.54.0 cockpit/preview partials).

**v3.54.0 new partials:**
- `overview_command_cockpit.html`
- `experience_live_preview_pane.html`
- `automation_simulation_preview_pane.html`
- `output_readiness_preview_pane.html`
- `launch_readiness_preview_pane.html`
- `control_governance_preview_pane.html`

## CSS bundles

**Shared (preserved):** `studio-os-cockpit.css`, `studio-workspace.css`, **`studio-mode-rail.css`** (the v3.54.0 systemic overflow fix lives at lines 5-20), `studio-shell-layout.css`, `studio-command-deck.css`, `studio-focus-layout.css`, `studio-guidance.css`, `studio-mode-hero.css`, `studio-operator-toolbar.css`, `studio-control-inline.css`, `studio-control-mode-canvas.css`, `studio-embed-minimal.css`, `studio-system-config-console.css`.

**v3.54.0 new per-section:**
- `studio-overview-cockpit.css` (~570 lines)
- `studio-experience-mode.css` (~260 lines)
- `studio-automation-cockpit.css` (~360 lines)
- `studio-output-cockpit.css` (~480 lines)
- `studio-launch-cockpit.css`
- `studio-control-cockpit.css` (34 selectors)

## JavaScript

- `static/js/_pages/studio_os__shell.js` — v3.54.0 adds shared capture-phase `data-rmc-confirm` handler IIFE
- `static/js/rmc-copilot-rail.js` (v3.53.1, persistent AI rail)
- `static/js/rmc-command-bar.js` (v3.53.0, cmd+k)

## Tests

**Section modules** (12 total including extensions):
- `test_overview_next_realm.py` (23 tests, v3.54.0 new)
- `test_experience_overflow_invariants.py` (7, v3.54.0 new)
- `test_experience_workbench.py` (extended +2)
- `test_automation_simulation_cockpit.py` (v3.54.0 new)
- `test_launch_and_automation_rails.py` (extended +6)
- `test_output_native_builder.py` (extended +2)
- `test_output_readiness_cockpit.py` (10, v3.54.0 new)
- `test_launch_readiness_cockpit.py` (v3.54.0 new)
- `test_school_infrastructure.py` (extended +4 in new partial-render class)
- `test_studio_control_inline.py` (extended +2)
- `test_control_governance_cockpit.py` (9, v3.54.0 new)

**Cross-cutting modules (v3.54.0 new, 27/27 PASS on Windows in 0.2s):**
- `test_studio_os_layout_contracts.py`
- `test_studio_os_live_previews.py`
- `test_studio_os_operator_tenant_boundaries.py`
- `test_studio_os_navigation_integrity.py`
- `test_studio_os_accessibility_contracts.py`

**Existing preserved modules:** 19 (cockpit_shell_contract, command_bar_registry, copilot_rail, cp_bridge_policy, deep_links, phase_05, phase5, preview_context, studio_embed_chrome, studio_focus_layout, studio_guidance, studio_operator_toolbar, studio_os_world_class_experience, studio_overview_deck, studio_rail_resolution, studio_ux_waves, studio_workspace_layout, batch949_experience_compare_view, batch963_command_palette_launch_panes).

## E2E

`tests/e2e/studio-os.spec.js` (v3.54.0 new). Coverage: 6 modes × 3 viewports (390/768/1366) + skip-link reachability + studio-rail link integrity + `data-rmc-confirm` capture-phase handler + tenant-boundary checks. Execution: deferred — requires Playwright + Django dev server.

## Preserved features (do not relitigate)

- v3.53.0 Mission Cockpit chrome (signal strip + canvas + co-pilot rail)
- v3.53.1 persistent AI rail
- v3.51 onwards command palette
- Existing operator toolbar + bottom bar
- Studio guidance panel service

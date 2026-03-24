# Studio OS Shell Requirements (§4.1)

**Purpose:** §4.1 of [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Measurable list of shared shell requirements.

**Status:** **Spine DONE** — shell, all five mode hubs, cross-host deep links, preview/publish/rollback, activity, recommendations, role preview, and control-plane canvas parity (`shell_control_plane.html` + `partials/shell_main_content.html`) are implemented. **Product PARTIAL (SOT §4.1 / §1.7):** retire remaining legacy tool URLs; full uniform pack tooling — see [LEGACY_PATH_INVENTORY.md](LEGACY_PATH_INVENTORY.md).

**Validation:** [STUDIO_OS_PHASE4_VALIDATION.md](STUDIO_OS_PHASE4_VALIDATION.md) — `python -m pytest apps/studio_os/tests/ -q`; line-by-line audit §7.

---

## 1. Shared shell must provide

| Requirement | Status | Notes |
|-------------|--------|-------|
| global search | DONE | `studio_os:global_search` API GET `?q=`; filters command palette |
| command palette | DONE | `get_studio_command_palette_entries`; CMD+K; shell + `shell_main_content` |
| cross-host deep links | DONE | `apps/studio_os/deep_links.py`, `resolve_studio_href`; tests `test_deep_links.py`, `test_studio_rail_resolution.py` |
| unified left rail | DONE | Mode rail (`studio_modes`) on tenant `shell.html` and manager/control-plane `shell_main_content.html` |
| unified preview engine | DONE | `studio_preview`, `get_studio_preview_url`; UNIFIED_PREVIEW_PUBLISH_CONTRACT.md |
| unified publish / rollback | DONE | `studio_os:publish`, `studio_os:rollback`, `studio_save_draft_api` |
| unified activity / audit feed | DONE | `get_studio_activity_feed`; `studio_audit_api` |
| unified recommendation engine | DONE | `get_studio_recommendations`; `studio_os:recommendations` |
| unified role/device preview switcher | DONE | `get_studio_role_preview_entries`; Launch payload / fallback roles |
| all five mode hubs | DONE | Experience, Automation, Output, Launch, Control — rail + native/iframe panes; Automation/Output/Launch canvases single-sourced in `partials/*_mode_canvas.html` |

---

## 2. Studio modes (absorb current tools)

- **Experience Studio:** customizer, theme colors, branding, experience packs, §11.1 rail items → `modes/experience.html`.
- **Automation Studio:** workflow, approvals, §11.1 automation items → `modes/automation.html` → `automation_mode_canvas.html`.
- **Output Studio:** report/document/report-card surfaces → `modes/output.html` → `output_mode_canvas.html`.
- **Launch Studio:** onboarding, plan, blueprint, checklist, payload → `modes/launch.html` → `launch_mode_canvas.html`.
- **Control Studio:** feature control, governance links → `modes/control.html` → `control_mode_canvas.html`.

---

## 3. Completion gate (§4.1)

- [x] All shared shell capabilities above implemented (search, palette, deep links, rail, preview, publish/rollback, activity, recommendations, role preview, five hubs).
- [x] Control-plane Studio uses the same mode canvases as tenant Studio where applicable (`shell_main_content.html` includes `automation_mode_canvas`, `output_mode_canvas`, `launch_mode_canvas` before generic `embed_url` fallback).
- [ ] **Product / subtractive:** Users no longer *need* legacy standalone URLs for daily work — redirect/retire per SOT §1.7 and LEGACY_PATH_INVENTORY (ongoing).

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §4.1.*

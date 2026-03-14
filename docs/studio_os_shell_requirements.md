# Studio OS Shell Requirements (§4.1)

**Purpose:** §4.1 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Single list of shared shell requirements so implementation is measurable. Nothing deferred.

**Status:** PARTIAL — shell and shared capabilities implemented; modes (Experience/Automation/Output/Launch/Control) in progress.

---

## 1. Shared shell must provide

| Requirement | Status | Notes |
|-------------|--------|-------|
| global search | DONE | `studio_os:global_search` API GET ?q=; filters command palette; extend with metadata search for full entity search |
| command palette | DONE | Entries in shell (get_studio_command_palette_entries); CMD+K primary per COMMAND_PALETTE_PRIMARY.md |
| unified left rail | DONE | Studio OS shell left rail shared across all modes (studio_modes) |
| unified preview engine | DONE | studio_preview; get_studio_preview_url per mode; UNIFIED_PREVIEW_PUBLISH_CONTRACT.md |
| unified publish / rollback engine | DONE | studio_os:publish, studio_os:rollback, studio_save_draft_api; contract doc |
| unified activity / audit feed | DONE | get_studio_activity_feed (theme, feature_control, package_apply); studio_audit_api |
| unified recommendation engine | DONE | get_studio_recommendations; studio_os:recommendations API; mode-specific recs |
| unified role/device preview switcher | DONE | get_studio_role_preview_entries; studio_role_preview_entries in shell template; Launch payload or fallback roles |

---

## 2. Studio modes (absorb current tools)

- **Experience Studio:** customizer, theme colors, branding, palette, experience preview → one Experience mode.
- **Automation Studio:** workflow hub, approval/workflow config, workflow preview → one Automation mode.
- **Output Studio:** report library, document library, design-studio output, report-card/document builder → one Output mode.
- **Launch Studio:** create school, plan, blueprint, branding, starter stack, migration path, preview, checklist, health score → one Launch mode.
- **Control Studio:** feature control, system config sprawl, runtime/blueprint/integration/plan governance → one Control mode.

---

## 3. Completion gate (§4.1)

- [ ] Users solve goals inside one shell, not by hopping across admin tools (modes still embed legacy tools).
- [x] All 8 shared shell requirements implemented and visible in Studio OS (search, palette, rail, preview, publish/rollback, activity, recommendations, role preview).

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §4.1.*

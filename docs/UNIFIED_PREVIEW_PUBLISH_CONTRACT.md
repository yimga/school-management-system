# Unified Preview / Publish Contract (§4.1)

**Purpose:** §4.1 Studio OS — single contract for preview vs publish/rollback across all Studio modes. Shared semantics so Experience, Automation, Output, Launch, and Control behave consistently.

**Status:** In force. Implementations must align to this contract.

---

## 1. Definitions

| Term | Meaning |
|------|--------|
| **Preview** | Render or simulate changes without persisting. User sees "what would happen" (theme, workflow, report, config). |
| **Publish** | Persist approved changes to the live tenant. May require confirmation and audit. |
| **Rollback** | Revert to a previous published state (or last known good). Must be auditable. |
| **Draft** | Staged state (e.g. session or DB) that can be previewed then published or discarded. |

---

## 2. Contract (all modes)

1. **Preview is read-only** — Preview must not mutate tenant data. Use session, sandbox, or copy.
2. **Publish is explicit** — No auto-publish. User action (e.g. "Publish" button) with optional confirmation.
3. **Rollback is available when state exists** — If the mode supports versioning or previous state, offer rollback; otherwise hide or disable.
4. **Audit** — Every publish and rollback must be logged (actor, timestamp, scope, outcome). Use `get_studio_activity_feed` / feature control audit / theme_recent_change_meta.
5. **Single entry points** — Use `studio_os:preview`, `studio_os:publish`, `studio_os:rollback` for Studio shell; mode-specific logic may delegate to existing views (e.g. theme_colors, feature_control_panel).

---

## 3. Per-mode mapping

| Mode | Preview | Publish | Rollback |
|------|---------|---------|----------|
| Experience | Theme/color preview (session/site_preview_settings) | theme_colors save / theme publish | theme_previous_state → restore |
| Control | N/A (config diff in UI) | feature_control_panel save | feature_control_previous_state → revert |
| Output | Report/document preview (sample data) | (future) ReportPack publish | (future) version history |
| Automation | Workflow simulation | Workflow activate | (future) workflow rollback |
| Launch | Role preview, health summary | execute_launch | N/A (one-time) |

---

## 4. Completion gate (§4.1)

- [x] Contract documented (this file).
- [ ] All modes implement preview/publish/rollback per contract (Experience + Control partial; others stubbed or in progress).

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §4.1.*

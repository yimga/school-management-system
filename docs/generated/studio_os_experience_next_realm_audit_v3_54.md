# Studio OS — Experience Next-Realm Audit (v3.54.0)

**Date**: 2026-05-21
**Agent**: Agent 2 (Experience)
**Pair JSON**: [studio_os_experience_next_realm_audit_v3_54.json](studio_os_experience_next_realm_audit_v3_54.json)
**Primary mandate**: catalog and remediate horizontal cut-off across Studio OS, with Experience as the worst-affected surface.

## 1. Surface inventory

Studio OS Experience renders through:

- **Shell**: `templates/studio_os/shell.html` (portal host) or `shell_control_plane.html` (manager host).
- **Mode page**: `templates/studio_os/modes/experience.html` — extends shell, links `studio-mode-rail.css`, includes the hero + guidance panel + body partial.
- **Body partial**: `templates/studio_os/partials/studio_experience_mode_body.html` — branches on `use_experience_in_page` (workbench with in-page Theme & Colors form) vs `experience_left_rail` (iframe canvas) vs `embed_url` (raw iframe) vs fallback card.
- **Workspace component**: `templates/studio_os/components/workspace_layout.html` — declares the three-pane `.rmc-studio-workspace--three-col` grid: rail | main | context.
- **Rail / canvas / context partials** (in-page workbench branch):
  - `templates/studio_os/partials/workspace/experience_inpage_rail.html`
  - `templates/studio_os/partials/workspace/experience_inpage_canvas.html`
  - `templates/studio_os/partials/experience_workbench_context.html`
- **Rail / canvas / context partials** (iframe branch):
  - `templates/studio_os/partials/workspace/experience_iframe_rail.html`
  - `templates/studio_os/partials/workspace/experience_iframe_canvas.html`
  - `templates/studio_os/partials/experience_workbench_context.html`

**Routes** (12 Experience routes — `apps/studio_os/urls.py:62-96`): `experience`, `experience_recommendations`, `experience_compare`, `experience_theme_tokens`, `experience_portal_shell_layouts`, `experience_dashboard_visual_packs`, `experience_school_website_blocks`, `experience_communication_style_packs`, `experience_packs`; plus three legacy `siteconfig:` routes wired into the rail.

**Context vars** the views feed in (`apps/studio_os/views.py:1370-1447`): `use_experience_in_page`, `experience_workspace_two_col`, `experience_left_rail`, `experience_context_tool_links`, plus everything `get_theme_colors_context()` provides (`form`, `site_settings`, `theme_token_values`, `theme_contrast_report`, `theme_contrast_targets`, `admin_theme_packs`, `back_url`, `theme_recent_change_meta`), plus the standard Studio shell extras (`studio_version_history`, `studio_audit`, `studio_role_preview_entries`, `studio_preview_url`, `studio_publish_url`, `studio_rollback_url`, `legacy_urls`).

## 2. Horizontal-overflow root-cause table

| ID | File / line | Selector or tag | Failure mode | Fix strategy | Owner |
|----|---|---|---|---|---|
| OF-1 | `experience_iframe_canvas.html:2-3` | `iframe.studio-os-iframe` | No responsive wrapper; class sets `min-height: 80vh` only; iframe content can force inner horizontal scroll | Wrap in `.rmc-studio-experience-iframe-shell` with `width:100%; max-width:100%; height:clamp(420px,60vh,720px); border:1px solid var(--hairline); border-radius` | agent 2 |
| OF-2 | `experience_inpage_rail.html:16-24` | `.studio-os__card ul li a` | Long rail labels (translated) have no `overflow-wrap`; rail grid track is `min(12.5rem, 100%)`; long unsplittable tokens push the rail wider than its track | `overflow-wrap:anywhere` on rail links via new `studio-experience-mode.css` | agent 2 |
| OF-3 | `experience_workbench_context.html:3-11` | `.studio-os__experience-context` aside | Context tool link labels can be long translated strings; risks horizontal widening when `min-width:0` isn't enforced on inner items | `overflow-wrap:anywhere` on context links; cards inherit `min-width:0` from the workspace contract | agent 2 |
| OF-4 | `experience_iframe_rail.html:7-9` | `<a class="experience-rail-link">` | Same long-label class as OF-2; iframe branch separately | Same CSS rule covers both branches (selector `.studio-os__experience-rail a.experience-rail-link`) | agent 2 |
| OF-5 | `static/css/studio-mode-rail.css:5-14` | shared rail-link rule | No `overflow-wrap` / `word-break`; affects 4 modes (Experience, Output, Automation, Launch) | **Do not edit shared file.** Layer Experience overrides in new `studio-experience-mode.css`. Flag for coordinator + other agents. | coordinator-task |
| OF-6 | `shell.html:24` | `.container-fluid.py-2.px-0.px-md-2.rmc-shell-content-grid` | `.rmc-shell-content-grid` already has `overflow-x: clip` (`studio-shell-layout.css:58`). Shell is fine; risk is downstream. | No action | coordinator (documented) |
| OF-7 | `static/css/studio-shell-layout.css:119-127` | `.studio-os__right` | Legacy right column (outside workspace 3-col) uses `overflow-x: clip` intentionally; not the Experience workspace context column. | No action | coordinator (documented) |
| OF-8 | `partials/subpages/experience_compare.html:13,27` | inline `style="width:1.25rem;height:1.25rem;background:..."` | Rem-based swatch; dynamic background unavoidable for tenant data. No horizontal cut. | No action | (outside Experience workspace ownership) |
| OF-9 | `experience_workbench_context.html` (planned content) | new context-column content | Under-built today; new content (token values, audit feed, version history) must enforce `min-width:0` + `overflow-wrap:anywhere` on every code/value cell | Rebuild context column with these invariants baked in | agent 2 |
| OF-10 | `experience_inpage_canvas.html:1` | single `{% include theme_colors_content.html %}` | Legacy include is dense (palette, form, preview); inner rows may not clamp on 1366px | Wrap include in `<div class="rmc-studio-experience-canvas-clamp">` firewall | agent 2 |

## 3. Live preview model

**Existing**:

- `studio_os:preview` (POST-only, `views.py:2216`) delegates to `siteconfig.preview_from_form` for `mode=experience` and to per-mode redirect-URLs for other modes — not a render endpoint.
- `studio_os:experience_compare` renders before/after swatches inside `experience_compare.html`.

**Gaps**:

- No in-shell live-preview iframe pane in Experience. Today the only "preview" is the legacy Theme & Colors form's own preview block plus the compare subpage.
- `studio_role_preview_entries` context is populated by `get_studio_role_preview_entries()` (services.py:259) but only rendered in **Launch** (via `launch_studio_role_preview_pane.html`), never in Experience.

**Plan**: build `experience_live_preview_pane.html`:

- responsive iframe wrapper (`aspect-ratio: 16/10; width: 100%; max-width: 100%`)
- `<select>` driven by `studio_role_preview_entries` (when populated) — real tenant role URLs
- "current applied" / "draft" badges driven by `theme_contrast_report.status` + `theme_recent_change_meta`
- honest "Preview unavailable — no role preview routes yet" empty state
- iframe `title="..."` attribute for a11y

## 4. Operator vs tenant capability

| Capability | Tenant | Operator |
|---|---|---|
| Theme & colors edit | yes (settings.manage) | yes |
| Customizer | yes | yes |
| Experience packs install | catalog read only | yes (governed) |
| Brand import from website | yes | yes |
| Theme tokens viewer | yes (read) | yes |
| Compare (before/after) | yes | yes |
| Live preview pane (new) | yes (own tenant) | yes (selected school) |
| Audit log of publishes | yes (own) | yes (all) |

All operator-only controls are already gated by `request.public_host_kind == 'manager'` checks at the view layer; no new operator surfaces added in Experience workspace.

## 5. Rail item health (12 / 12 real)

Every Experience rail item resolves to a real `reverse()`-able route via `_studio_rail_append`. No dummy `#` links in the rail.

## 6. Required actions

| Target | Action | Reason |
|---|---|---|
| `experience_workbench_context.html` | aggressive refactor | rebuild as real context column (tokens, contrast, history, audit, preview-as-role) |
| `experience_inpage_canvas.html` | minor repair | clamp wrapper around legacy include |
| `experience_iframe_canvas.html` | minor repair | responsive iframe shell |
| `experience_inpage_rail.html` | minor repair | wrap long labels; live-active marker |
| `experience_iframe_rail.html` | keep | CSS-only overflow-wrap fix covers it |
| `modes/experience.html` | minor repair | link new CSS file |
| `studio_experience_mode_body.html` | keep | pass-through; no overflow risk |
| `studio-mode-rail.css` | do not edit | shared by 4 modes; layer overrides instead |
| `studio-experience-mode.css` | **create** | Experience-scoped layout safety |
| `experience_live_preview_pane.html` | **create** | next-realm preview brief |
| `test_experience_overflow_invariants.py` | **create** | lock invariants |
| `test_experience_workbench.py` | extend | assert new context column content |

## 7. Coordinator follow-up

- **Shared rail CSS** (`static/css/studio-mode-rail.css`) is used by Experience / Output / Automation / Launch. The `overflow-wrap` fix Experience adds should be ported to the other three rails too (CSS-only, 1-line each). Coordinator can either:
  1. Apply the same selectors in the shared file (preferred), or
  2. Have each mode-agent layer their own per-mode override.
- **Cockpit canvas** (`cockpit_canvas.html`) is owned by Agent 1 — Experience cannot inspect its overflow behavior, but the shell has `overflow-x: clip` upstream, so cockpit overflow is bounded.
- **No new context vars required** from `studio_shell`; everything the new context column and preview pane render comes from existing keys (`theme_token_values`, `theme_contrast_report`, `studio_version_history`, `studio_audit`, `studio_role_preview_entries`).

## 8. Scanner-risk assessment

No new sticky+overflow combos, no inline hex, no new `theme-locked-allow`, no inline style attrs, no PII logging touched, no `data-theme` writes, no `rmc-reveal` logic touched. All new `.rmc-studio-experience-*` classes are defined in the new `studio-experience-mode.css`. Expected delta: all zero-tolerance gates remain 0.

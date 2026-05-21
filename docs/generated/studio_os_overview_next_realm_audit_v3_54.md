# Studio OS Overview — Next-Realm Cockpit Audit (v3.54.0, 2026-05-21)

Agent 1 / 6 — owns the **OVERVIEW (cockpit home)** section of the Studio OS rebuild.

## Scope

Studio OS shell renders `current_mode is None` as the cockpit home (the "Overview"). This audit
inventories every panel that renders in that state, classifies architecture / UX / workflow / tenant
boundary, identifies missing context vars + dummy links + horizontal overflow risks, and proposes
the minimum next-realm fix per panel.

## View-side context vars available to Overview

`apps/studio_os/views.py::studio_shell` (lines ~1296-1369) passes the following when `mode is None`:

| Var | Source | Shape |
|---|---|---|
| `studio_modes` | `STUDIO_MODES` constant | `list[{id,label,description,guidance_*}]` |
| `current_mode` | `None` for Overview | `str|None` |
| `legacy_urls` | `_resolve_legacy_urls` | dict of optional URL keys |
| `school` | `request.school` | `School|None` |
| `studio_activity_feed` | `get_studio_activity_feed` | `list[{kind,label,timestamp,actor,detail,url}]` |
| `studio_recommendations` | `get_studio_recommendations` | `list[{label,detail,url,tone}]` |
| `studio_command_palette_entries` | `get_studio_command_palette_entries` | `list[dict]` |
| `studio_role_preview_entries` | `get_studio_role_preview_entries` | `list[{role,label,url}]` |
| `studio_overview_deck` | `get_studio_overview_deck` (Overview only) | `{mode_cards,tenant_banner,tenant_context,quick_stats,operational_hubs,show_command_hint}` |

## Context vars missing for the next-realm cockpit (flagged as coordinator tasks)

| Var | Purpose | Honest deferral |
|---|---|---|
| `overview_signals` | Payload for the 6 mission-signal tiles (pending launches, draft experiences, active automations, output readiness pct, open blockers, mode indicator) | Tiles render `—` placeholder and `data-state="unknown"` until service lands. NEVER fake data. |
| `launch_health_summary` / `launch_ready` in Overview | Today these are only set when `current_mode == 'launch'` (views.py:1456-1478). The Overview signal strip needs them too. | Treat as unknown when absent; tile renders `—`. |
| `studio_blockers` | Aggregated cross-mode blockers (launch payload + feature control + automation conflicts) | Render only when present. |

## Panel-by-panel verdict

### 1. `partials/cockpit_signal_strip.html`

- **Architecture:** template-only — pulses are decorative
- **UX:** dense / minimal — only 3 pulses (tenant, mode, launch summary)
- **Workflow:** partial — no primary action, no preview link
- **Tenant boundary:** shared
- **Required action:** **aggressive refactor** — convert to mission-grade 6-tile signal strip with operator/tenant indicator and honest `—` placeholders.

### 2. `partials/cockpit_copilot_rail.html`

- **Architecture:** coherent (context strip + insights + actions + endpoint hooks)
- **UX:** premium — skeleton rows + JS hydration + server-rendered fallback
- **Workflow:** clear — primary action is `⌘K Open command bar`
- **Required action:** **minor repair** — add an operator mode badge and preview-shortcuts microlist. Keep service contract intact.

### 3. `partials/studio_guidance_panel.html`

- **Architecture:** coherent — wired to `studio_guidance.get_guidance_for(...)` service
- **UX:** acceptable — collapsible Q&A list with optional `pane_hint`
- **Workflow:** partial — surfaces questions only; no primary/secondary action, no preview, no blocker indicator
- **Required action:** **minor repair** — when `studio_guidance.primary_action` / `preview_url` / `blocker` are provided, surface them. Defaults remain a graceful fallback.

### 4. `shell.html` lines 91-110 (mode-card grid)

- **Architecture:** template-only — duplicates the `studio_overview_deck.html` partial that already exists
- **UX:** dense per-mode if/elif CTA chain
- **Workflow:** single CTA per card; no readiness signal; no preview
- **Required action:** **coordinator-task** — replace with `{% include 'studio_os/partials/overview_command_cockpit.html' %}` (new partial owned by this agent). Coordinator removes shell.html lines 91-123.

### 5. `shell.html` lines 113-123 (operational hubs action row)

- **Architecture:** coherent — driven by `legacy_urls` keys
- **UX:** **horizontally dense** — 9 buttons in `.row.g-2 .col-auto`. Bootstrap `row` flex-wraps, so no overflow, but visual density is high.
- **Workflow:** dead-end — links open destinations without context
- **Tenant boundary:** shared — should be operator-emphasised when `request.public_host_kind == 'manager'`
- **Required action:** **coordinator-task** — same as #4. Subsumed by `overview_command_cockpit.html`.

### 6. `shell.html` lines 155-269 (right-rail `<aside>`)

- **Issue:** the `Impact & publish` card cascade (`{% if current_mode == 'experience' %} … {% elif current_mode == 'launch' %} …`) has **no Overview branch**. When `current_mode is None` it falls through to the final `{% else %}` block (line 265) which renders generic copy.
- **Required action:** **coordinator-task** — add an `{% elif not current_mode %}` branch (proposed diff in JSON `coordinator_tasks_required.co-2`).

### 7. `partials/launch_studio_overview_body.html`

- **Architecture / UX:** coherent — drives off `launch_payload`
- **Required action:** **keep** — light additive polish: ensure top card emphasises primary action, ensure flex children carry `min-width: 0`.

### 8. `partials/launch_studio_role_preview_pane.html`

- **Architecture / UX:** coherent
- **Required action:** **keep** — light additive polish only.

## Live-preview link inventory

Every link in our owned partials resolves through one of:

- `studio_recommendations[i].url` — real `reverse()`-resolved URL (`studio_os:experience`, `studio_os:control`, `studio_os:launch`, `siteconfig:feature_control_audit`). Service emits the rec only when reverse succeeds.
- `studio_activity_feed[i].url` — real mode-shell reverse.
- `legacy_urls.*` — only present when the underlying view exists; templates guard with `{% if %}`.
- `launch_role_previews[i].url` — real per-tenant role-preview URLs from setup_studio payload. Already `target="_blank" rel="noopener noreferrer"`.
- Mode card CTAs in shell.html — `{% url 'studio_os:<mode>' %}` always resolves.

**Zero `href="#"` dummy links found in agent-owned templates.** The only `href="#"` in the larger studio_os tree
is `cockpit_copilot_rail.html:76` (the `⌘K` open-command-bar action) — that one is deliberately a no-op anchor
handled by `rmc-copilot-rail.js` via `data-rmc-cmdk-trigger="1"`. Test will accept this exemption via attribute
allowlist.

## Horizontal overflow risk per viewport

| Location | 390 | 768 | 1366+ | Verdict |
|---|---|---|---|---|
| `shell.html:91-110` mode card grid | wraps cleanly | wraps cleanly | grid | safe |
| `shell.html:113-123` action row | wraps to multiple lines (dense) | wraps | row | safe but dense |
| `cockpit_signal_strip` flex pulses | **risk** — long content overflows | safe | safe | **must add `flex-wrap` + `min-width: 0` in new CSS** |
| `cockpit_copilot_rail` rail | fixed 320px in cockpit grid | depends on grid breakpoint in `studio-os-cockpit.css` (coordinator-owned) | rail | safe |
| `launch_studio_overview_body` registry list | `d-flex flex-wrap` + `text-break` | safe | safe | safe |

## Coordinator tasks (out of agent ownership)

| # | File | Lines | Task |
|---|---|---|---|
| co-1 | `templates/studio_os/shell.html` | 91-123 | Replace overview body block (mode cards + ops paragraph + action row) with `{% include 'studio_os/partials/overview_command_cockpit.html' %}` |
| co-2 | `templates/studio_os/shell.html` | 155-269 | Add `{% elif not current_mode %}` branch in the right-rail Impact-publish cascade (see `coordinator_tasks_required.co-2.proposed_diff_snippet` in JSON) |
| co-3 | `apps/studio_os/views.py` | 1342-1369 | Attach `overview_signals` dict to context when `not mode`. Honest deferral: tiles render `—` until service lands. |
| co-4 | `apps/studio_os/views.py` | 1449-1479 | Mirror `launch_health_summary` + `launch_ready` into context even when `current_mode is None`. |

## Non-negotiables checklist

- **No hardcoding** — every copy string wrapped in `{% trans %}`; tile values come from context vars.
- **No inline hex / off-token colors** — new CSS uses only `var(--*)` tokens declared in `design-tokens.css`.
- **No dummy links** — every anchor either resolves to a real URL or is gated by `{% if %}`.
- **Tenant safety** — operator-only tiles gated by `{% if request.public_host_kind == 'manager' %}`.
- **A11y** — `<h2>`/`<h3>` semantic order preserved; `role="region"` + `aria-label` on tile strip; `aria-describedby` on tiles with unknown state.
- **Layout safety** — every flex/grid child carries `min-width: 0`; tile strip uses `flex-wrap` so 6 tiles wrap on narrow viewports.
- **CSS retirement hygiene** — no `/* removed */`, no `// dead`, no orphan markers.

## Scanner risks introduced

None expected — the new `static/css/studio-overview-cockpit.css` uses only existing design tokens
(`--surface-elevated`, `--surface-canvas`, `--hairline`, `--text-primary`, `--text-secondary`,
`--text-tertiary`, `--elev-1/2`, `--radius-md/pill`, `--motion-signature-state` if defined; falls back
to `--motion-normal`). All new `.rmc-overview-*` classes are defined in the same file (no
`scan_undefined_css_classes` regression). No inline `style="..."` literals (no
`scan_inline_style_off_token` regression). No JS attribute writes of `data-theme="system"` (no
`scan_theme_attribute_contract` regression).

## What this audit explicitly does NOT do

- Touch any mode template (`modes/{experience,automation,output,launch,control}.html`) — owned by other agents.
- Edit `shell.html` / `shell_control_plane.html` / `shell_subpage_wrap.html` — coordinator-owned.
- Edit `static/css/studio-os-cockpit.css` — coordinator-owned.
- Wire `overview_signals` service in `views.py` — flagged as coordinator task co-3.
- Bump the service worker — coordinator-owned.
- Update CLAUDE.md / MEMORY.md / CSS_RETIREMENT_DOCKET.md — coordinator-owned.

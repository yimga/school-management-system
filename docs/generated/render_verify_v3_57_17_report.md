# render-verify v3.57.17 (2026-05-22) — structural comparison

## Context strategy

**PARTIAL-ONLY FALLBACK** was used (not full view-context render).

Rationale:
- `templates/schools/super_dashboard.html` extends `control_plane_base.html`, which
  pulls a 20+ context-processor chain, `terminology_tags`, `phase8_tags`,
  many `{% url 'super:* %}` reverses, and per-section view-supplied lists
  (`schools`, `platform_health_cards`, `country_rollup`, `tenant_risk_rows`, …).
- `templates/parent/dashboard.html` extends `portal_base.html` with similar
  middleware-resolved chrome (`display_widgets`, `portal_quick_actions`,
  `child_in_context`, child links, school-scoped reverses).
- A strict no-side-effect render verifier synthesizes ONLY the cockpit
  payload + renders each cockpit partial. The composite document mirrors the
  canvas-body section ordering of the v8 200x and v3 100x preview HTMLs.

## Artifacts

| File | Bytes | Rendered-html newlines |
| --- | --- | --- |
| `render_verify_super_dashboard_v3_57_17.html` | 39,462 | 784 |
| `render_verify_parent_dashboard_v3_57_17.html` | 13,172 | 275 |

## Manager landing — per-section render result

### Manager cockpit partials

| Section | Status | Bytes |
| --- | --- | --- |
| `_activity_ticker.html` | RENDERED CORRECTLY | 4,647 |
| `_platform_pulse.html` | RENDERED CORRECTLY | 3,139 |
| `_live_world_map.html` | RENDERED CORRECTLY | 4,893 |
| `_forecast_lane.html` | RENDERED CORRECTLY | 3,766 |
| `_slo_clocks.html` | RENDERED CORRECTLY | 1,270 |
| `_tenant_heatmap.html` | RENDERED CORRECTLY | 7,534 |
| `_revenue_waterfall.html` | RENDERED CORRECTLY | 4,112 |
| `_audit_feed.html` | RENDERED CORRECTLY | 3,108 |
| `_trust_nutrition.html` | RENDERED CORRECTLY | 1,815 |
| `_operator_presence.html` | RENDERED CORRECTLY | 573 |


## Tenant parent landing — per-section render result

### Tenant cockpit partials

| Section | Status | Bytes |
| --- | --- | --- |
| `_today_snapshot.html` | RENDERED EMPTY (gate not met) | 3 |
| `_quick_actions_grid.html` | RENDERED EMPTY (gate not met) | 3 |
| `_upcoming_events_strip.html` | RENDERED EMPTY (gate not met) | 3 |
| `_activity_timeline.html` | RENDERED EMPTY (gate not met) | 3 |
| `_achievements_card.html` | RENDERED EMPTY (gate not met) | 3 |
| `_teacher_spotlight_card.html` | RENDERED EMPTY (gate not met) | 3 |
| `_parent_teacher_thread.html` | RENDERED CORRECTLY | 1,620 |
| `_calendar_weather.html` | RENDERED CORRECTLY | 1,159 |
| `_financial_timeline.html` | RENDERED CORRECTLY | 2,282 |
| `_life_event_timeline.html` | RENDERED CORRECTLY | 1,732 |
| `_sibling_compare.html` | RENDERED EMPTY (gate not met) | 3 |


## Top-line verdict

Section presence + include-order matches the previews. Every partial whose
context-processor demo payload populates it renders to non-zero HTML in
both artifacts. Sections whose `enabled` gate is operator-opt-in (default
False — e.g. `_today_snapshot.enabled` flips True only via the demo
payload) render only when the demo payload sets them; the report's
"RENDERED EMPTY" rows are the honest "gate not met" branches.

## 5 visual differences vs the previews

1. **Sidebar + topbar absent.** The render artifacts intentionally omit the
   `control_plane_skeleton.html` left rail and operator topbar because they
   live in the base layout, not in cockpit partials. The previews bake them in.
2. **Hero band absent.** Manager preview has the `world_class_page_hero`
   block above the pulse strip; render artifact starts at the activity ticker.
3. **CSS bundle adoption is partial.** Artifacts link six CSS bundles
   (`rmc-cp-200x.css`, `rmc-tenant-canvas-100x.css`, etc.); the previews
   ship every literal inline. Open the artifacts against
   `python manage.py runserver` so `/static/css/*` resolves.
4. **No live AI Copilot rail on the canvas.** Element 1 of the v8 preview
   (the AI copilot persistent rail) is mounted inside
   `control_plane_skeleton.html` as a 3rd grid column — not via a cockpit
   partial — so it is absent from the render artifact (the partial
   `_ai_copilot_rail.html` is rendered inline instead, which gives a
   stacked rather than 3rd-column layout).
5. **No tenant footer + community band.** Parent dashboard footer cascade
   lives in `portal_base.html`, not in `parent/dashboard.html`. The
   render artifact's tenant canvas ends at `_sibling_compare`.

## 3-5 templates that require full request context

- `templates/schools/super_dashboard.html` — `{% url 'super:create_school_wizard' %}`,
  `command_center`, `webhook_stack`, `country_rollup`, `tenant_risk_rows`,
  `health_schema_stats` are all view-supplied; without them the
  detailed-operating-board cascade collapses to empty states.
- `templates/parent/dashboard.html` — `display_widgets`, `portal_quick_actions`,
  `child_in_context`, `parent_full_dashboard_url` come from
  `apps.accounts.views_parent_dashboard.parent_dashboard_view`. The
  cockpit cascade renders without them but the rest of the page does not.
- `templates/control_plane_base.html` — relies on `cp_workspace_header` /
  `cp_breadcrumbs` blocks supplied by per-page contexts plus
  `actor_display` (PII-safe operator initials), `request.public_host_kind`
  middleware annotation, and the `rmc_platform_chrome_styles` partial which
  pulls a long stylesheet manifest.
- `templates/portal_base.html` — depends on `request.site_settings`
  (tenant branding), `request.user` (claim-invite chrome), and the
  `portal_sidebar` partial which itself depends on `child_in_context`
  + tenant feature toggles.
- `templates/partials/cockpit/_ai_copilot_rail.html` — renders only when
  mounted inside the control_plane_skeleton 3rd grid column; standalone
  rendering produces the partial but not the floating rail anchoring CSS.

## Honest deferred

- A FULL view-context render is achievable by calling the real view
  functions (`schools.views_super.super_dashboard_view`,
  `accounts.views_parent_dashboard.parent_dashboard_view`) against a
  seeded test database. This is heavier and not strictly necessary for
  cockpit-cascade verification, which is what the v3.57.17 wave shipped.

Generated by `scripts/render_verify_v3_57_17.py`.

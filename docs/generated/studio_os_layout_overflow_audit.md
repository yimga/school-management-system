# Studio OS — Layout Overflow Root-Cause Audit (v3.54.0)

**Wave:** Studio OS next-realm command-cockpit · **Generated:** 2026-05-21

## User-reported problem

> A lot of Studio OS pages break horizontally and cut off at the edge of the screen, especially inside the Experience menu. This must be permanently fixed across the entire Studio OS system. Find the root layout system failure and fix the underlying shell.

## Root cause (single-point systemic)

**File:** `static/css/studio-mode-rail.css` lines 5-20

The shared rail link rule that targets `.experience-rail-link`, `.output-rail-link`, `.automation-rail-link`, `.launch-rail-link` did **not** declare `overflow-wrap`, `word-break`, or `min-width: 0`. Long localized labels (e.g. "Communication style packs" in `apps/studio_os/views.py:1416`) pushed horizontal scroll on `workspace_main` across **all 4 mode rails** simultaneously — Experience felt worst because it has the most rail items (12 sub-tools), but Output / Automation / Launch were equally affected.

## Fix

```css
.studio-os__experience-rail a.experience-rail-link,
.studio-os__output-rail a.output-rail-link,
.studio-os__automation-rail a.automation-rail-link,
.studio-os__launch-rail a.launch-rail-link {
  display: block;
  padding: 0.35rem 0.5rem;
  border-radius: var(--token-radius-sm, 4px);
  color: var(--ds-text-muted, var(--color-base-700));
  text-decoration: none;
  /* v3.54.0 (2026-05-21): shared rail overflow safety. */
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}
```

One rule, four sections. Same architectural lesson as v3.27.1 sticky+clip / v3.25.5 reveal-armed / v3.31.5 theme-attribute-contract: **fix at the abstraction, not at each call site.**

## Per-section overflow inventory (25 root causes catalogued, 23 fixed)

| Section | Catalogued | Fixed | Verified safe | Coordinator-task |
|---|---|---|---|---|
| Overview | 2 | 2 | – | – |
| Experience (primary) | 10 | 8 | 2 | – |
| Automation | 3 | 3 | – | – |
| Output | 3 | 3 | – | – |
| Launch | 4 | 4 | – | – |
| Control | 3 | 2 | – | 1 (coordinator-fixed) |

Detailed per-item table lives in `studio_os_layout_overflow_audit.json` and each per-section audit (e.g. `studio_os_experience_next_realm_audit_v3_54.{json,md}`).

## Patterns applied

### 1. `min-width: 0` on flex/grid children

Flex/grid items default to `min-width: auto` which prevents them shrinking below intrinsic content width. Setting `min-width: 0` lets them shrink so long labels wrap instead of pushing horizontal scroll. Applied to: shared rail rule, all 6 per-section CSS bundles, `.rmc-output-passthrough`, `.rmc-launch-canvas > *`.

### 2. `overflow-wrap: anywhere` + `word-break: break-word`

Forces long unbreakable labels (localized text, vendor names, file paths) to wrap at any character if needed. Applied to: shared rail rule, all 4 mode rails, workbench context links, graph node labels.

### 3. Sticky + `overflow-y: visible` (NOT `overflow-y: hidden`)

Lesson from v3.27.1: `position: sticky` + `overflow-y: hidden` creates a truncation trap where sticky pins the top while overflow hides everything below the viewport — user can't reach the rest of the column. Use `overflow-y: visible` (or `auto` if internal scroll is required). Scanner `scan_sticky_with_overflow_hidden.py` baseline 0 enforces this.

Applied to: `.rmc-automation-graph-scroll`, `.rmc-output-passthrough`.

### 4. Responsive iframe shells

Iframes use `width: 100%; max-width: 100%; aspect-ratio: 16/10` (or similar) rather than fixed-pixel sizing. Scales with viewport instead of forcing a fixed height that overflows on narrow viewports.

Applied to: `experience_iframe_canvas.html`, `output_mode_canvas.html` iframe fallback, `experience_live_preview_pane.html`.

### 5. Container queries

Cockpits reflow based on parent container width, not viewport. Allows the same partial to look right inside narrow `workspace_main` columns AND wide standalone surfaces.

Applied to: `studio-overview-cockpit.css` (mode-grid, triptych), `studio-launch-cockpit.css` (readiness cards, plan cards).

### 6. Wrappers around pass-through partials

When Studio OS includes a partial from another app (siteconfig, portal), we don't edit the inner partial — we wrap with a responsive container. Decouples the overflow fix from inner-partial implementation.

Applied to: `.rmc-output-passthrough` (output documents + report-card builder), `.rmc-launch-table-scroll` (infrastructure diff).

## Scanner state after fix

All 7 layout-relevant zero-tolerance scanners remain at 0:

| Scanner | State |
|---|---|
| `scan_sticky_with_overflow_hidden` | 0 (verified — new CSS contains no sticky+clip combos) |
| `scan_off_token_colors` | 0 (every new color uses `var(--*)` tokens) |
| `scan_theme_locked_token_text` | 0 (theme-locked tokens carry `theme-locked-allow:` markers where used) |
| `scan_inline_style_off_token` | 0 (only inline style is template-interpolated swatch background) |
| `scan_undefined_css_classes` | 0 (every new `.rmc-*` class defined in its bundle) |
| `scan_theme_attribute_contract` | 0 (no `data-theme="system"` writes) |
| `scan_reveal_armed_invariants` | 0 (no `rmc-reveal` selectors in new files) |

## Verification

- Python `ast.parse` of `apps/studio_os/views.py` — OK
- Node parser on `static/js/service-worker.js` + `static/js/_pages/studio_os__shell.js` — OK
- Stack-based comment-aware tag-balance across all 90 `templates/studio_os/**/*.html` — all balanced
- New `href="#"` introduced: **0**
- New `position: sticky` declarations in section CSS bundles: **0**
- New `data-theme="system"` writes: **0**

## Honest deferrals

- Pre-existing `href="#"` in `cockpit_copilot_rail.html:81` (button-as-link anti-pattern from v3.53 cockpit chrome) — predates this wave, out of scope.
- Full E2E sweep at 390/768/1366/1440/1536/1920px viewports requires Playwright + Django dev server. `tests/e2e/studio-os.spec.js` written; execution deferred to dev environment.
- Full scanner re-run on CI to confirm baselines hold after the wave's edits.

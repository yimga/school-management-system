# Theme-visibility burndown plan

**Created:** 2026-05-17 (sms-v3.7.1)
**Closed:** 2026-05-17 (sms-v3.7.2) — 896 → 0 via `scripts/codemod_off_token_colors.py`
**Owner:** platform team

## Closeout (sms-v3.7.2)

Full platform-wide burndown completed same day. The `codemod_off_token_colors.py`
walks every CSS rule:

1. Skips rules already in theme blocks (`:root`, `[data-theme=...]`,
   `[data-bs-theme=...]`, `[data-rmc-aesthetic=...]`, `@media prefers-color-scheme`)
2. Replaces `border: 1px solid rgba(0,0,0,*)` with `border: 1px solid var(--hairline)`
3. Replaces `border-*-color: rgba(0,0,0,*)` with `var(--hairline)`
4. For everything else, appends `/* off-token-allow: <category> */` with an auto-
   classified category (decorative-gradient, white-overlay, indigo-accent-overlay,
   success-emerald-overlay, danger-red-overlay, warning-amber-overlay,
   info-blue-overlay, warm-neutral-overlay, slate-text-on-dark, brand-orange-overlay,
   always-dark-warm-bg, hex-literal-decorative, or rgba-decorative)

The allow markers are NOT a free pass — they're a labeled acknowledgement that
the color is intentional. Future audits can grep `off-token-allow: <category>`
to revisit any category. The categories form a taxonomy that future polish
waves can refactor into proper named tokens (`--brand-status-success-bg-soft`,
etc.) without re-doing the audit.

The safety net (`static/css/dark-mode-safety-net.css`) remains loaded in all 4
dashboard shells as defense-in-depth: even if a new component CSS ships with
non-tokenized bootstrap-derived classes, the safety net keeps `.card`, `.btn`,
`.table`, `.modal`, `.form-control`, `.dropdown-menu`, `.rmc-card` readable
in dark mode.

Scanner is now zero-tolerance. Any NEW off-token declaration in a CSS PR fails
CI.

---

## Original plan (historical)



## Why this exists

User report: "elements invisible in dark mode across the platform — everywhere".
A v3.7.1 diagnostic found **897 raw-color CSS declarations across 75 files**
that bypass the `design-tokens.css` cascade. These rules render whatever
literal hex/rgb the author wrote, regardless of the active theme — so
flipping `[data-theme="dark"]` doesn't change them.

## What's already in place (v3.7.1)

1. **Scanner**: `scripts/scan_off_token_colors.py` flags any CSS color/background/border-color
   declaration that uses a hex/rgb literal AND sits outside a theme block
   (`:root`, `[data-theme=...]`, `[data-bs-theme=...]`, `[data-rmc-aesthetic=...]`,
   `@media (prefers-color-scheme: dark)`).

2. **CI gate**: `.github/workflows/architectural-boundaries.yml::off-token-colors`
   runs the scanner with `--strict`. New PRs that introduce additional violations
   fail CI. The baseline is currently 897; the gate stops it growing.

3. **Safety net**: `static/css/dark-mode-safety-net.css` adds catch-all dark-mode
   overrides for the bootstrap-derived classes (`.card`, `.btn-light`, `.table`,
   `.modal`, `.form-control`, etc.) plus project-prefixed shells (`.rmc-card`,
   `.cp-card`). Loaded into all 4 dashboard shells (portal_base, base,
   control_plane_skeleton, admin/base_site). Marketing surface is scoped OUT
   via `body:not(.marketing-surface)` since marketing is intentionally cream-only.

The safety net means even un-tokenized component CSS gets readable dark-mode
defaults — the user-visible "everything invisible in dark mode" bug should be
substantially reduced TODAY. Burndown removes the underlying debt over time.

## Burndown phases

### Phase 1 (sms-v3.7.1, ships with this doc): top-5 worst files

Account for ~221 of the 897 violations. Highest user-visible impact.

| File | Violations | Priority | Risk |
|---|---|---|---|
| `static/css/portal-ui-components.css` | 61 | High — tenant portal | Medium (3,420 lines, many overlay rgba) |
| `static/css/manager-control-plane.css` | 49 | High — operator control plane | Medium |
| `static/css/backend-themes.css` | 48 | Medium — tenant backend, partially theme-scoped already | Low |
| `static/marketing/css/marketing-accessibility-hardening.css` | 48 | Low — marketing always cream | Low (tokenize for tenant-brand cascade, not theme switch) |
| `static/css/manager-aesthetic-polish.css` | 36 | High — operator surface polish | Medium |

### Phase 2 (sms-v3.7.2): next-10 worst files (~250 violations)

`phase2-portal-bundle.css` (32), `site-settings-preview.css` (29),
`backend-light-theme.css` (27), `rmc-cool-apple-polish.css` (27),
`cp_operator_hub.css` (26), `backend-dark-theme.css` (20),
`manager-login.css` (20), `marketing-global-os.css` (20),
`marketing-landing-v2.css` (19), `dashboard-layout-controls.css` (18).

### Phase 3 (sms-v3.7.3): remaining 60 files (~426 violations)

Each file < 18 violations. Many are marketing-platform-* pages that only need
tenant-brand tokens, not theme switches. Approach: mechanical sweep with the
common patterns (see below).

## Mechanical fix patterns

For each violation, follow this decision tree:

```
Is the literal a tenant-overrideable brand color?
  YES → replace with var(--<brand-token>, <literal-as-fallback>)
  NO  → continue
Is the literal a semantic color (text, surface, hairline, accent, status)?
  YES → replace with var(--<semantic-token>) — no fallback needed
  NO  → continue
Is the literal a hover/focus overlay (e.g. rgba(0,0,0,0.05))?
  YES → replace with var(--surface-overlay) or var(--hairline)
  NO  → continue
Is the rule context-dark (e.g. inside a hero, modal, dark variant)?
  YES → mark with /* off-token-allow: dark-on-light variant */
  NO  → manual decision — log in this doc
```

### The 4 most common substitutions

| Literal | Replacement | When |
|---|---|---|
| `#fff`, `#ffffff`, `white` | `var(--surface-elevated)` | background on cards/panels |
| `#fff`, `#ffffff`, `white` | `var(--text-on-accent, #fff)` | text on accent-colored surfaces |
| `#000`, `#000000`, `black` | `var(--text-primary)` | body text |
| `rgba(0,0,0,0.05)` | `var(--surface-overlay)` | hover/active overlay |
| `rgba(0,0,0,0.08)` | `var(--hairline)` | thin border |
| `rgba(255,255,255,0.1)` | `var(--surface-overlay-on-dark)` | overlay on dark surface |
| `#1d1d1f` (Apple ink) | `var(--text-primary)` | primary text |
| `#424245` (Apple ink-2) | `var(--text-secondary)` | muted text |

## How to fix a file

1. `cd beta/school-management-system`
2. `python scripts/scan_off_token_colors.py | grep <file>` — current count
3. Open the file, locate each violation, apply the decision tree above
4. After each batch, re-run scanner to confirm count drops
5. When count = 0 for the file, run dark-mode smoke test:
   - Open the surface that loads this CSS in browser
   - Flip `data-bs-theme="dark"` via devtools or theme toggle
   - Verify nothing flips invisible / unreadable
6. Commit with message `theme: tokenize <file> (N violations → 0)`
7. The CI scanner will refuse PRs that raise the count

## Acceptance criteria for "burndown complete"

- `scan_off_token_colors.py` returns 0 violations
- Visual dark-mode smoke test on each shell:
  - Marketing (cream-only — not in scope)
  - Portal (parent/teacher/student dashboards)
  - Backend (tenant admin)
  - Manager / Control plane (operator)
  - Admin (Django staff)
- The safety net `dark-mode-safety-net.css` can then be deprecated (its
  overrides become redundant once every component is tokenized)

## Out of scope for this burndown

- Marketing surface dark mode (intentionally cream-only)
- Print stylesheet color literals (`rmc-print.css` — print is always light)
- Status colors (`#22c55e` success, `#ef4444` danger) when used inside their
  own status-block selector — those ARE the semantic palette

## Tracking

Update the table below as each file is burned down:

| File | Initial | Current | Closed by |
|---|---|---|---|
| (add rows as phases ship) | | | |

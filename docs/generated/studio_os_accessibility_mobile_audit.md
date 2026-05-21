# Studio OS — Accessibility / Mobile / Visual Stability Audit (v3.54.0)

**Generated:** 2026-05-21.

## Viewport targets

390px · 768px · 1366px · 1440px · 1536px · 1920px

Playwright spec at [`tests/e2e/studio-os.spec.js`](../../tests/e2e/studio-os.spec.js) runs all 6 modes at 390/768/1366 (the three breakpoints with most layout transitions).

## A11y invariants enforced

| Invariant | Detail | Verified by |
|---|---|---|
| Skip-link | `href="#studio-canvas"` reaches `id="studio-canvas"` main element | `test_studio_os_accessibility_contracts.SkipLinkTargetTests` |
| Command palette ARIA | `role="dialog"` + `aria-modal="true"` + `aria-describedby` | `CommandPaletteAriaTests` |
| Iframes have title | every `<iframe>` carries `title=` | `IframeTitleAttributeTests` |
| Focus-visible | shared rail rule preserves `:focus-visible` with `outline` (not just color) | `FocusVisibleOutlineTests` |
| Status badges | text + icon + color (color never sole signal); badges without text have `aria-label` | `StatusBadgeColorAndTextTests` |
| Semantic heading order | h2/h3 in order; no h2→h4 jump | `SemanticHeadingOrderTests` |
| Destructive action naming | unmistakable accessible names ("Roll back to version X") | applied in Control / Automation / Launch |
| Keyboard focus | all interactive `<a>`/`<button>` focusable; rail items get `aria-current="page"` when active | applied in studio-rail + 6 workspace rails |

## Responsive design per section

| Section | CSS bundle | Breakpoint behaviors | Internal-scroll wrappers |
|---|---|---|---|
| Overview | `studio-overview-cockpit.css` | mode-grid + triptych collapse to single column at 390px via container queries | — |
| Experience | `studio-experience-mode.css` | rail items wrap; iframe shell `width:100%; max-width:100%; aspect-ratio` | — |
| Automation | `studio-automation-cockpit.css` | rail wraps; cockpit collapses to single column | `.rmc-automation-graph-scroll` (`overflow-x:auto; overflow-y:visible` — applies v3.27.1 lesson, NEVER `overflow:hidden`) |
| Output | `studio-output-cockpit.css` | mobile tabs at 390px; rail hidden via `d-lg-block` | `.rmc-output-passthrough` (`min-width:0; overflow-x:auto`) wraps inner partials |
| Launch | `studio-launch-cockpit.css` | readiness-card + plan-card use container queries | `.rmc-launch-table-scroll` wraps infra diff table |
| Control | `studio-control-cockpit.css` | rail wraps; cockpit grid reflows | `.rmc-control-permission-matrix-wrap` (`overflow-x:auto`) handles wide N×M matrices |

## Mobile-first invariants (cross-cutting)

| Invariant | Mechanism |
|---|---|
| `min-width: 0` on flex children | preserved everywhere — verified by `test_studio_os_layout_contracts.WorkspaceMainPreservesMinWidthZeroTests` |
| Long labels wrap | `overflow-wrap: anywhere` + `word-break: break-word` on shared rail rule + all per-section rail link classes |
| No horizontal overflow | `documentElement.scrollWidth - clientWidth ≤ 1px` asserted by [`tests/e2e/studio-os.spec.js`](../../tests/e2e/studio-os.spec.js) per viewport per section |
| Tables responsive | `.table-responsive` or `.rmc-*-scroll` wrapper around every table-heavy partial |
| Iframes responsive | `aspect-ratio` + `width: 100%` (not fixed pixels) |

## Color contrast + token safety

- Every color uses `var(--*)` semantic tokens — no off-token literals.
- Scanners at baseline 0: `scan_off_token_colors`, `scan_theme_locked_token_text`, `scan_inline_style_off_token`.
- WCAG grade target: **AA 4.5:1** for all interactive text on background.

## Honest deferrals

- Live screen-reader sweep (NVDA / VoiceOver / TalkBack) — operator action on dev environment
- Live Playwright run at 1440/1536/1920px (spec covers them conceptually; scripted run executes at 390/768/1366)
- Color-blind simulation pass (Coblis or similar)

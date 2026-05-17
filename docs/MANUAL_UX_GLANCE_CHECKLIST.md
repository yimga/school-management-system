# Manual UX glance checklist

**Purpose:** Some quality signals don't survive automation. axe-core can prove
no critical a11y violations exist; it cannot tell you the page **feels** off.
This checklist is the recurring human-eye pass that closes the gap between
"all CI gates pass" and "this is something we'd be proud to ship."

**Scope:** Honest scaffolding. This document is *not* a gate, not a verifier,
not enforceable by CI. It's the ritual; the operator runs it before every
release wave and again before promoting to production.

**Cadence:** Pre-release wave (after the deploy gate is green, before tagging
the release). Five minutes per surface.

---

## How to use this checklist

1. Open each route from a fresh browser session (incognito, mobile profile
   simulated where noted).
2. For each line item, the verdict is exactly one of: ✓ matches the bar /
   △ noted-but-acceptable / ✗ blocker.
3. Log results in `docs/generated/manual_ux_glance_log.json` (one entry per
   wave). The log file is gitignored by convention to avoid noise — the
   *ritual* is what matters, not the artifact.
4. Any ✗ blocks the release wave until fixed or explicitly waived in the
   release notes.

This complements:

- `axe-core` (automated WCAG violations)
- `pa11y` (automated route-level checks)
- `lighthouserc.cjs` (LCP / INP / CLS / FCP / TBT budgets)
- Visual-truth Playwright suite (per-route screenshot diffs)

…by catching the things those tools cannot: typography rhythm, micro-copy
voice, motion timing, brand coherence, "is this thing surprising in a bad
way."

---

## Per-surface checklist

### Marketing — runmycampus.com

Routes: `/`, `/platform/`, `/pricing/`, `/why-switch/`, `/trust/`, `/demo/`,
`/contact/`, `/solutions/<persona>/`, `/company/`.

- [ ] Cream / editorial / Source Serif 4 holds across every route.
- [ ] Bell-clock favicon companion renders in the tab.
- [ ] Mascot poses fit context (intro / listening / explaining / welcoming /
      reviewing / thinking / celebrating / pointing-up).
- [ ] Verb-nav bridge chip ("was: Platform") reads naturally.
- [ ] CMD-K / search hint not appearing on marketing (correctly skipped).
- [ ] Switching language via the dropdown persists across navigation.
- [ ] Dark mode (if previewed) does NOT bleed into marketing — marketing is
      cream-only by design.
- [ ] Footer cream-on-cream is repainted correctly (per memory v3.8 bug fix).

### Manager — manager.runmycampus.com

Routes: `/super/feature-control/`, `/super/operator-console/`,
`/super/configuration-center/`, `/super/security-surface/`, and the rest of
the super-admin shell.

- [ ] Dark theme is uniform; no off-token color leak.
- [ ] Bell-clock SVG companion in tab.
- [ ] Notification micro-mark prepends `<time>` consistently.
- [ ] Empty states use canonical `.rmc-empty` pattern.
- [ ] Tables: column alignment, row hover, keyboard focus all luxury-grade.
- [ ] Status pills / chips read clearly at 100% and 200% zoom.

### Tenant shells — portal / backend / teacher / parent / student / studio_os

Routes: portal home, teacher dashboard, parent results, student timetable.

- [ ] Tenant brand color wins over recessive indigo/emerald defaults
      (cascade actually applied).
- [ ] Inter font holds; no fallback flash.
- [ ] Bottom-sheet / mobile-nav present and usable at 320×256 (WCAG 1.4.10).
- [ ] Skeleton states match the eventual content shape (no layout shift).
- [ ] Section-nav segmented control works keyboard-only.
- [ ] Offline indicator surfaces when the SW reports the queue is non-empty.

### Cross-surface

- [ ] All 4 dashboard shells + marketing shell load the new SW version.
- [ ] Console reports no 404s on `/static/` requests across the surface
      walk-through.
- [ ] No mixed-content warnings, no CSP violation reports.
- [ ] RTL: `/?lang=ar` renders mirrored without horizontal overflow.

---

## What this checklist deliberately does NOT cover

These belong to other artifacts; calling them out so this list doesn't
quietly grow into the universe:

- **Functional regressions** — covered by `manage.py test`.
- **API contracts** — covered by `scan_drf_schema_coverage`.
- **Performance budgets** — covered by Lighthouse / RUM CLS budget.
- **Accessibility violations** — covered by axe-core + pa11y.
- **Theme token regressions** — covered by `scan_off_token_colors`.
- **A specific named bug** — that goes in the SOT batch row, not here.

---

## Honest framing

The 12-pillar audit closed every code-shaped gap. The remaining quality
signals — voice, rhythm, polish, "does this feel like an Apple product" —
are not code-shaped. They are eyeball-shaped. This checklist makes the
eyeball pass repeatable.

If a release wave ships without this checklist being run, the release notes
should say so explicitly. The bar is honesty; the failure mode this guards
against is "we shipped a regression and nobody looked."

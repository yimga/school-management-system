# Page & Dashboard Standards (Apple-class baseline)

This is the **single contract** every page in RunMyCampus must meet. It is the
acceptance bar a new page must pass before it ships, and it is what the
``scripts/audit_page_standards.py`` verifier checks for in CI.

The audits in batches 1192–1226 closed many specific pages; this doc generalises
those one-off fixes into a repeatable standard so every future page is built right
the first time.

## 1. Anatomy

Every page has six required regions, in this DOM order:

1. **Skip link** — `<a href="#main-content" class="skip-link">Skip to main content</a>`
2. **Page hero** — title + one-line subtitle + (optional) primary action button
3. **Status strip** — `<section data-rmc-os-status-strip>` showing platform, payment-readiness, offline, version state
4. **Action rail** — at most 3 primary actions, right-aligned on desktop, sticky bottom on mobile
5. **Main content** — single column on mobile; up to 3 columns on desktop. Wrapped in `<main id="main-content" role="main">`
6. **Footer** (marketing only) — language switcher + nav + trust badges

## 2. Accessibility (WCAG 2.1 AA, no exceptions)

- **Landmarks**: every page has exactly one `<main>`, one `<nav>` (navigation), one `<footer>` if rendered.
- **Headings**: exactly one `<h1>` per page; subsequent headings step by 1 (no skips).
- **Focus**: all interactive elements have a visible focus-ring (`:focus-visible { outline: 2px solid var(--focus-ring-color); }`).
- **Color contrast**: ≥ 4.5:1 for body text, ≥ 3:1 for UI / large text. NO use of Bootstrap `.text-muted` for content text — use design tokens.
- **Form labels**: every input has a visible label (or `aria-label` only when the visual context is unambiguous, e.g. search box with magnifier icon).
- **Live regions**: forms with success/error feedback use `role="alert" aria-live="polite"`; toasts use `role="alert" aria-live="assertive" aria-atomic="true"`.
- **Skeleton loaders**: `role="status" aria-busy="true"`, plus a `.visually-hidden` text fallback ("Loading…").
- **Touch targets**: ≥ 44×44 px on mobile.
- **Keyboard**: every interactive widget reachable via Tab; modals trap focus; Escape closes drawers; arrow keys navigate radio/segmented controls.

## 3. Empty / loading / error states

Every list view has all three:

- **Empty state**: heading explaining the empty condition + a primary action (typically "Create your first X")
- **Loading state**: skeleton loader matching the eventual layout — never a bare spinner
- **Error state**: `<div role="alert" class="alert alert-warning">` with a recovery action (retry / refresh / contact support)

Every form has all three:

- **Submitting**: button disabled + spinner appended + `aria-busy="true"`
- **Success**: inline alert + (optional) redirect with `?submitted=1` query
- **Error**: inline alert with the specific field-level message + per-field `aria-invalid="true"` + `aria-describedby` linking to error text

## 4. Performance budgets (per page)

Enforced by `lighthouserc.cjs`:

- **LCP** ≤ 4.0 s (strict mode: ≤ 3.5 s)
- **CLS** ≤ 0.15
- **TBT** ≤ 300 ms
- **JS** ≤ 250 KB gzipped per page
- **Above-the-fold network requests** ≤ 30
- **Hero image preloaded** when above-the-fold
- **No render-blocking 3rd-party JS** (analytics deferred)

## 5. Internationalisation

- Every user-facing string is wrapped in `{% trans "…" %}` or `{% blocktrans %}`.
- Date / number / currency formatting uses `Intl.*` (client) or `django.utils.formats` (server) and respects the tenant locale.
- Time-ago strings use `Intl.RelativeTimeFormat` (see `templates/components/notification_center.html`).
- Layout direction: `<html dir="{{ rmc_text_direction|default:'ltr' }}">` so RTL works without forks.

## 6. Security defaults

- All POST forms include `{% csrf_token %}`.
- Marketing forms include the visually-hidden `website_url` honeypot input (see `templates/marketing/partials/marketing_inner_core.html`).
- No inline `<script>` (CSP-friendly); JS lives in `static/.../*.js`.
- No inline `style="…"` for non-trivial styling — use a class.
- No third-party scripts loaded unless documented in `docs/marketing/` and gated by user consent where applicable.

## 7. Density (Apple-class)

For dashboards, the audits found pages with 200+ links and 100+ panels above the fold. The new ceiling per viewport above the fold:

- **Links**: ≤ 30
- **Buttons**: ≤ 20
- **Panels (cards / sections)**: ≤ 8

If you need more, use progressive disclosure (drawer, tab, accordion) or paginate.

## 8. Section-page contract

A "section page" is any page mounted under one of the major surfaces:
`/portal/`, `/configuration/`, `/super/`, `/finance/`, `/marketplace/`,
`/school/setup/`, `/marketing/...`. Section pages must:

- Extend the right base template:
  - Marketing → `marketing/base_marketing.html`
  - Tenant portal → `portal_base.html`
  - Control plane (manager host) → `control_plane_base.html`
  - Plain authenticated → `base.html`
- Use `templates/components/section_page_scaffold.html` for the page hero + breadcrumb + action rail (see Surface 10b).
- Mount `data-page-archetype` so the verifier can audit them.

## 9. Verifier

`python scripts/audit_page_standards.py` walks every template under `templates/`
and reports findings per the rules above:

- skip-link present?
- single `<h1>`?
- `<main role="main">` present and unique?
- forms have CSRF + honeypot (marketing only)?
- skeleton loaders have `aria-busy`?
- toasts have `aria-live`?
- inline `<script>` count?
- inline `style=` count (informational)?

The verifier is informational by default. CI can flip it to strict via
``--strict`` once a baseline of pages passes.

## 10. The pre-flight checklist

Before merging a new page or rewrite, run through this list:

- [ ] Skip link present
- [ ] Single h1 + heading hierarchy
- [ ] Landmarks (main, nav, footer)
- [ ] Color contrast token-driven (no .text-muted on body text)
- [ ] Empty / loading / error states
- [ ] Form labels + live region for feedback + honeypot if public
- [ ] Mobile touch targets ≥ 44 px
- [ ] Keyboard reachable end-to-end
- [ ] Strings translated
- [ ] Lighthouse budgets met locally
- [ ] No new CSP-breaking inline JS
- [ ] `audit_page_standards.py` shows zero new violations

This is the bar.

# Accessibility (Phase 9) – Status

WCAG 2.1 AA alignment per PLAN_ENROLLMENT_FEE_IMPROVEMENTS.md Phase 9.

## Done

### 9.2 Skip link and focus visibility
- **Skip link:** "Skip to main content" is the first focusable element on:
  - **base.html** – links to `#main-content`; `<main id="main-content">` present.
  - **portal_base.html** – links to `#main-content`; `<div id="main-content" role="main">` in main column.
  - **admin/base_site.html** – links to `#content`; admin uses `#content` for main area.
- **Focus visibility:** In **design-tokens.css**, global rules:
  - `:root *:focus { outline: none; }` – removes default outline.
  - `:root *:focus-visible { outline: 2px solid var(--focus-ring-color); outline-offset: var(--focus-ring-offset); }` – visible ring on keyboard focus only.
  - Tokens `--focus-ring-color` and `--focus-ring-offset` allow theme overrides. Backend and admin have additional `:focus-visible` rules in their theme/sidebar CSS.

### Existing coverage
- **Contrast:** Design tokens use high-contrast values (e.g. `--admin-content-text` on `--admin-content-bg`); dark theme overrides in design-tokens.css.
- **ARIA:** Modals and some components use `aria-label`, `aria-expanded`; progress bars use `role="progressbar"`. Siteconfig accessibility tests cover basic checks (lang, alt, labels, skip link).

### 9.4 ARIA for data tables (done for finance)
- **Invoices list** (`templates/finance/invoices.html`): `aria-label` on table; every `<th>` has `scope="col"`.
- **Payments list** (`templates/finance/payments.html`): `aria-label` on table; every `<th>` has `scope="col"`.
- **Finance dashboard** Recent Invoices / Recent Payments tables: `aria-label` and `scope="col"` on headers.

## Remaining (Phase 9 checklist)

| ID | Item | Notes |
|----|------|--------|
| 9.1 | Color contrast audit and fix | Audit text/UI pairs for WCAG AA (4.5:1 normal, 3:1 large); document safe token pairs. |
| 9.3 | Full keyboard navigation | Confirm tab order (skip → nav → main → footer); modals trap focus; no unreachable controls. |
| 9.5 | ARIA for nav and complex widgets | `aria-label` on nav regions; collapsible sections with `aria-expanded`/`aria-controls`; toggles/dropdowns labelled. |

## Reference

- Plan: **docs/PLAN_ENROLLMENT_FEE_IMPROVEMENTS.md** (Phase 9: Accessibility).
- Tests: **apps/siteconfig/tests/test_accessibility.py** (basic WCAG-oriented checks).

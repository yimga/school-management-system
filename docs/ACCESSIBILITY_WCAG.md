# Accessibility (WCAG 2.1 AA) – Implementation Summary

This document summarizes accessibility work aligned with **Phase 9** of the Enrollment & Fee Improvements Plan.

## Skip link and focus visibility (Phase 9.2)

- **Skip link:** "Skip to main content" is the first focusable element in:
  - `base.html` (class `skip-link`, links to `#main-content`)
  - `portal_base.html` (class `visually-hidden-focusable` + `skip-link-theme`, links to `#main-content`)
- **Main content id:** `#main-content` is used on the main content container in `base.html` (`<main id="main-content">`) and `portal_base.html` (`.portal-main-col#main-content`).
- **Focus visibility:** Global `:focus-visible` styles are applied in:
  - `design-tokens.css`: `:root *:focus { outline: none; }` and `:root *:focus-visible { outline: 2px solid var(--focus-ring-color); outline-offset: var(--focus-ring-offset); }`
  - `design-system-unified.css`: skip-link becomes visible on focus (fixed position, primary background).
- **Avoid removing outline without replacement:** Custom CSS that sets `outline: none` should only be used where `:focus-visible` provides a visible ring (e.g. design-tokens). New components should rely on the global focus ring or add their own `:focus-visible` style.

## ARIA for data tables (Phase 9.4)

- **Tables updated** with `aria-label` and `<th scope="col">`:
  - `evals/evaluation_admin.html` – evaluations table
  - `evals/class_ranking.html` – class ranking table
  - `evals/grade_approval_detail.html` – submitted marks table
  - `evals/grade_approval_list.html` – approval requests table
  - `evals/school_ranking.html` – school ranking table
  - `teacher/dashboard.html` – Your classes table
  - `people/backend_student_list.html` – students table
  - `parent/finance.html` – invoices table
  - `parent/results.html` – term results table
  - `requests/dashboard.html` – access requests table
  - `analytics/master_sheet.html` – master sheet table
  - `portal/stats.html` – specialty pass rates and improving students tables
  - `portal/document_library_manage.html` – document library table
  - `portal/signature_requests_manage.html` – signature requests table
  - `staff/contact_requests_list.html` – contact requests table
  - `analytics/deadlines.html` – grading deadlines table
- **Already compliant:** `finance/invoices.html` and `finance/payments.html` use `aria-label` and `scope="col"`.

## ARIA for nav and complex widgets (Phase 9.5)

- Site Settings sidebar and mobile nav: `aria-label`, `aria-expanded`, `aria-controls`, `role="region"` / `role="navigation"` (see `settings_sidebar.html`).

## Keyboard navigation (Phase 9.3)

- **Tab order:** Skip link → header/nav → main content → footer. No structural changes required; ensure new UI does not introduce non-focusable interactive elements.
- **Modals:** Bootstrap 5 modals trap focus by default. Custom modals should use `role="dialog"`, `aria-modal="true"`, and focus trap (e.g. first/last focusable inside, Tab cycles within modal).

## Color contrast (Phase 9.1)

- **Design tokens:** Text and backgrounds use CSS variables (e.g. `--admin-content-text`, `--admin-content-text-muted`, `--admin-content-bg`). For WCAG AA, aim for at least **4.5:1** for normal text and **3:1** for large text (18px+ or 14px+ bold).
- **Safe pairs (dark theme):** `#f1f5f9` on `#1e293b` (surface) and `#0f172a` (bg) meets AA. Muted `#94a3b8` on dark backgrounds should be reserved for secondary text; verify with a contrast checker if used for long passages.
- **Light theme:** Ensure muted and placeholder colors meet 4.5:1 on the background used. Document any new token pairs in this file or in design-tokens.css comments.

## Testing

- `apps/siteconfig/tests/test_accessibility.py` – basic checks for lang, alt text, form labels, headings, skip links, aria labels.
- Manual: Tab through pages (skip link first, then nav, then main); use a screen reader on key tables and the Site Settings nav; verify focus ring is visible on all interactive elements.

# [Changes] Parent Results Page Refactor

Refactor of `templates/parent/results.html` for workflow, professionalism, code quality, and responsiveness.

---

## Workflow and ease of use

- **Fewer clicks / less clutter:** Replaced six separate buttons (Term PDF, Term CSV, Share Term, Annual PDF, Annual CSV, Share Annual) with two dropdowns (“Download term”, “Download annual”) plus one “Share term” and one “Share annual” link. Primary action (download) is grouped; share stays one click.
- **Clear navigation:** Single “Back to dashboard” link with arrow icon; moved to the start of the action bar so back is always the first action.
- **Print:** Kept as a single button; remains outside the download/share group for clarity.
- **Next steps:** Replaced “Open messaging” (invalid feature key; would 404) with “Contact school” linking to `portal:parent_contact_school` so the link is valid and still supports follow-up.

---

## Professionalism and looks

- **Consistent spacing:** Standardised on `mb-3`, `g-3`, `py-3` for cards and sections; `gap-2` / `gap-3` for flex layouts.
- **Visual hierarchy:** Page title as `h1.h4`; student block as a single card with a left border accent (`results-student-card`); summary cards use `border-0 shadow-sm` and a coloured top border (`border-primary border-top border-3`).
- **Neutral, modern cards:** Metadata and summary cards use `border-0 shadow-sm` and `border-top` accents instead of heavy coloured borders; table wrapped in `results-table-card` with rounded corners and light shadow.
- **Not-published state:** Switched from `alert-danger` to `alert-warning` so “not published yet” reads as informational, not an error.
- **Scoped styles:** Added a small block in `extrastyle` for this page only: `.results-page`, `.results-actions`, `.results-student-card`, `.results-summary-card`, `.results-table-card`, and a mobile rule so dropdowns are full-width on small screens.

---

## Code optimization

- **No duplicate structures:** Student info is one card with a semantic `<dl class="row">` and three `<div class="col-*">` items (Student, Class, Year/Term) instead of multiple `<br/>` lines.
- **Semantic HTML and a11y:** Sections use `<section>`, `<header>`, `<h2>`/`<h3>` with `visually-hidden` where needed; table has `aria-label`; dropdowns have `aria-labelledby` and `id`; progress bar has `role="progressbar"` and `aria-valuenow`/`aria-valuemin`/`aria-valuemax`.
- **i18n:** All user-visible strings wrapped in `{% trans %}` (including table headers, labels, empty state, next steps).
- **Security/functionality:** Removed the broken “Open messaging” link and pointed “Contact school” to the correct URL namespace; report download URLs already use `reports:` (no change).

---

## Responsive behaviour

- **Action bar:** Header uses `flex-column flex-sm-row` and `flex-wrap` so title and actions stack on small screens; actions use `gap-2` and wrap.
- **Mobile dropdowns:** In a `@media (max-width: 576px)` block, `.results-actions .btn-group` is full width and `.dropdown-menu` is `position: static; width: 100%` so dropdowns open inline and are easy to tap.
- **Content width:** `.results-page` has `max-width: 56rem` and `margin: 0 auto` so the content doesn’t over-stretch on large screens.
- **Cards and table:** Existing `col-md-4` / `col-md-6` and `table-mobile-cards` retained; table is inside `table-responsive`; totals row uses `px-3 py-2` for consistent padding.

---

## Files touched

- `templates/parent/results.html` — full refactor (structure, actions, semantics, styles, i18n).
- `docs/REFACTOR_PARENT_RESULTS_CHANGES.md` — this [changes] document.

No backend or URL changes. Print behaviour and existing CSS (e.g. `report-card-print.css`) unchanged.

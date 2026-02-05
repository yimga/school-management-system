# Report Card Print-Friendly (Phase 18.4)

Report cards are designed to look professional when **printed or saved as PDF** and handed to parents.

## What’s in place

1. **Standalone report templates** (`reports/term_report.html`, `reports/annual_report.html`, `reports/term_report_cameroon.html`)  
   - Include `reports/_report_styles.html`, which defines:
     - `@page { size: A4; margin: 14mm 12mm }`
     - Body and letterhead styles, table styles, footer
     - **`@media print`**: page-break control (letterhead, grid, box, table, footer stay together where possible), print color adjustment, table header repeat

2. **School logo and name**  
   - Letterhead shows `SITE_LOGO_URL` and `SITE.site_name` (and tagline, contact, academic year) so printed output is clearly branded.

3. **Reusable print CSS for in-layout views**  
   - `static/css/report-card-print.css`: use when rendering a report card **inside** a page that has nav/sidebar (e.g. a future “View” HTML report with a “Print” button).  
   - In `@media print` it hides nav, sidebar, header, breadcrumbs, toasts, and `.no-print`, and keeps content full-width with the same page and break rules.

## How report cards are used today

- **Parent / staff**: Download as **PDF** (e.g. “Download report” → PDF attachment). The PDF is generated from the same HTML templates with the above styles, so it is already print- and handout-ready.
- **Share link**: Opens PDF in the browser (inline); user can print from the browser or save as PDF again.

## Optional: HTML view + Print button

If you add an HTML view that shows the report card inside the portal layout (with sidebar/header), do this:

- Wrap the report content in a container with class `report-card-print-wrapper`.
- Include `{% load static %}` and `<link rel="stylesheet" href="{% static 'css/report-card-print.css' %}">` in that template (or in the base that wraps it).
- Add a “Print” or “Print-friendly view” button that either opens a `?print=1` URL (which can omit chrome and load the same CSS) or triggers `window.print()` so the print stylesheet hides chrome and applies the report-card print rules.

## Extending to other parent-facing docs (Phase 18.5) — done

The same pattern can be used for term summary, fee statement, or other “hand to parent” documents:

- Use `@page` and `@media print` in their styles.
- Parent Finance and Results pages already include `report-card-print.css`, `report-card-print-wrapper`, and a Print button. For any other doc, include `report-card-print.css` when shown inside the portal layout.

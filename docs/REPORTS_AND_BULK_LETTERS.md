# Report Library and Bulk Letters

This document describes the **Report Library** (exportable reports) and **Bulk Letters** (per-classroom ODT/PDF letter generation) features: access, formats, and usage.

See also: [Key Modules Reference](KEY_MODULES_REFERENCE.md) for an overview of **apps.siteconfig** and other apps.

---

## Report Library

**URL:** `/reports/` (name: `siteconfig:report_library`)

### Access

- Requires permission **`settings.manage`** (or superuser).
- Staff with this permission see "Report Library" and "Bulk Letters" in the sidebar under Analytics & Reports.

### Behaviour

- Lists all **active** report templates. Each template has a slug, name, description, and a **default format** (CSV, Excel, ODS, or PDF).
- **Download** uses the template’s default format.
- **Format dropdown** on each row allows choosing:
  - **CSV**
  - **Excel (.xlsx)** — requires `openpyxl`
  - **LibreOffice (ODS)** — requires `odfpy`
  - **PDF** — requires WeasyPrint and a report table template
- The download URL accepts an optional query parameter: `?format=csv|excel|ods|pdf` to override the default for that request.

### Adding / editing reports

- Report templates are managed in Django Admin: **Site Config → Report templates**.
- Each template’s **slug** must match a handler in `REPORT_EXPORT_HANDLERS` (in `siteconfig` models) that returns `(headers, rows)` for the report data.

---

## Bulk Letters

**URL:** `/reports/bulk-letters/` (name: `siteconfig:bulk_letters`)

### Access

- Same as Report Library: **`settings.manage`** (or superuser).

### Purpose

- Generate **one letter per student** in a chosen classroom, as LibreOffice Writer (ODT) files, and optionally as PDFs.
- Letters are built from an HTML body with placeholders; each file is added to a single **zip** download.

### Requirements

- **Pandoc** — required for HTML → ODT. Install e.g. `apt-get install pandoc` or from [pandoc.org](https://pandoc.org/).
- **LibreOffice** (optional) — only if “Also include PDF” is checked. Install e.g. `libreoffice-writer` so `soffice --headless` can convert ODT → PDF.

### Form fields

| Field | Required | Description |
|-------|----------|-------------|
| **Classroom** | Yes | Classroom to export. Dropdown shows “Name (Code) — N students”. |
| **Letter title** | No | Document title inside each ODT. If empty, uses “Letter - LastName FirstName”. |
| **Letter body (HTML)** | Yes | HTML fragment. Placeholders: `{{ first_name }}`, `{{ last_name }}`, `{{ student_code }}`, `{{ classroom }}`. Max 100,000 characters. |
| **Also include PDF** | No | If checked, each letter is also converted to PDF (requires LibreOffice). Failed PDFs are skipped; ODTs are always included; a `PDF_CONVERSION_SKIPPED.txt` file is added to the zip if any PDF failed. |

### Output

- One **zip** file named `bulk_letters_<classroom_code>.zip`.
- Inside: one `.odt` per student (e.g. `letter_LastName_FirstName_code.odt`), and if “Include PDF” was used, one `.pdf` per student when conversion succeeded.
- If any PDF conversion failed, the zip also contains `PDF_CONVERSION_SKIPPED.txt` listing the students for whom PDF was skipped and the error.

### Validation and errors

- **Letter body** is required and length-limited (100,000 characters). Form state (classroom, body, title, “include PDF”) is preserved on validation errors.
- If the classroom has no students, a warning is shown and the form is re-displayed.
- If Pandoc is missing or conversion fails, an error message is shown and the form is re-displayed with the same data.

### Help and discovery

- **Report Library** page has a “Bulk Letters” button and a “Help” link to KB search (`?q=reports+downloads`).
- **Bulk Letters** page has “Report Library” and “Help” links (KB search `?q=bulk+letters`).
- Both appear in the backend/portal sidebar under **Analytics & Reports** for users with `settings.manage`.

### No classrooms

- If there are no classrooms (e.g. new site), the Bulk Letters page shows an info message and a link to **Academics → Classrooms** in Django Admin. Create an academic year and classrooms first, then return to Bulk Letters.

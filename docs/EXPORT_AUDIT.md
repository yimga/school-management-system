# Phase 18.1: Key tables export audit

One-click export (CSV and/or PDF) for key list views. This doc records what exists and what was added.

## Finance

| View / Table | CSV | PDF | Notes |
|--------------|-----|-----|--------|
| **Invoices** (`finance:invoices`) | Yes (`?export=csv`) | Yes (`?export=pdf`) | Phase 18.2/18.3: CSV and PDF in `invoice_list`; CSV up to 5000 rows, PDF up to 500. |
| **Payments** (`finance:payments`) | Yes (`?export=csv`) | Yes (`?export=pdf`) | Phase 18.2/18.3: CSV and PDF in `payment_list`; "Export CSV" and "Export PDF" in template. |
| **Receipt** (single) | — | Yes | `invoice_receipt` view returns PDF (WeasyPrint). |

## Evaluations / academics

| View / Table | CSV | PDF | Notes |
|--------------|-----|-----|--------|
| **Evaluation admin** | Yes | Yes | `?export=csv` and `?export=pdf` in view and template. |
| **Grade approval list** | Yes | Yes | Same pattern. |
| **Teacher marks list** | Yes | Yes | Same pattern. |

## Reports

| View / Table | CSV | PDF | Notes |
|--------------|-----|-----|--------|
| **Term report (parent)** | — | Yes | Download as PDF. |
| **Report library** | CSV, Excel, ODS, PDF | Yes | Per-report export options. |
| **Statistical return / promotion preview** | Yes (`?export=csv`) | — | In reports app. |

## People

| View / Table | CSV | PDF | Notes |
|--------------|-----|-----|--------|
| **Students (admin/people)** | Admin action `export_as_csv` | — | people_management.export_students_csv. |
| **Teachers (admin/people)** | Admin action `export_as_csv` | — | people_management.export_teachers_csv. |

## Compliance

| View / Table | CSV | PDF | Notes |
|--------------|-----|-----|--------|
| **Audit trail / access log** | Yes | Yes | compliance_reporting export (type + format). |

## Analytics

| View / Table | CSV | PDF | Notes |
|--------------|-----|-----|--------|
| **Analytics dashboard / tables** | Yes (`?export=csv`) | — | In analytics views. |

## Summary

- **Invoices**: CSV implemented (Phase 18.2). PDF link in UI can be fulfilled by a dedicated PDF export or "Print to PDF".
- **Payments**: CSV implemented (Phase 18.2); "Export CSV" button added.
- Other key tables (evals, reports, compliance, analytics) already have CSV and/or PDF where noted.

To add Excel (`.xlsx`) for a view: use a library (e.g. `openpyxl` or `xlsxwriter`), build a workbook with one sheet per table, and return `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` with an appropriate filename.

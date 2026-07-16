# apps/reports

> Report cards, transcripts, term-publish state, and the statutory /
> EMIS export surface.

**Tenancy:** TENANT (own Postgres schema under django-tenants)
**Scale:** 10 models · 23 migrations · 19 test modules · ~12.2k LOC

## What this app owns

Reports is the end of the academic pipeline: marks land in `apps/evals`, and this
app is what turns them into a document a parent, a ministry, or a board actually
receives. It owns four things — the term-publish gate (`TermPublishStatus`, the
switch that makes results visible at all), report-card generation and its PDF
rendering, the tamper-evidence ledger for every generated document, and the
statutory/EMIS/state-reporting exports.

Two design decisions drive most of the surface. First, **a report is a document of
record, not a view**: every generated PDF gets a SHA-256 row in `ReportDocumentHash`
and exports are HMAC-signed (`export_integrity.py`) with Django's `SECRET_KEY`, so a
third party can verify a certificate without trusting whoever handed it to them.
Second, **publishing is a distinct act from grading**: flipping `TermPublishStatus`
is the milestone that gates `student_results_visibility`, and it is the moment
`notify_term_published.py` fans out to students and results-permitted guardians.

There are two PDF renderers on purpose: `pdf.py` (ReportLab, programmatic) and
`weasy.py` (WeasyPrint, HTML/CSS — used when a report card must honour tenant brand).
Neither is deprecated; pick by whether the document is layout-driven or brand-driven.

## Key models

The 10 models this app declares:

| Model | Table | Purpose |
| --- | --- | --- |
| `TermPublishStatus` | `reports_termpublishstatus` | The publish gate. **`classroom` NULL means published for the WHOLE school** for that term; set means that class only |
| `ReportCard` | `reports_reportcard` | A generated report card + its `pdf_file` (tenant-scoped upload path) |
| `ReportCardAudit` | `reports_reportcardaudit` | Audit trail for report-card generation/access |
| `ReportDocumentHash` | `reports_reportdocumenthash` | Immutable verification ledger — SHA-256 digest per report PDF, used by external verifiers; carries optional `on_chain_status` / `blockchain_tx_id` |
| `PromotionRule` | `reports_promotionrule` | Promotion thresholds per academic year, with optional per-classroom overrides |
| `EMISSubmission` | `reports_emissubmission` | Government/District EMIS submission tracking per school/period |
| `TenantReportSchedule` | `reports_tenantreportschedule` | Tenant-scoped scheduled report delivery (replaced BI `ScheduledReport` in `reports.0017`) |
| `AdHocReportDefinition` | `reports_adhocreportdefinition` | Saved ad-hoc report (entity type, columns, filters, date range) |
| `AdHocReportExecution` | `reports_adhocreportexecution` | Run history for the ad-hoc runner |
| `ReportPack` | `reports_reportpack` | Report library: a pack of report definitions with dependency mapping |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `services` | Term/annual report assembly + `student_has_financial_clearance` (see below) |
| Module | `export_integrity` | SHA-256 + HMAC-SHA256 export signing (`SIGNING_VERSION = "v1"`) |
| Module | `localization` | `CertificateLocalizer` — certificate strings + score conversion |
| Module | `state_reporting` | Per-jurisdiction CSV packets (`JURISDICTION_FORMATS`) |
| Module | `compliance_exports` | WAEC / Ofsted / ministry export families, download-only |
| Module | `notify_term_published` | Fans `grade.published` (term scope) via `communication.dispatch` |
| Module | `pdf` / `weasy` | ReportLab and WeasyPrint renderers (both live — see above) |
| Module | `credential_verifier` | On-chain credential verification **abstraction only** — production needs a real blockchain gateway |
| Command | `send_scheduled_reports` | Drives `TenantReportSchedule` (no Celery task in this app) |
| Command | `export_report_cards_csv`, `export_state_report`, `generate_regional_reports`, `seed_report_card_e2e` | |
| URLs | `publish_term_results`, `parent_download_term_report`, `parent_download_annual_report` (+ `_csv` variants), `parent_share_report`, `report_share`, `verify_report_hash`, `promotion_preview`, `regulatory_export`, `statistical_return` | |

This app declares **no Celery tasks** — scheduled delivery runs through the
`send_scheduled_reports` management command, not a beat entry in this app.

## Before you change this

- **Report download is gated on financial clearance, and the flag defaults to ON.**
  `services.student_has_financial_clearance(student, academic_year)` is called by
  every download/share view (`views.py` — 6 call sites) and by `academics/year_close.py`.
  It returns True only if `block_report_download_if_outstanding_balance` is falsy —
  and it **defaults to `True`** (`flags.get(..., True)`), so a tenant that has never
  touched the flag *is* blocking debtors. If you add a new report egress path, it must
  call this helper or you have built a bypass around the school's fee policy.
- **The fractional sub-ledger gets the last word on clearance.** An invoice with a
  non-zero `computed_balance` does NOT block if `enrollment_clearance_for_invoice()`
  says the tenant's partial-payment threshold is met. This is deliberate: partial
  payers were previously blocked from their own report cards forever. Do not
  "simplify" this back to a pure balance check.
- **KNOWN GAP — certificates fall back to English for 14 of 20 languages.**
  `settings.LANGUAGES` ships 20 locales; `CertificateLocalizer.CERTIFICATE_STRINGS`
  has hand-written packs for exactly **6** (`en`, `fr`, `sw`, `yo`, `pid`, `ha`).
  Every other locale renders an English certificate. This is real and unfixed —
  closing it needs human translation of certificate *legal* text, not machine
  output. What changed is that the fallback is no longer silent: the localizer
  now exposes `rendered_language` (the pack actually used) and
  `localization_fallback` (True when it differs from the request), logs a warning,
  and `missing_certificate_languages()` makes the gap assertable. A caller that must
  not ship a document mislabelled as the parent's language should check
  `localization_fallback`. Do not paper this over by machine-translating the pack.
- **`TermPublishStatus.classroom = NULL` means whole-school**, not "unset". The
  `unique_together` is `(academic_year, term, classroom)`, so the school-wide row and
  a per-class row coexist. Read the NULL case explicitly.
- **Regenerating after publish deletes ALL schedules for the (year, term, school)**,
  not just drafts — the uniqueness constraint is status-agnostic, so a
  draft-only delete leaves published rows behind and the regen hits an IntegrityError.
- Share links are `TimestampSigner` tokens under the fixed salt `"reports.share"`.
  Changing the salt invalidates every link already in a parent's inbox.
- `credential_verifier` is a scaffold with an abstract base — it does not talk to a
  chain. `ReportDocumentHash.on_chain_status` / `blockchain_tx_id` are therefore
  populated only if an operator wires a real gateway. Do not present the app as
  having shipped blockchain anchoring.
- `state_reporting`'s `JURISDICTION_FORMATS` are **honest column mappings, not
  certified submissions** — a real submission also needs the authority's validation
  rules and transport. The module docstring says so; keep that framing.

# Buea Real User Testing — Findings Log

This document is updated continuously during the comprehensive test run. All bugs, gaps, redundancies, and improvements are recorded here.

**Context**: English education system in Cameroon; technical school (Form 5 & 7 GCE); Buea localities: Molyko, Great Soppo, Mile 17, Bonduma. Passwords: superuser from ensure_superuser (e.g. `Sch00l_1234`), all other users `Test124`.

---

## Environment / Setup

| Date | Finding | Severity | Notes |
|------|---------|----------|--------|
| 2026-02-04 | SQLite DB in project root (`db_working.sqlite3` / `db.sqlite3`) failed with "database disk image is malformed" during migrate. | High | Migrate succeeded when using `DB_FILE=$TEMP/gilead_buea_test.sqlite3` (DB in system temp). Likely cause: cloud sync or antivirus on project directory. **Workaround**: Use `export DB_FILE=$TEMP/gilead_buea_test.sqlite3` (or copy the created DB to a non-synced path and set DB_FILE). |
| 2026-02-04 | Superuser created: username `admin`, password `Sch00l_1234`. | Info | Created via `ensure_superuser --no-input --username admin --password Sch00l_1234`. |
| 2026-02-04 | Synthetic Buea seed completed (scale=small). | Info | 200 students, 150 parents, 10 teachers, 5 admins, 1 bursar; academics, fee plans, invoices (~30% debt), evals subset, GCE session and candidates. DB copied to `db_buea_seed.sqlite3`. Use `DB_FILE=db_buea_seed.sqlite3` to run against seeded data. |
| 2026-02-05 | Seed expanded to engage **every app/module**: reports (TermPublishStatus), portal (Announcement, PortalFeatureItem), communication (Message, ContactRequest), requests (AccessRequest, RequestDecision), analytics (AttendanceLog, GradeImportJob), people (TeacherAttendance, TeacherLeaveRequest, StudentResourceReturn), evals (MockExamSetting), finance (Payment, PaymentReminder), payroll (PayScale, PayrollEmployee, Contract, PayrollRun, Payslip), siteconfig (RegionConfig, HolidayCalendar), compliance (ComplianceRule), automation (AutomationExecutionLog). See docs/BUEA_SEED_FEATURE_CONFIRMATION.md. | Info | Single run of `seed_buea_synthetic` creates full test environment; document all issues in this tracker (test_finding.md). |
| 2026-02-05 | **Step 4 (tracker run)** executed: Automated test suites run and results logged here. | Info | See "Step 4 execution" below. |

---

## Step 4 execution (test run and tracker update)

| When | What was run | Result | Notes |
|------|----------------|--------|--------|
| 2026-02-05 | `python manage.py test apps.evals.tests.test_grade_approval_workflow apps.finance.tests.test_phase0_security apps.reports.tests apps.requests` | **69 tests OK** | Evals: grade approval workflow (submit, list, detail, 25/20 rejection, non-final role). Finance: webhook security, idempotency, signature, IP. Reports: publish term. Requests: module. |
| 2026-02-05 | Migrate + seed (for full environment) | **Skipped** | `DB_FILE=db_step4.sqlite3` was used; migrate failed partway with "database disk image is malformed" (same disk/sync issue as in Environment). On a healthy DB: run `migrate` → `ensure_superuser` → `seed_buea_synthetic` → then run all scenarios and log every finding in this tracker. |

**Ongoing**: As you run more scenarios (manual or automated), add rows to Bugs, Gaps, Redundancies, Improvements, Security, or Data and Config above. Keep this table updated with what was run and the outcome.

---

## Bugs

| Date | Description | Severity | Notes |
|------|-------------|----------|--------|
| 2026-02-04 | **GradeApprovalRequest**: Views and approval flow referenced `deadline_at` and `validation_flags`, which were removed from the model in migration 0021. | High | Fixed: `evals/views.py` and `evals/approval.py` no longer pass or read these fields; detail template uses `deadline_display = None` and `validation_flags = []`. |
| 2026-02-04 | **Evals templates**: `grade_approval_list.html` used `format_date` (region_format), causing "format_date requires 2 arguments, 1 provided" in test context; `grade_approval_detail.html` used `{% load humanize %}` (KeyError when humanize not in INSTALLED_APPS) and Python-style `x if y` in `{{ }}` (TemplateSyntaxError). | Medium | Fixed: list/detail use `date:"d/m/Y"` for requested_at; humanize load removed; conditional output replaced with `{% if %}...{% endif %}`. |
| 2026-02-04 | **Evals test**: `test_grade_approval_request_has_deadline_and_flag` asserted on removed `deadline_at`/`validation_flags`; `test_non_final_role_cannot_finalize` used `assertFormError` on a response that re-renders with invalid choice (no custom error). | Low | Fixed: test renamed to `test_grade_approval_request_rejects_out_of_range_score` (asserts no approval request when 25/20 submitted); non-final test now asserts status remains PENDING and form has error on `status`. |

---

## Gaps

| Gap | Description | Notes |
|-----|-------------|--------|
| **Debt-block on report card** | `parent_download_term_report`, `parent_download_term_report_csv`, `parent_download_annual_report`, `report_share` do **not** check student/guardian outstanding balance or arrears. Parents of students with debt can download term/annual PDF/CSV and use share links. | **Expected (from guide)**: Block PDF and show “Clear Workshop Fees at Bursary” (or similar); optionally trigger SMS to guardian. **Recommendation**: Add financial clearance check in reports views and optionally notify on payment to “unlock” report. |
| **GCE export columns** | `export_certification_pack` produces: academic_year, session_name, board, level, student_id, student_name, classroom, specialty, admission_number, candidate_number, status, ca_uploaded_at, notes. **Missing vs guide**: CIN (9 digits), FULL_NAMES UPPERCASE, DATE_OF_BIRTH in **DD/MM/YYYY**, EXAM_TYPE (GCE_OL, GCE_AL, ITC, ATC), SPECIALTY_CODE, MOMO_TRANS_ID. Date is not in DD/MM/YYYY; student_name is not forced UPPERCASE. | Add columns and date/name formatting for board template compliance. |
| 6-sequence evals | Model has seq1, seq2, exam, mock, practical (5). If MINESEC requires 6 sequences, document and add if missing. | |
| **Arrears carry-forward** | Unpaid fees from previous year do not appear as opening balance for next year in finance (no explicit carry-forward implemented). | Document for Buea: consider adding opening_balance or arrears carry on rollover. |
| ITC/ATC pass rule, industrial attachment, workshop inventory, QR on report | (To be verified in respective sections.) | |

---

## Redundancies

*(None yet.)*

---

## Improvements

*(None yet.)*

---

## Security

*(None yet.)*

---

## Data and Config

*(None yet.)*

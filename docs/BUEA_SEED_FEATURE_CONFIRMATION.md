# Buea Synthetic Seed — Full System Engagement

This document confirms that **every app and feature** in the school management system is **engaged in creating and seeding** the test environment, so that **everything** can be tested and issues documented in **[test_finding.md](../test_finding.md)**.

---

## How to create the test environment

1. **Database**: Ensure migrations are applied (`python manage.py migrate`). If the project DB is corrupted, use a fresh DB (e.g. `DB_FILE=$TEMP/gilead_buea_test.sqlite3` or copy a good backup).
2. **Superuser**: Ensure an admin exists (`python manage.py ensure_superuser --no-input --username admin --password Sch00l_1234`).
3. **Seed**: Run `python manage.py seed_buea_synthetic [--scale small|full]`. All data **remains** in the system (no teardown).
4. **Tracker**: Log every bug, gap, redundancy, and improvement in **[test_finding.md](../test_finding.md)** at project root.

---

## Apps and modules engaged by the seed

| App | What is seeded | Purpose |
|-----|----------------|--------|
| **accounts** | Users (teachers, admins, bursar, parents), AccessRole, passwords Test124 | RBAC, login, MFA, certification UI |
| **academics** | AcademicYear (2024/25, 2025/26), Terms, Departments, Specialties, Classrooms (Form 1–5, L6, U6, Year 1–7), Subject, SubjectAssignment (coefficients), CertificationExamSession, CertificationCandidate (Form 5 / Upper Sixth), GCE enabled | Curriculum, rollover, GCE export |
| **people** | StudentProfile (Matricule BUEA/2025/001…), TeacherProfile, StudentGuardian (with Buea addresses), **TeacherAttendance**, **TeacherLeaveRequest**, **StudentResourceReturn** | Students, staff, guardians, attendance, leave, resource return (rollover) |
| **evals** | AssessmentWeights (20-point scale), TeacherAssignment, Evaluation (pre-filled subset), **MockExamSetting** (Form 5) | Mark entry, rankings, approval, mock blending |
| **finance** | ComplianceProfile (Buea), FeePlan, FeeItem (Tuition, PTA, Workshop, MTA), Invoice (~30% with balance), **Payment**, **PaymentReminder** | Invoices, payments, webhook tests, reminders |
| **reports** | PromotionRule, **TermPublishStatus** (one term published) | Publish flow, parent report download |
| **portal** | **Announcement** (2), **PortalFeatureItem** (Syllabus, Documents with links) | Portal dashboard, documents, syllabus |
| **communication** | **Message** (admin→parent), **ContactRequest** (parent query, assigned to admin) | Messaging, contact school |
| **requests** | **AccessRequest** (MODULE_ACCESS, LEAVE_APPROVAL), **RequestDecision** (approved) | Request workflow, approvals |
| **analytics** | **AttendanceLog** (3 days), **GradeImportJob** (1 completed) | Analytics dashboard, import monitor |
| **payroll** | **PayScale**, **PayrollEmployee** (from teachers), **EmploymentContract**, **PayrollRun**, **Payslip** | Payroll dashboard, run, payslips |
| **siteconfig** | **RegionConfig** (CM-BUE, Buea), **HolidayCalendar** (Christmas) | Region, localization, holidays |
| **compliance** | **ComplianceRule** (data retention) | Compliance module, audit |
| **automation** | **AutomationExecutionLog** (seed_verification) | Automation / execution history |
| **observability** | (No seedable models; dashboards use existing data) | Health, metrics |
| **api** | (No seedable models; API uses existing data) | REST/API tests |

**Bold** = data added in the “full system” expansion so that every app has something to list or test.

---

## Feature-level checklist (everything testable)

- **Accounts**: Login (admin, teacher, parent, bursar), roles, MFA (if enabled), certification home/session/export, rollover workflow.
- **Academics**: Years, terms, classrooms, specialties, subjects, coefficients, GCE session and candidates, attendance (if used).
- **People**: Students (General/Technical), matricules, guardians, addresses, teacher attendance, leave requests, resource returns.
- **Evals**: Mark entry, 25/20 rejection, coefficients, rankings, grade approval, import/OCR, mock setting, compliance dashboard, audit trail, offline conflict.
- **Finance**: Invoices (tuition, PTA, workshop, MTA), payments, reminders, webhook (success/fail/duplicate), trial balance, reports, access requests.
- **Reports**: Term/annual PDF/CSV, share link, publish (with approval guard), promotion preview, statistical return, report builder, debt-block (document gap if not implemented).
- **Portal**: Parent/teacher dashboards, announcements, documents/syllabus, link child, contact school, onboarding.
- **Communication**: Messages, contact requests, groups, announcements (if used).
- **Requests**: Access requests (finance, module, leave, etc.), decisions, audit.
- **Analytics**: Dashboard, deadlines, master sheet, grade import jobs.
- **Payroll**: Dashboard, pay scale, employees, runs, payslips, leave.
- **Siteconfig**: Region (Buea), holidays, report styles, feature control.
- **Compliance**: Rules, audit log, access control, IP/country (if configured).
- **Automation**: Execution log, approval queue (if used).
- **Observability**: Health, metrics (no seed; smoke test).
- **API**: Endpoints (no seed; use existing entities for API tests).

---

## Issue tracker: test_finding.md

- **Location**: [test_finding.md](../test_finding.md) at project root.
- **Use it for**: Bugs (steps, expected vs actual, severity), Gaps (missing features), Redundancies, Improvements, Security, Data/Config.
- **Update**: Continuously as each scenario is run; do not wait until the end.

---

## Summary

- **One command** creates the full test environment: `python manage.py seed_buea_synthetic [--scale full]`.
- **Every app** that has seedable data is populated so that every feature can be exercised.
- **All data remains** in the database for inspection and regression.
- **Issues** are documented in **test_finding.md** so the tracker is the single place for findings.

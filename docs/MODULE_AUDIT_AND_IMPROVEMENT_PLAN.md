# Module-by-Module Audit & Improvement Plan

> **Non-authoritative.** Historical module audit. Execution order, BR status, and “what’s left” are defined only in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11.4 and §0.3.3. Use this file for ideas, not for contradicting single-execution direction.

**Purpose:** Thorough review of all modules for gaps, redundancy, integration quality, free automation, and seamless end-user experience.  
**Scope:** All apps (accounts, academics, people, evals, finance, payroll, reports, portal, analytics, siteconfig, compliance, communication, requests, observability, api, automation, emis).

---

## Executive Summary

- **`payment_processors_temp` / `payment_validators_temp`:** Not present in codebase — legacy audit line **stale**; finance processors are production models/integrations.
- **MFA:** Zero-cost (`django_otp`); no change required.
- **Active year/term:** Use `apps.academics.services.get_active_year_and_term` in new code.
- **Evals ↔ Reports** are correctly tied: report cards use `Evaluation`, `AssessmentWeights`, and `GradeApprovalRequest`; publish is gated by `TermPublishStatus` and optional `reports_require_approved_grades_before_publish`. Strengthen with explicit “report ready” signals and scheduled report generation where needed.
- **Automation** is partially unified: finance and analytics tasks log to `AutomationExecutionLog`; requests reminder does not. Celery Beat is configured; automation hub exists but could drive more workflows from one place.
- **Redundancy:** Some dashboard/context logic is duplicated between portal and accounts.
- **Gaps:** Requests task not in execution log; no evals→report “ready” notification; EMIS/API test coverage thin; communication (WhatsApp) integration not audited; observability not wired to compliance alerts.

---

## 1. apps.accounts — Authentication & User Management (MFA, RBAC, preferences)

### What’s in place
- Custom User, AccessRole, Permission, UserPreference.
- MFA: `django_otp` (TOTP + otp_static), `views_mfa.py`, `RequireMFAMiddleware`, SiteSettings `require_mfa_roles` / `require_mfa_all_staff`.
- RBAC: decorators, backend dashboard, workflow center, certification flows.
- Backend vs Configuration Engine split (sidebar, quick actions, recommended_next_steps).

### Gaps
- **Profile/backend context:** Ensure every view that renders profile or “admin context” passes `is_backend_context` (e.g. from request path) so labels (Configuration Engine vs Admin) stay correct everywhere.
- **MFA recovery:** No documented flow for “lost device + no backup codes”; consider a small recovery path (e.g. superuser reset or time-limited bypass with audit).
- **Session list/revoke:** No UI to see active sessions or revoke them (helps compliance).

### Redundancy
- MFA check exists in both middleware and login redirect; keep both but ensure one source of truth for “must_have_mfa” (e.g. helper used by both).
- `_admin_context()` and dashboard context both build URLs; consider a single “staff console URLs” helper.

### Integration
- **Compliance:** MFA status could be exposed to compliance dashboard (e.g. “staff without MFA” count already in admin; ensure compliance reporting can use it).
- **Observability:** Login failures and MFA failures should be counted in health/metrics or audit logs.

### Free automation
- Optional “remind users without MFA” (when `require_mfa_roles` is set): periodic task or one-time nudge; zero external cost.

### Tests
- Add tests for: backend_dashboard recommended_next_steps (workflow_center vs admin), profile with `is_backend_context`, MFA required but user has no device (redirect to setup).

---

## 2. apps.academics — Academic Structure (years, terms, classrooms, subjects, scheduling)

### What’s in place
- AcademicYear, Term, Classroom, Subject, SubjectAssignment, Department, Specialty, etc.
- `get_active_year_and_term()` used widely; year cloning; certification (GCE) links.

### Gaps
- **Consistency of “active” year:** Some code uses `AcademicYear.objects.filter(is_active=True).first()`; ensure all key flows use the same service so backend, reports, and evals agree.
- **Term ordering:** Ensure terms have a stable order (e.g. `order` or `start_date`) everywhere (reports, evals, publish).
- **Classroom capacity:** No explicit capacity/overflow checks when enrolling students (people); optional but improves UX.

### Redundancy
- Year/term resolution may be duplicated in portal, reports, evals; centralize in `academics.services` and reuse.

### Integration
- **Evals:** SubjectAssignment and terms drive evaluations; no gap.
- **Reports:** term_report_context and annual_report_context use academics; publish uses TermPublishStatus (reports) and term/year from academics; good.
- **People:** StudentProfile academic_year/classroom/specialty; teacher assignments; ensure bulk imports/backend create use same validation.

### Free automation
- None critical; optional: “warn when term end date passed and not published” (could be a small Celery task or dashboard widget).

### Tests
- Test year clone; test get_active_year_and_term with no year / multiple years (if allowed); test term order in report context.

---

## 3. apps.people — People Management (students, teachers, guardians)

### What’s in place
- StudentProfile, TeacherProfile, StudentGuardian; backend list/create views; links to Configuration Engine for deep edit.
- NotificationPreference, TeacherLeaveRequest, TeacherPayRecord (payroll link).

### Gaps
- **Guardian–student link:** Ensure all flows that “add guardian” or “link to student” go through one path (e.g. invite or backend link) so no orphan guardians.
- **Inactive handling:** When student/teacher is set inactive, evals/reports/finance should respect it (e.g. exclude from active term reports or show “withdrawn”); verify.
- **Bulk import:** If people have bulk import, ensure it logs to AutomationExecutionLog and shows in automation hub (same pattern as finance).

### Redundancy
- Backend student/teacher create vs admin create: already split; ensure no duplicate validation logic (shared form or validator).

### Integration
- **Evals:** Evaluations reference StudentProfile and SubjectAssignment (teacher); good.
- **Reports:** Report cards and term_report_context use StudentProfile; good.
- **Finance:** Invoices/parent view by guardian/student; ensure guardian link is used consistently.
- **Portal:** Parent dashboard uses linked children; teacher dashboard uses TeacherProfile; good.

### Free automation
- Optional: “remind to complete guardian link for students without guardian” (internal notification or report).

### Tests
- Test backend student create (with/without use_backend_people_ui); test guardian link and invite flow; test inactive student excluded from active reports.

---

## 4. apps.evals — Evaluations & Grading (super important; tie with report cards)

### What’s in place
- Evaluation (scores, weights), AssessmentWeights, GradeApprovalRequest, Evidence, offline sync, grade import, ranking, mock exams.
- Approval workflow: PENDING → APPROVED / REJECTED / REVISION_REQUESTED; reports can use “approved only” via SiteSettings.

### Gaps
- **Report-ready signal:** When all grades for a term are approved (and optionally when published), there is no explicit “report card ready” event. Consider: after publish or after approval, set a flag or send internal event so report generation (or scheduled PDF) can run; or document that “parent downloads report” is the trigger (current behavior).
- **Missing grades UX:** Clear “missing evaluations” list for teachers (evaluation_admin and similar) so they know what to fill before publish.
- **Offline sync:** Ensure offline sync and re-import don’t overwrite approved grades without explicit action or audit.

### Redundancy
- Ranking logic in evals.services vs reports.services: both use evals; reports calls evals.services for classroom_term_rankings/school_term_rankings; no duplication.

### Integration with reports (critical)
- **Data flow:** reports.services.term_report_context() and annual_report_context() use Evaluation, AssessmentWeights, and (when enabled) GradeApprovalRequest filter; TermPublishStatus (reports) gates parent visibility; reports_require_approved_grades_before_publish gates publish. This is correct.
- **Improvements:**
  - Add a “Report card status” or “Ready for report” indicator in evaluation_admin (e.g. “All approved for Term 1” or “Pending approval: 2 subjects”).
  - Optional: scheduled task “generate term report PDFs for published terms” (batch) to reduce first-download latency; store in ReportCard.pdf_file if desired.
  - Document in admin/siteconfig that “Reports use approved grades only” and “Require approved grades before publish” control how evals tie to report cards.

### Free automation
- None required for correctness. Optional: reminder for teachers with pending grade approval requests (reuse Notification model).

### Tests
- test_grade_approval_workflow; test that term_report_context respects reports_use_approved_grades_only; test publish_term when reports_require_approved_grades_before_publish True/False; test ranking consistency with evals.

---

## 5. apps.finance — Financial Management (fees, invoices, payments, receipt automation, fraud detection)

### What’s in place
- Invoice, Payment, FeePlan, PaymentReminder, Notification, receipt verification, bank verification, fraud_detection, tasks (Celery) for reminders, invoice generation, status update, receipt processing, bank retry. All key tasks log to AutomationExecutionLog.

### Gaps
- **Payment processor abstraction:** `payment_processors_temp` is imported from `payment_processors`; either rename to canonical name and remove “_temp”, or document why temp and keep both in sync.
- **Payment validators:** Same for `payment_validators_temp`; consolidate or document.
- **Idempotency:** Receipt upload and payment status updates should be idempotent where possible (already have idempotency_key on PaymentProofUpload); verify all entry points.

### Redundancy
- payment_processors_temp vs payment_processors: single import in payment_processors; reduce to one module name and deprecate _temp in code and docs.

### Integration
- **Portal:** Parent sees invoices and payments; finance dashboard data in backend; good.
- **Compliance:** Finance requests and audit; ComplianceProfile; ensure sensitive actions are in audit log.
- **Automation:** Finance tasks already log to AutomationExecutionLog; approval queue used where configured; good.

### Free automation
- Already in place: payment reminders, retry failed reminders, update invoice statuses, retry bank verification (all Celery). No extra cost if broker (Redis) is available or use database as broker for low volume.

### Tests
- test_phase0_security, test_services, test_payment_phase2, test_referral_reward; add test that send_payment_reminders (or key task) creates AutomationExecutionLog.

---

## 6. apps.payroll — Payroll Management (payslips, CNPS, tax)

### What’s in place
- PayrollRun, PayrollRunApproval, PayScale; services; run_payroll_cycle command.

### Gaps
- **Automation log:** Payroll run (manual or scheduled) should log to AutomationExecutionLog so it appears in automation hub and can be audited (same pattern as finance).
- **CNPS/tax:** Ensure formulas are configurable or documented; no hardcoded rates in code if they change by year.

### Integration
- **People:** TeacherPayRecord, pay_grade; TeacherProfile; good.
- **Portal:** Teacher may see payslip; ensure permission and link from teacher dashboard.

### Free automation
- Optional: scheduled “run payroll for month” (e.g. Celery Beat) with approval step (AutomationApprovalQueue) for safety.

### Tests
- Test payroll run creates run record and (after change) AutomationExecutionLog entry; test approval flow if present.

---

## 7. apps.reports — Reports & Report Cards (super important; tied to evals)

### What’s in place
- TermPublishStatus, ReportCard, ReportCardAudit, PromotionRule; term_report_context, annual_report_context; grade_approval_publish_readiness; publish_term_results view; PDF generation (WeasyPrint); parent download term/annual; report library and styles (siteconfig).

### Gaps
- **Scheduled/batch generation:** No built-in “generate all term report PDFs for published term” task; first parent download generates on the fly. Optional: nightly task to pre-generate and cache PDFs for better first-load experience.
- **Localization:** ReportCard has language/region_code; ensure term_report_context and templates use them consistently (e.g. labels, decimals).
- **Large schools:** For many students, bulk PDF generation could be heavy; consider chunking or queue (Celery) if you add batch generation.

### Redundancy
- Report context building (rows, summary, rankings) is in reports.services; evals provides data; no duplication.

### Integration with evals (critical)
- **Already correct:** term_report_context and annual_report_context pull from Evaluation; reports_use_approved_grades_only and _approved_or_unrequested_subject_assignment_filter ensure only approved (or unrequested) grades show when enabled; publish is gated by grade_approval_publish_readiness when reports_require_approved_grades_before_publish. Evals and reports are well tied.
- **UX improvement:** On “Publish term” page, show explicit “Report cards will use these grades” and link to “Evaluation admin” for missing grades; and in evaluation admin show “Report status: ready / not ready” for the term.

### Free automation
- Optional Celery task: “pre-generate term report PDFs for last published term” (e.g. daily) to warm cache; or “generate on first request” only (current) to avoid storage cost.

### Tests
- test_cameroon_report_context, test_publish_term; add test that term_report_context excludes unapproved evaluations when reports_use_approved_grades_only is True.

---

## 8. apps.portal — Parent & Teacher Portal (dashboards, documents, communication)

### What’s in place
- Parent/teacher dashboards, document library, KB, onboarding, AI copilot, contact requests, dashboard layout.

### Gaps
- **term_report_context in loops:** portal/services or views call term_report_context per student in a loop; optimize with bulk prefetch or single query per term (e.g. prefetch evaluations for all children) to avoid N+1.
- **Report download permission:** Ensure parent can only download reports for their linked children and only for published terms (already enforced via is_term_published); verify in view.
- **Teacher dashboard:** Ensure teacher sees only their classes/subjects and evals; no cross-class data leak.

### Redundancy
- Dashboard layout and widget metadata may overlap with siteconfig/accounts; keep one source of truth (e.g. siteconfig.models_dashboard) and reuse in portal and accounts.

### Integration
- **Reports:** Parent download term/annual uses reports.views and term_report_context/annual_report_context; good.
- **Evals:** Teacher evals and grade entry; good.
- **Finance:** Invoices and payments on parent dashboard; good.
- **Communication:** Announcements and messages; good.

### Free automation
- None critical; optional: “notify parent when new report is available” (internal notification when term is published).

### Tests
- test_dashboard_custom_layout, test_rbac_teacher_pay, test_teacher_timetable; add test for parent report download (allowed only for own child and published term); add test for N+1 in report list if applicable.

---

## 9. apps.analytics — Analytics & Dashboards (metrics, ML, compliance tracking)

### What’s in place
- Dashboard views, deadline reminders (Celery task logs to AutomationExecutionLog), services for metrics and predictions.

### Gaps
- **ML predictions:** If any ML model is used, ensure it’s optional (no hard dependency) and document data source and refresh (e.g. which evals/finance data).
- **Compliance tracking:** Clarify whether “compliance tracking” here is same as apps.compliance or a subset (e.g. deadline compliance); avoid duplicate concepts.

### Integration
- **Evals:** Deadline reminders use evals/assignment data; good.
- **Observability:** Metrics could be exposed to observability app for unified health view.

### Free automation
- send_deadline_reminders already scheduled; no extra cost.

### Tests
- Test that send_deadline_reminders creates AutomationExecutionLog; test dashboard data with no data (empty state).

---

## 10. apps.siteconfig — System Configuration (settings, themes, preferences)

### What’s in place
- SiteSettings (large model: theme, MFA, reports flags, finance automation, feature flags), RegionConfig, ReportCardStyle, portal sidebar, context_processors (site_settings, is_backend_context), dashboard widget metadata.

### Gaps
- **Single source of truth:** Ensure all “feature flags” and “report behavior” flags live in SiteSettings and are read via get_solo() or cached; no scattered env vars for the same concept.
- **Backend vs admin:** Already done; keep is_backend_context in sync with any new portal/backend routes.

### Redundancy
- Theme/color logic in siteconfig vs unfold admin: ensure customizer writes to SiteSettings and admin theme reads same; no duplicate color sets.

### Integration
- **Reports:** reports_use_approved_grades_only, reports_require_approved_grades_before_publish, ReportCardStyle; good.
- **Accounts:** require_mfa_roles, require_mfa_all_staff; good.
- **Finance:** Reminder intervals, fee automation; good.

### Free automation
- None; siteconfig is configuration, not background jobs.

### Tests
- test_backend_context, test_reportcard_builder, test_theme_studio; test that changing reports_require_approved_grades_before_publish is reflected in publish_term view.

---

## 11. apps.compliance — Compliance & Security (audit, access control, threat detection)

### What’s in place
- AccessLog, AuditLog, ComplianceReport, ThreatDetectionConfig, CountryAccessRule, IPAccessRule, AlertDigest; middleware; reporting views; management commands (archive, check, detect_threats, generate_compliance_reports, etc.).

### Gaps
- **MFA (zero-cost):** Already using django_otp (TOTP); no extra cost. Document in compliance docs that “MFA” is TOTP + backup codes and is zero-cost.
- **Alerting:** Ensure digest or alerts can be sent via existing notification channel (e.g. email or in-app Notification) without adding paid services; document.
- **Threat detection:** If using GeoIP or similar, document free vs paid limits (e.g. MaxMind free DB).

### Redundancy
- Compliance “dashboard” vs observability “health”: ensure compliance is about policy/audit and observability about uptime/metrics; no duplicate “health” definition.

### Integration
- **Accounts:** MFA status; login and sensitive actions should write to AccessLog/AuditLog where applicable.
- **Finance:** Sensitive finance actions in audit log; ComplianceProfile; good.
- **Observability:** Health endpoint need not duplicate compliance checks; compliance can consume health or vice versa for “degraded” state.

### Free automation
- Management commands for archive, detect_threats, generate_compliance_reports can be run from cron or Celery Beat at no extra cost; document schedule.

### Tests
- test_access_control, test_analytics, test_compliance, test_threat_detection; add test that MFA setup/verify is audited if required.

---

## 12. apps.communication — Communication (messaging, announcements, WhatsApp)

### What’s in place
- Message, Announcement, groups, contact requests, video_conferencing, integrations (likely WhatsApp here or in siteconfig).

### Gaps
- **WhatsApp:** If WhatsApp is used, document whether it’s API (cost) or link-only (free); ensure env vars and keys are not committed; rate limits and error handling.
- **Delivery status:** Track “sent/failed” for outbound messages where possible (in-app or external) for compliance and support.

### Redundancy
- Announcements vs Message: clarify “announcement” = one-to-many, “message” = conversation; avoid overlapping tables for same concept.

### Integration
- **Portal:** Parent/teacher see announcements and messages; good.
- **Finance:** Payment reminders may use Notification (finance) or communication; ensure one path for “reminder” so users don’t get duplicates.

### Free automation
- Optional: “digest of announcements” (e.g. daily email or in-app) using existing email backend; no extra cost.

### Tests
- Test announcement creation and visibility by role; test that contact requests are stored and (if applicable) linked to compliance.

---

## 13. apps.requests — Access Requests (workflow, approval)

### What’s in place
- AccessRequest model, workflow, Celery task remind_pending_assignees (no AutomationExecutionLog).

### Gaps
- **Execution log:** Add AutomationExecutionLog entry when remind_pending_assignees_task runs (same pattern as finance/analytics) so automation hub shows “Requests reminder” runs.
- **Approval SLA:** Optional: “remind if request pending > N days” (already interval-based); document in SiteSettings.

### Integration
- **Accounts:** Assigned_to, requester; RBAC; good.
- **Finance:** Notification used for reminder; good.

### Free automation
- Task already in Celery Beat; add logging to AutomationExecutionLog at no extra cost.

### Tests
- Test that when interval > 0, task sends notifications and (after change) creates execution log.

---

## 14. apps.observability — Monitoring & Observability (health, metrics)

### What’s in place
- healthz, public health, metrics endpoints; admin dashboard charts; optional middleware.

### Gaps
- **Compliance link:** Health “degraded” or “unavailable” could trigger a compliance alert or log (e.g. “service degraded at X”); optional integration.
- **Metrics:** Ensure metrics don’t expose PII; document what is exposed at /metrics.

### Integration
- **API:** Health used by load balancers; good.
- **Admin:** Dashboard uses api_health, api_dashboard_charts; good.

### Free automation
- None; observability is pull-based (scrape /health, /metrics).

### Tests
- Test health returns 200 when DB/cache available; test metrics format if used by Prometheus.

---

## 15. apps.api — REST API (mobile, integrations)

### What’s in place
- Entity API, dashboard API, search API, mobile API, notification API, user preferences, JWT; schema and schema UI.

### Gaps
- **Search API:** Returns admin URLs for entity links (e.g. student change); when request is from backend context (e.g. Referer or header), consider returning backend URLs for students/teachers so mobile/UI stays in backend flow where appropriate.
- **Versioning:** If mobile app is long-lived, consider /api/v1/ and document stability.
- **Rate limiting:** Ensure API is rate-limited (e.g. compliance or DRF throttling) to avoid abuse.

### Redundancy
- Dashboard API vs portal dashboard context: share logic where possible (e.g. same service layer) so API and HTML use same data.

### Integration
- **Accounts:** JWT and permissions; good.
- **Portal:** Dashboard layout API; good.

### Free automation
- None; API is request/response.

### Tests
- test_dashboard_api_rbac, test_entity_flags; add test for search API returns valid links; add test for rate limit or permission on sensitive endpoints.

---

## 16. apps.automation — Automation & Background Tasks (configurable automation)

### What’s in place
- AutomationExecutionLog, AutomationApprovalQueue; admin and hub (accounts.views.automation_hub). Finance and analytics tasks write to ExecutionLog; requests task does not.

### Gaps
- **Unified logging:** All Celery tasks that represent “automation” (finance, analytics, requests, future payroll) should create an ExecutionLog entry so operators see one place (automation hub + admin list).
- **Approval queue usage:** Document which tasks use ApprovalQueue (e.g. bulk fee generation) and ensure they create queue entries when “approval required” is on.
- **Beat schedule:** CELERY_BEAT_SCHEDULE is in settings; ensure django_celery_beat PeriodicTask is in sync if you use DB-backed schedule (optional).

### Redundancy
- automation_hub links to admin changelists for log and queue; no duplicate storage.

### Integration
- **Finance, analytics:** Already integrated; **requests:** add integration (log only).
- **Payroll:** When payroll run is automated, add ExecutionLog (and optionally ApprovalQueue).

### Free automation
- All current automation is free (Celery + DB); document “no Redis” option (e.g. database broker for low volume) for zero-cost setup.

### Tests
- Test that at least one finance task creates AutomationExecutionLog; after adding requests logging, test that too.

---

## 17. emis — EMIS Integration (government reporting, data export)

### What’s in place
- EMISExport, EMISCompliance; dashboard; export view; services (EMISExportService).

### Gaps
- **Export format:** Ensure export format matches current government spec (e.g. Cameroon); document version and field mapping.
- **Large export:** For large schools, export could be long-running; consider Celery task + “download when ready” link and log to AutomationExecutionLog.
- **Tests:** tests.py exists; ensure it covers at least one export path and permission.

### Redundancy
- None significant.

### Integration
- **Academics, people, evals:** Export pulls from these; ensure export runs on consistent snapshot (e.g. same year/term) and doesn’t change mid-export.

### Free automation
- Optional: scheduled “monthly EMIS export” (Celery) with optional approval; log to AutomationExecutionLog.

### Tests
- Test export with minimal data; test that only allowed roles can access dashboard and export.

---

## Cross-Module Integration Summary

| From → To   | Integration point | Status / Action |
|-------------|-------------------|------------------|
| evals → reports | Evaluation, weights, approval filter; publish gate | OK; add “report ready” UX and optional batch PDF task |
| reports → evals | term_report_context, annual_report_context | OK |
| accounts → compliance | MFA, audit, access log | OK; document MFA zero-cost |
| accounts → siteconfig | MFA flags, backend context | OK |
| finance → automation | ExecutionLog for all key tasks | OK |
| analytics → automation | ExecutionLog for deadline reminders | OK |
| requests → automation | ExecutionLog for reminder task | **Add** |
| payroll → automation | ExecutionLog (and optional ApprovalQueue) | **Add** when payroll is automated |
| portal → reports | Parent download; term_report_context | OK; optimize N+1 |
| portal → evals | Teacher grade entry | OK |
| api → accounts/siteconfig | Backend vs admin URLs in search | Optional: return backend URLs when appropriate |
| compliance → observability | Optional: health → compliance alert | Optional |

---

## Redundancy Checklist

- [ ] **Finance:** Rename or remove `payment_processors_temp` / `payment_validators_temp`; single canonical module.
- [ ] **Dashboard context:** One source for “staff console URLs” and widget metadata (siteconfig/accounts).
- [ ] **MFA “must have” logic:** Single helper used by middleware and login redirect.
- [ ] **Year/term resolution:** Centralize in academics.services where possible.

---

## Free Automation Checklist (zero or minimal cost)

- [ ] **Celery:** Use existing broker (or DB broker) and Beat; no new paid service.
- [ ] **MFA:** Already TOTP + static (django_otp); zero cost.
- [ ] **Requests reminder:** Already scheduled; add ExecutionLog.
- [ ] **Optional:** Remind users without MFA when require_mfa_roles is set (internal notification).
- [ ] **Optional:** Notify parents when term is published (internal notification).
- [ ] **Optional:** Pre-generate term report PDFs (nightly) to warm cache; or keep on-demand.
- [ ] **Optional:** Payroll run and EMIS export as scheduled tasks with ExecutionLog (and approval where needed).

---

## Testing Priorities

1. **Evals ↔ reports:** term_report_context with reports_use_approved_grades_only; publish_term with reports_require_approved_grades_before_publish; “report ready” behavior.
2. **Accounts:** Backend context and recommended_next_steps; MFA redirect and setup; profile Configuration Engine label.
3. **Finance:** One key task (e.g. send_payment_reminders) creates AutomationExecutionLog; idempotency where applicable.
4. **Requests:** remind_pending_assignees creates AutomationExecutionLog (after implementation).
5. **Portal:** Parent report download permission and published-term check; N+1 in report list.
6. **API:** Search API and dashboard API RBAC; rate limit or throttle.
7. **Compliance:** MFA audit or compliance report includes “staff without MFA” when applicable.
8. **EMIS:** Export permission and minimal export run.

---

## Action Plan (Prioritized)

### P0 (Critical for correctness and security)
1. **Requests task → AutomationExecutionLog:** In `apps.requests.tasks.remind_pending_assignees_task`, create an `AutomationExecutionLog` entry (SUCCESS/FAILED) so automation hub shows it.
2. **Evals–reports documentation:** Add a short doc or admin help: “How report cards use grades” (approved-only, publish gate, where to fix missing grades).
3. **Finance _temp modules:** Remove or rename `payment_processors_temp` / `payment_validators_temp` to canonical names and update imports.

### P1 (High value, seamless experience)
4. **Report “ready” UX:** In evaluation_admin (or publish term page), show “Report card status: ready / pending approval / missing grades” for the selected term.
5. **Portal report N+1:** In portal views that list or build report context for multiple students, prefetch evaluations (and related) per term to avoid N+1.
6. **Payroll → AutomationExecutionLog:** When payroll run is executed (command or future task), create an AutomationExecutionLog record.
7. **Single MFA helper:** Extract “must_have_mfa(user, site)” (and optionally “is_verified(request)”) and use in middleware and login redirect to avoid drift.

### P2 (Quality and maintainability)
8. **API search backend URLs:** Optional: when request has Referer or header indicating backend, return backend student/teacher URLs from search API.
9. **Session list/revoke (accounts):** Optional UI for “active sessions” and “revoke” for compliance and UX.
10. **Compliance doc:** Document MFA (TOTP, zero-cost), threat detection (GeoIP if used), and recommended cron/Celery for compliance commands.
11. **Test coverage:** Add the tests listed in “Testing Priorities” above.

### P3 (Nice to have)
12. **Scheduled report PDF generation:** Optional Celery task to pre-generate term report PDFs for published term (with chunking for large schools).
13. **Parent “report available” notification:** When a term is published, create in-app Notification for parents with linked children.
14. **EMIS export as task:** Run export in Celery, provide “download when ready” link, log to AutomationExecutionLog.

---

## Summary Table: Module Health

| Module      | Integration | Gaps | Redundancy | Automation | Tests |
|------------|-------------|------|------------|------------|-------|
| accounts   | Good        | MFA recovery, session revoke | MFA/dashboard context | Optional MFA nudge | Add backend/MFA tests |
| academics  | Good        | Active year consistency     | Year/term resolution  | Optional term warn | Year/term tests |
| people     | Good        | Guardian link, inactive      | Backend vs admin create | Optional guardian nudge | Backend create, guardian |
| evals      | **Strong**  | Report-ready UX, missing list | None                  | Optional reminder   | Approval + report filter |
| finance    | Good        | _temp rename, idempotency    | _temp modules         | **In place**        | + ExecutionLog test |
| payroll    | Good        | ExecutionLog                | None                  | Optional schedule   | + ExecutionLog |
| reports    | **Strong**  | Batch PDF optional           | None                  | Optional pre-gen    | + approved-only test |
| portal     | Good        | N+1, permission check        | Dashboard metadata    | Optional notify     | Report download, N+1 |
| analytics  | Good        | ML optional, compliance scope | None                 | **In place**        | ExecutionLog test |
| siteconfig | Good        | Single source flags          | Theme vs admin        | N/A                 | Backend context, flags |
| compliance | Good        | MFA doc, alert channel       | vs observability      | Commands/cron       | MFA audit |
| communication | Good     | WhatsApp cost/doc, delivery  | Announcement vs message | Optional digest   | Announcement visibility |
| requests   | Good        | **ExecutionLog**             | None                  | **Add log**         | + ExecutionLog test |
| observability | Good     | Compliance link optional     | None                  | N/A                 | Health/metrics |
| api        | Good        | Backend URLs, versioning     | Dashboard logic share | N/A                 | Search, RBAC, throttle |
| automation | Good        | **Unified logging**          | None                  | Document            | Finance/requests log |
| emis       | Good        | Export format, large export  | None                  | Optional schedule   | Export + permission |

This plan should give you a clear, module-by-module view and a prioritized path to a more seamless, professional, and maintainable system with no new cost for MFA and minimal extra cost for automation (existing Celery/Beat).

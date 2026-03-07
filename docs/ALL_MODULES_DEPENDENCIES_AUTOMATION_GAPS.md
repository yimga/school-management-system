# All Modules: Dependencies, Integration, Automation & Gaps

**Purpose**: For every module: how they depend on each other, how they integrate, how automation can help, and gaps with suggested fixes.

---

## 1. Module dependency graph

```
accounts (core – no app dependencies)
├── academics     → accounts
├── people        → accounts, academics
├── siteconfig    → accounts, academics*, people*, reports*  (* for dashboard/widgets only)
│
├── evals         → accounts, academics, people
├── finance       → accounts, academics, people, siteconfig
├── payroll       → accounts, academics, people, finance
├── reports       → accounts, academics, people, evals, siteconfig
│
├── portal        → accounts, academics, people, evals, finance, reports, analytics, siteconfig, communication, requests
├── analytics     → accounts, academics, people, evals, siteconfig, finance
│
├── communication → accounts, academics, people
├── requests      → accounts, evals, finance, people, communication
├── compliance    → accounts
├── observability → (optional refs to accounts, people, finance, evals, compliance for health/metrics)
├── api           → accounts, academics, people, evals, siteconfig, communication, finance
├── automation    → academics, siteconfig  (+ finance/evals use automation models)
│
emis (external)   → accounts, academics, people, finance, siteconfig
```

**Summary**:
- **accounts** is the only app with no in-project app dependencies.
- **academics** and **people** are the next layer; **evals**, **finance**, **reports**, **payroll** depend on them.
- **portal** and **analytics** are heavy consumers (many integrations).
- **requests** acts as a hub: it syncs from evals (grade approval), finance (report request), people (leave request) into a unified AccessRequest list.
- **automation** provides models/helpers used by **finance** (and potentially evals); it only imports **academics** and **siteconfig** for helpers.

---

## 2. Per-module: integrations, automation, gaps, fixes

### 2.1 apps.accounts – Authentication & user management

| Aspect | Detail |
|--------|--------|
| **Depends on** | None (core). |
| **Used by** | Every other app (User, roles, permissions, decorators). |
| **Integrations** | MFA (django_otp), RBAC, preferences; portal/evals/finance use `role_required`, `get_user_role`, `get_dashboard_context`. |
| **Automation help** | Password reset emails, session/Token cleanup, preference sync; optional “inactive user” reminders. Do **not** automate: user create/delete, role/permission changes, MFA reset. |
| **Gaps** | (1) No unified “require MFA for role” flag in SiteSettings. (2) Inactive-user cleanup/reminder not automated. |
| **Fixes** | Add `require_mfa_roles` (e.g. JSON list) in SiteSettings and enforce in login/sensitive views. Optional: scheduled task to warn or flag inactive users. |

---

### 2.2 apps.academics – Academic structure

| Aspect | Detail |
|--------|--------|
| **Depends on** | accounts. |
| **Used by** | people, evals, finance, payroll, reports, portal, analytics, communication, api, automation, emis. |
| **Integrations** | Years/terms/classrooms/subjects drive evals (SubjectAssignment), finance (FeePlan by classroom), reports (term publish), portal (student context), EMIS (structure export). |
| **Automation help** | Year/term rollover **clone** with dry-run + optional approval; “term ending soon” reminders. Do **not** automate: create/delete years, terms, classrooms. |
| **Gaps** | (1) Rollover cloning may be manual or partial; no single “rollover wizard” with approval. (2) No automated reminder “term ends in X days”. |
| **Fixes** | Centralize rollover in one flow (clone year, terms, fee plans, etc.) with dry-run and optional AutomationApprovalQueue. Add SiteSettings + Celery task for term-end reminder. |

---

### 2.3 apps.people – People management

| Aspect | Detail |
|--------|--------|
| **Depends on** | accounts, academics. |
| **Used by** | evals, finance, payroll, reports, portal, analytics, communication, requests, api, siteconfig, emis. |
| **Integrations** | Students/teachers/guardians feed evals (Evaluation, TeacherAssignment), finance (invoices, reminders), reports (report cards), portal (dashboards), payroll (PayrollEmployee), requests (leave → AccessRequest), communication (announcements by class/department). |
| **Automation help** | Bulk export/sync with approval; “new guardian not linked” reminder. Do **not** automate: withdrawal, guardian unlink, status changes. |
| **Gaps** | (1) Finance signals (e.g. stop reminders on withdrawal) may need to stay robust after people changes. (2) No automated “orphan” guardian or “student without guardian” report. |
| **Fixes** | Ensure finance signal on StudentProfile (inactive/withdrawn) is well tested. Optional: scheduled report or dashboard widget “Students without guardian” / “Pending guardian invites”. |

---

### 2.4 apps.evals – Evaluations & grading

| Aspect | Detail |
|--------|--------|
| **Depends on** | accounts, academics, people. |
| **Used by** | reports, portal, analytics, requests, api, observability. |
| **Integrations** | **Reports**: report card data comes from Evaluation + AssessmentWeights + evals.services (rankings). **Portal**: teacher/parent see grades; **analytics**: compliance, deadlines, master sheet; **requests**: GradeApprovalRequest synced to AccessRequest. **Compliance**: AuditLog for grade changes. |
| **Automation help** | Deadline reminders (SubjectAssignment or equivalent), bulk import **validation** (no auto-apply without approval), lock grades after term publish. Do **not** automate: grade entry, approval decisions, changing weights after publish. |
| **Gaps** | (1) GradingDeadline removed; deadline logic uses SubjectAssignment or similar – ensure one canonical source (see CODE_REVIEW_GAPS_REDUNDANCIES.md). (2) Report publish can happen before all grade approvals when `grade_approval_enabled`. (3) No “approved grades only” filter in report context. |
| **Fixes** | Use single source for grading deadline (e.g. SubjectAssignment.grading_deadline_at). Add optional “require approved grades before publish” and “reports_use_approved_grades_only” in SiteSettings; block or warn on publish page when pending approvals exist. |

---

### 2.5 apps.finance – Financial management

| Aspect | Detail |
|--------|--------|
| **Depends on** | accounts, academics, people, siteconfig. |
| **Used by** | payroll, portal, requests, api, observability, emis. |
| **Integrations** | **Payroll**: ComplianceProfile, TaxBracket, ContributionRule. **Portal**: invoices, payments, receipt upload, payment link. **Requests**: ReportRequest → AccessRequest. **Automation**: invoice generation (with optional approval queue), reminders, receipt verification, bank verification. |
| **Automation help** | Already strong: fee invoice generation (optional approval), payment reminders, receipt verification, retry failed reminders, bank verification. Do **not** automate without approval: apply payment from receipt (configurable), void, refund. |
| **Gaps** | (1) Ensure void/reject receipt always require reason + audit. (2) Some flows may still hardcode limits; ensure all thresholds in SiteSettings. |
| **Fixes** | Audit all “override” actions (void, reject, reassign receipt) for mandatory reason and AuditLog. Review code for any remaining hardcoded amounts/days; move to SiteSettings. |

---

### 2.6 apps.payroll – Payroll management

| Aspect | Detail |
|--------|--------|
| **Depends on** | accounts, academics, people, finance. |
| **Used by** | portal (payslip view), observability (if metrics include payroll). |
| **Integrations** | Uses finance ComplianceProfile, TaxBracket, ContributionRule; people TeacherProfile; academics Department. Portal shows payslips to staff. |
| **Automation help** | **Preview** run (dry-run) on schedule; “payroll due” reminder. Do **not** automate: actual payroll run (always manual or approval). |
| **Gaps** | (1) No approval queue for “run payroll” if ever exposed to automation. (2) Portal integration may be minimal (only view). |
| **Fixes** | Keep payroll run explicitly manual or behind AutomationApprovalQueue. Optional: Celery task that only sends “Payroll window open – run when ready” reminder. |

---

### 2.7 apps.reports – Reports & report cards

| Aspect | Detail |
|--------|--------|
| **Depends on** | accounts, academics, people, evals, siteconfig. |
| **Used by** | portal (parent/teacher view results), evals (is_term_published locks grade entry). |
| **Integrations** | **Evals**: report context = Evaluation + AssessmentWeights + evals.services (rankings). Publish (TermPublishStatus) locks evals for that term. Portal uses term_report_context / annual_report_context for display and PDF. |
| **Automation help** | Scheduled **generation** of PDFs for already-published terms; cache refresh. Do **not** automate: **publishing** term results (manual). |
| **Gaps** | (1) Publish allowed even when grade approval pending. (2) No “approved grades only” in report context. (3) Publish action audit (who/when) could be more explicit. |
| **Fixes** | Add `reports_require_approved_grades_before_publish` and `reports_use_approved_grades_only`; warn/block on publish when pending approvals; ensure Publish term is in AuditLog/ReportCardAudit. |

---

### 2.8 apps.portal – Parent & teacher portal

| Aspect | Detail |
|--------|--------|
| **Depends on** | accounts, academics, people, evals, finance, reports, analytics, siteconfig, communication, requests. |
| **Used by** | (nothing – it’s a consumer). |
| **Integrations** | Aggregates: students (people), grades (evals), rankings (evals.services), report context (reports), invoices/payments (finance), dashboard (siteconfig), messages/announcements (communication), access requests (requests), analytics (deadlines, compliance). Evals views reused for teacher grade entry; finance for payment link; requests for “request access”. |
| **Automation help** | Notification digest, cache invalidation when underlying data changes. Do **not** automate: feature toggles, access changes. |
| **Gaps** | (1) Many imports; risk of circular imports if new cross-links added. (2) Dashboard context duplicated in places – should use get_dashboard_context everywhere. |
| **Fixes** | Prefer `get_dashboard_context()` in every portal dashboard view. Avoid adding new direct dependencies from portal to other apps; use services/APIs. |

---

### 2.9 apps.analytics – Analytics & dashboards

| Aspect | Detail |
|--------|--------|
| **Depends on** | accounts, academics, people, evals, siteconfig, finance. |
| **Used by** | portal, evals (get_teacher_compliance, get_audit_trail, GradeImportJob). |
| **Integrations** | Evals (Evaluation, TeacherAssignment, GradeImportJob), academics (SubjectAssignment, deadlines), finance (Notification for alerts). Deadline reminders task uses academics + evals. |
| **Automation help** | Deadline reminders (already), cache refresh, ML batch predictions (e.g. fee default risk). Do **not** automate: changing promotion thresholds that affect reports. |
| **Gaps** | (1) GradingDeadline removed; analytics may still reference it – use SubjectAssignment or single deadline source. (2) ML predictions not necessarily on a schedule. |
| **Fixes** | Replace any GradingDeadline reference with canonical deadline source. Optional: Celery beat task for periodic ML run (with configurable on/off). |

---

### 2.10 apps.siteconfig – System configuration

| Aspect | Detail |
|--------|--------|
| **Depends on** | accounts, academics (Classroom, Subject), people (StudentProfile, TeacherProfile, StudentGuardian), reports (ReportCard) – mainly for dashboard/widget config. |
| **Used by** | Almost every app (SiteSettings, feature flags, integrations, dashboard layout). |
| **Integrations** | Single source for feature flags, themes, finance automation settings, report card styles, region config, dashboard widgets. |
| **Automation help** | Cache invalidation when settings change. Do **not** automate: changing settings that affect security/finance/evals. |
| **Gaps** | (1) Large SiteSettings model; some settings may be duplicated or unclear. (2) Dashboard layout logic split between siteconfig and api. |
| **Fixes** | Group settings in admin (already partial); document which flags affect which modules. Keep layout normalization in one place (e.g. dashboard_views) and reuse from API. |

---

### 2.11 apps.compliance – Compliance & security

| Aspect | Detail |
|--------|--------|
| **Depends on** | accounts. |
| **Used by** | evals (AuditLog), observability (AccessLog, AuditLog in health), other apps that log actions. |
| **Integrations** | AuditLog used by evals (grade changes), finance (sensitive overrides); access control and threat detection middleware. |
| **Automation help** | Audit log retention (archive/delete old logs by policy), scheduled compliance reports. Do **not** automate: deleting logs, changing retention without approval. |
| **Gaps** | (1) MFA: need zero-cost option – TOTP (django_otp) already in project; document for compliance. (2) Retention policy may not be enforced automatically. |
| **Fixes** | Recommend/require TOTP for sensitive roles (SiteSettings `require_mfa_roles`). Optional: scheduled task to archive/apply retention to old AuditLog/AccessLog. |

---

### 2.12 apps.communication – Communication

| Aspect | Detail |
|--------|--------|
| **Depends on** | accounts, academics (Classroom, Department). |
| **Used by** | portal, requests, api, finance (Notification), evals (MessageThread). |
| **Integrations** | **Portal**: messages, announcements, class threads. **Requests**: Message for notifications. **Finance**: Notification model for payment alerts. **Evals**: MessageThread. People (TeacherProfile), academics (Department) for targeting. |
| **Automation help** | Scheduled announcements, “pending contact request” reminder. Do **not** automate: sending to entire school without review. |
| **Gaps** | (1) Multiple “notification” concepts: Message, Notification (finance), PortalNotification – can be confusing. (2) WhatsApp/SMS/Email config in siteconfig; ensure communication app uses them consistently. |
| **Fixes** | Document when to use Message vs Notification vs PortalNotification. Ensure one place for “channels” config (SiteSettings) and communication uses get_notification_channels where relevant. |

---

### 2.13 apps.requests – Access requests

| Aspect | Detail |
|--------|--------|
| **Depends on** | accounts; **integrates with** evals, finance, people via signals. |
| **Used by** | portal (request access), finance (create_access_request). |
| **Integrations** | **Evals**: GradeApprovalRequest → synced to AccessRequest (unified list). **Finance**: ReportRequest → AccessRequest. **People**: TeacherLeaveRequest → AccessRequest. **Communication**: Message for notifications. Creates single “request center” for staff. |
| **Automation help** | Reminder for pending requests (“N pending access requests”). Do **not** automate: approve/deny decisions. |
| **Gaps** | (1) If new request types (e.g. refund) are added, they must be synced to AccessRequest if they should appear in center. (2) No scheduled “remind assignee” task. |
| **Fixes** | Document how to add a new request type and sync to AccessRequest. Optional: Celery task “remind assigned_to of pending requests” (configurable). |

---

### 2.14 apps.observability – Monitoring & observability

| Aspect | Detail |
|--------|--------|
| **Depends on** | Optional refs to accounts, people, finance, evals, compliance for health checks and metrics. |
| **Used by** | DevOps / external monitoring (no in-app consumer). |
| **Integrations** | May check DB, cache, and optionally entity counts (students, invoices, etc.) or AuditLog for “last activity”. |
| **Automation help** | Health checks and metrics scrape are already “automated” (on request). Optional: alerting when health fails (external or Sentry). |
| **Gaps** | (1) Some health views import models (finance.Notification, people, evals, compliance) – ensure lazy imports to avoid circular import. |
| **Fixes** | Keep optional model imports inside view functions; document which endpoints need which apps installed. |

---

### 2.15 apps.api – REST API

| Aspect | Detail |
|--------|--------|
| **Depends on** | accounts, academics, people, evals, siteconfig, communication, finance. |
| **Used by** | Mobile app, external integrations. |
| **Integrations** | Entity API (students, teachers, guardians), dashboard layout (siteconfig), search, notifications; serializers touch people, finance, communication. |
| **Automation help** | Token cleanup (expired JWT), rate-limit cleanup. Do **not** automate: changing API permissions or versioning. |
| **Gaps** | (1) Many API endpoints listed as “NEEDED” in docs may be missing. (2) Consistency between API and portal (e.g. same permissions). |
| **Fixes** | Audit API_COMPLETE_GUIDE.md vs implemented endpoints. Ensure permission classes align with portal (e.g. guardian can only see own students). |

---

### 2.16 apps.automation – Automation & background tasks

| Aspect | Detail |
|--------|--------|
| **Depends on** | academics, siteconfig (helpers). |
| **Used by** | finance (AutomationExecutionLog, AutomationApprovalQueue), and potentially evals/others for logging. |
| **Integrations** | Provides execution log and approval queue; finance uses them for invoice generation and optional receipt approval. Helpers: get_current_academic_year, get_current_term, get_cached_site_settings, get_notification_channels. |
| **Automation help** | This is the “automation” layer: any new scheduled or high-impact task should log here and use approval queue when required. |
| **Gaps** | (1) Only finance heavily uses it; evals/analytics/payroll could use ExecutionLog and optional ApprovalQueue. (2) No UI to “retry” failed execution. |
| **Fixes** | When adding new automations (e.g. payroll reminder, report batch), use AutomationExecutionLog and optionally AutomationApprovalQueue. Optional: “Retry” action in admin for failed log entries where safe. |

---

### 2.17 emis – EMIS integration

| Aspect | Detail |
|--------|--------|
| **Depends on** | accounts, academics, people, finance, siteconfig. |
| **Used by** | (external – government reporting). |
| **Integrations** | Exports students, teachers, enrollment, performance (from people, academics, evals if needed), finance (Invoice) for EMIS format. |
| **Automation help** | **Generate** export file on schedule (with optional approval). Do **not** automate: **submitting** to government (manual). |
| **Gaps** | (1) EMIS may need evals data (grades) for “performance”; ensure export includes it and stays in sync with report card logic. (2) No approval step for “generate and submit”. |
| **Fixes** | Document EMIS export fields and source (evals vs reports). Optional: generate export in background, then require manual “submit” or approval before sending. |

---

## 3. Cross-cutting summary

| Topic | Summary |
|-------|--------|
| **Dependencies** | accounts → academics → people form the core; evals, finance, reports, payroll build on them; portal and analytics consume most; requests aggregates from evals, finance, people. |
| **Integration** | Evals ↔ reports (report cards from Evaluation); finance ↔ payroll (compliance/tax); requests ↔ evals/finance/people (unified request center); portal/analytics pull from many. |
| **Automation** | Reminders, invoice generation (with approval), receipt verification, report PDF generation, deadline reminders, retries – all good. Publish, payroll run, void/refund, grade approval, EMIS submit – keep manual or approval-gated. |
| **Guardrails** | Approval queue for high-impact automations; configurable “require approval” for finance; admin override with audit for all critical actions; no silent overwrites. |
| **Gaps** | Grading deadline single source; report publish vs grade approval; “approved grades only” in reports; MFA-for-role; request-center reminders; EMIS/evals consistency; dashboard context consolidation; API coverage. |

---

## 4. Suggested fix priorities

1. **High**: Evals–reports – optional “require approved grades before publish” and “approved grades only” in report context; single source for grading deadline.
2. **High**: Finance – ensure every override (void, reject receipt) has reason + audit.
3. **Medium**: Accounts – `require_mfa_roles` and TOTP recommendation for compliance.
4. **Medium**: Requests – document sync pattern; optional “pending request” reminder task.
5. **Medium**: Automation – use ExecutionLog (and where appropriate ApprovalQueue) for any new automation (payroll reminder, report batch, etc.).
6. **Lower**: Portal – ensure all dashboards use `get_dashboard_context()`; API – align permissions and fill missing endpoints; EMIS – document and optionally add approval for export/submit.

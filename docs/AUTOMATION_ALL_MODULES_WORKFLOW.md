# Automation for All Modules: What to Automate, What Not, Admin Role & Workflow

**Purpose**: One place for automation across **all** modules: what can be automated, what cannot, the role admin plays, a single workflow, and how to remove redundancy and keep things seamless.

**Used by**: [MASTER_PLAN.md](MASTER_PLAN.md) Phase 3 (Automation).

---

## 1. Single automation workflow (seamless, no redundancy)

All automations follow one pattern so behaviour is predictable and admin stays in control.

### 1.1 Standard flow

1. **Trigger** – Schedule (Celery Beat), manual “Run now” in admin, or event (e.g. upload).
2. **Config check** – Read SiteSettings (and feature flags). If automation is disabled for this type, exit without changing data.
3. **High-impact?** – If the task creates/updates many records or money (e.g. bulk invoice generation, payroll run):
   - If SiteSettings say **“require approval”**: create **AutomationApprovalQueue** entry with summary; notify assignees; **stop**. Admin must approve (or reject) in admin. On approve, re-run the task (or a dedicated “execute approved” path).
   - If “require approval” is off: continue to step 4.
4. **Execute** – Run the task. Use **dry-run** where supported (e.g. invoice generation) and show summary before real run when triggered manually.
5. **Log** – Write **AutomationExecutionLog**: task_name, status, records_processed, records_failed, error_message, triggered_by, execution_summary.
6. **Admin override** – Any automated outcome that affects money, grades, or publish status can be **reversed or overridden** in admin (void invoice, reject receipt, unlock term, etc.) with **mandatory reason** and **AuditLog** entry. No automation may prevent admin from doing that.

### 1.2 Principles (no redundancy, easy and seamless)

- **One log, one queue** – All automations use the same `AutomationExecutionLog` and `AutomationApprovalQueue` (no per-module duplicate logging).
- **One config source** – Schedules, thresholds, “require approval”, and channels live in **SiteSettings** (or env read by SiteSettings). No hardcoded limits for production.
- **One notification layer** – Use `get_notification_channels()` and shared communication paths; document when to use Message vs Notification vs PortalNotification to avoid duplicate concepts.
- **Dashboard context** – Every dashboard uses `get_dashboard_context()`; no duplicated layout-loading logic.
- **Single grading deadline** – One canonical source (e.g. SubjectAssignment) for evals/analytics; no leftover GradingDeadline references.

---

## 2. Admin’s role (in all modules)

| Role | What admin can do |
|------|-------------------|
| **Config** | Enable/disable automations per type in Site Settings (e.g. invoice generation, reminders, receipt auto-apply). Set schedules, thresholds, and “require approval” per automation. |
| **Approve / reject** | For tasks that use AutomationApprovalQueue (e.g. bulk invoice generation), admin (or assigned role) approves or rejects. Rejection stops the run; approval triggers execution (or “execute approved” flow). |
| **Override** | Every critical automated action can be overridden: void invoice, reject receipt, reassign receipt, bypass grade approval (with reason), unlock term for edit (if policy allows). Override always requires reason and creates an audit record. |
| **Visibility** | Admin sees AutomationExecutionLog (what ran, when, success/fail, who triggered). Sees AutomationApprovalQueue (pending/approved/rejected). Sees audit trail for overrides (AuditLog / model-specific audit). |
| **Run / retry** | Where safe, admin can “Run now” (e.g. send reminders now, run invoice generation now) or “Retry” a failed execution from the log. Dry-run option where applicable. |
| **No silent bypass** | Automation must not do things that admin cannot later undo or override. No deleting audit logs; no overwriting data that hides history (use status flags, e.g. deactivate reminder). |

---

## 3. Per-module: what to automate vs what not, and admin’s levers

### 3.1 accounts

| Can automate | Do not automate | Admin role / config |
|--------------|------------------|----------------------|
| Password reset emails (triggered by user). | User create/delete, role/permission changes, MFA reset. | No automation toggles here; MFA and roles are admin-only. Optional: `require_mfa_roles` in Site Settings (Phase 4). |
| Session/token cleanup (expired). | | Optional scheduled task; log to ExecutionLog. |
| Optional: “inactive user” reminder (e.g. notify admins). | | Configurable in Site Settings (e.g. inactive days threshold). |

### 3.2 academics

| Can automate | Do not automate | Admin role / config |
|--------------|------------------|----------------------|
| Year/term rollover **clone** (copy structure, fee plans, etc.) with **dry-run** and optional **approval**. | Create/delete years, terms, classrooms without going through rollover or admin UI. | Site Settings: “Rollover require approval” (→ AutomationApprovalQueue). Admin runs rollover from admin or Automation; approves if required. |
| “Term ending in X days” reminder (notify staff). | | Schedule + channels in Site Settings; log to ExecutionLog. |

### 3.3 people

| Can automate | Do not automate | Admin role / config |
|--------------|------------------|----------------------|
| Bulk **export** (no write). Sync from external source only with **approval** (preview + approve). | Student withdrawal, guardian unlink, status changes (active/withdrawn). | Withdrawal/unlink only in admin/portal with audit. Finance signal stops reminders on withdrawal (no extra automation). |
| Optional: “Students without guardian” / “Pending guardian invites” report (read-only). | | Dashboard widget or scheduled report; no approval needed. |

### 3.4 evals

| Can automate | Do not automate | Admin role / config |
|--------------|------------------|----------------------|
| **Deadline reminders** (notify teachers/staff when grading deadline near). | Grade entry, grade approval decisions, changing AssessmentWeights after term publish. | Single grading-deadline source (e.g. SubjectAssignment); schedule/channels in Site Settings; log to ExecutionLog. |
| Bulk import **validation** (preview only). **Apply** import only after admin/teacher confirms. | Auto-apply bulk import without confirmation. | Import apply = manual or approval step. |
| Lock grade entry after term publish (already: is_term_published). | | No automation to “unlock”; admin override only with reason if policy allows. |

### 3.5 finance

| Can automate | Do not automate | Admin role / config |
|--------------|------------------|----------------------|
| Fee **invoice generation** (optional approval queue). Payment **reminders**. Receipt **verification** (pattern match, bank match). **Retry** failed reminders. Bank deposit verification. | **Void** invoice, **refund**, **reject** receipt (admin only). **Apply** payment from receipt can be gated by “require approval” in Site Settings. | All toggles and thresholds in Site Settings. Override: void/reject/reassign require reason + AuditLog. AutomationExecutionLog + AutomationApprovalQueue for invoice generation. |

### 3.6 payroll

| Can automate | Do not automate | Admin role / config |
|--------------|------------------|----------------------|
| **Preview** run (dry-run) on schedule. “Payroll window open – run when ready” **reminder**. | **Actual** payroll run (always manual or via ApprovalQueue). | If payroll run is ever exposed to automation, it must use AutomationApprovalQueue. Reminder: schedule in Site Settings; log to ExecutionLog. |

### 3.7 reports

| Can automate | Do not automate | Admin role / config |
|--------------|------------------|----------------------|
| **Generation** of PDFs for **already-published** terms; cache refresh. | **Publishing** term results (manual). Report content = from evals only (no duplicate storage). | Publish only in Reports UI by admin; optional “require approved grades before publish” and “approved grades only” in report context (Site Settings). Publish action audited. |

### 3.8 portal

| Can automate | Do not automate | Admin role / config |
|--------------|------------------|----------------------|
| Notification **digest** (e.g. daily summary). Cache invalidation when underlying data changes. | Feature toggles, access changes (admin only). | No automation that changes portal features or permissions. Use get_dashboard_context() everywhere to avoid redundant layout logic. |

### 3.9 analytics

| Can automate | Do not automate | Admin role / config |
|--------------|------------------|----------------------|
| **Deadline reminders** (shared with evals; single deadline source). Cache refresh. **ML** batch predictions (e.g. fee default risk) on schedule. | Changing promotion thresholds that affect reports (admin only). | Schedule/channels in Site Settings; log to ExecutionLog. Single grading-deadline source (Phase 2). |

### 3.10 siteconfig

| Can automate | Do not automate | Admin role / config |
|--------------|------------------|----------------------|
| **Cache invalidation** when settings change (e.g. clear layout cache). | Changing settings that affect security/finance/evals (admin only in Site Settings). | All automation **config** lives here (schedules, thresholds, require approval). Layout normalization in one place (dashboard_views); API reuses it. |

### 3.11 compliance

| Can automate | Do not automate | Admin role / config |
|--------------|------------------|----------------------|
| **Audit log retention** (archive or delete old logs by policy). Scheduled **compliance reports** (generate only). | Deleting logs or changing retention **without** approval or policy. | Retention policy in Site Settings or compliance config; optional scheduled task; admin can run report generation manually. |

### 3.12 communication

| Can automate | Do not automate | Admin role / config |
|--------------|------------------|----------------------|
| **Scheduled** announcements (time-based send). “Pending contact request” **reminder** to assignees. | Sending to **entire school** without review (prefer draft + admin publish). | Use single channels config (SiteSettings + get_notification_channels). Document Message vs Notification vs PortalNotification to remove confusion. |

### 3.13 requests

| Can automate | Do not automate | Admin role / config |
|--------------|------------------|----------------------|
| **Reminder** for “pending AccessRequest” to assignees (e.g. N pending). | **Approve/deny** decisions (admin/staff only). | Celery task with interval in Site Settings; log to ExecutionLog. Document how to add new request types and sync to AccessRequest (one workflow). |

### 3.14 observability

| Can automate | Do not automate | Admin role / config |
|--------------|------------------|----------------------|
| Health checks and metrics (on request or scrape). Optional: alerting when health fails (Sentry/external). | N/A. | Lazy imports in health views to avoid circular imports. |

### 3.15 api

| Can automate | Do not automate | Admin role / config |
|--------------|------------------|----------------------|
| **Token cleanup** (expired JWT). **Rate-limit** cleanup. | Changing API permissions or versioning. | Scheduled task; log to ExecutionLog. |

### 3.16 automation (the app)

| Can automate | Do not automate | Admin role / config |
|--------------|------------------|----------------------|
| **Execution logging** (all tasks write here). **Approval queue notifications** (notify when item pending). | **Execution** of a task that is in ApprovalQueue with status PENDING (only after approve). | Admin sees ExecutionLog and ApprovalQueue in admin; optional “Retry” for failed runs where safe. |

### 3.17 emis

| Can automate | Do not automate | Admin role / config |
|--------------|------------------|----------------------|
| **Generate** export file on schedule (optional approval to submit). | **Submitting** to government (manual). | Generate → optional AutomationApprovalQueue “submit”; admin submits from UI. Document evals/report data source for consistency. |

---

## 4. Redundancy removal and improvements (all modules)

| Area | Redundancy / issue | Improvement |
|------|--------------------|------------|
| **Dashboard context** | Duplicated layout-loading and role checks in multiple dashboard views. | Use **get_dashboard_context()** everywhere; **get_user_role()** for role. Already done for main dashboards; verify portal and any new views. |
| **Layout normalization** | Similar logic in dashboard_views and dashboard_layout_api. | **One** normalization function (e.g. _normalize_dashboard_settings); API and views call it. |
| **Notification concepts** | Message, Notification (finance), PortalNotification used inconsistently. | **Document** when to use which; **one** channel config (SiteSettings) and get_notification_channels for automations. |
| **Grading deadline** | GradingDeadline removed; references may remain in analytics/portal/evals. | **Single source** (e.g. SubjectAssignment.grading_deadline_at); remove or redirect all references; deadline reminders use it. |
| **Request center** | Grade approval, report request, leave request sync to AccessRequest via signals; new types may be added ad hoc. | **Document** sync pattern (signal → sync_request_for_target); template for new request types so workflow is one place. |
| **Automation config** | Schedules/thresholds could be scattered. | **Site Settings – Automation** section: one place for “require approval” toggles, schedules, and links to ExecutionLog/ApprovalQueue. |
| **Override actions** | Void, reject, reassign might lack reason or audit. | **Audit** all override actions: mandatory reason (or dropdown) and AuditLog (or model audit). No silent overwrites. |

---

## 5. Checklist: automation coverage by module

- [ ] **accounts** – Token/session cleanup optional; require_mfa_roles in Site Settings (Phase 4).
- [ ] **academics** – Rollover with dry-run + optional approval; term-end reminder; log to ExecutionLog.
- [ ] **people** – No high-impact automation; optional read-only reports; finance signal on withdrawal robust.
- [ ] **evals** – Deadline reminders use single deadline source + ExecutionLog; bulk import apply = manual/approval.
- [ ] **finance** – All current automations log + optional approval; overrides have reason + audit; all config in Site Settings.
- [ ] **payroll** – Reminder only (or preview); actual run manual or ApprovalQueue.
- [ ] **reports** – PDF generation for published terms only; publish manual; publish guard and approved-grades-only (Phase 2).
- [ ] **portal** – Digest/cache only; get_dashboard_context everywhere.
- [ ] **analytics** – Deadline reminders + ML batch use ExecutionLog; single deadline source.
- [ ] **siteconfig** – Cache invalidation; all automation config in Site Settings; layout normalization single place.
- [ ] **compliance** – Retention/reports with policy; no auto-delete without approval.
- [ ] **communication** – Scheduled sends + reminders; one channel config; document Message vs Notification.
- [ ] **requests** – Pending-request reminder; document sync pattern.
- [ ] **observability** – Health/metrics; lazy imports.
- [ ] **api** – Token/rate-limit cleanup; log to ExecutionLog.
- [ ] **automation** – ExecutionLog + ApprovalQueue used by all; admin visibility and optional Retry.
- [ ] **emis** – Generate with optional approval; submit manual; document evals source.

---

## 6. Implementation status (by module)

| Module | Implemented | Notes |
|--------|-------------|--------|
| **accounts** | Partial | MFA/roles in Site Settings; token/session cleanup optional. |
| **academics** | Partial | Rollover/clone from UI; term-end reminder (schedule); dry-run where added. |
| **people** | OK | No bulk automation; finance signal on withdrawal. |
| **evals** | OK | Deadline reminders (dry_run); bulk import preview/apply; single deadline source. |
| **finance** | OK | Invoice gen, payment reminders, receipt verification, status updates; all support dry_run; ExecutionLog + optional ApprovalQueue; overrides with reason. |
| **payroll** | OK | Reminder/preview only; actual run manual. |
| **reports** | OK | Publish manual; PDF generation for published terms; approved-grades guards. |
| **portal** | OK | Digest/cache; get_dashboard_context used. |
| **analytics** | OK | Deadline reminders; ExecutionLog. |
| **siteconfig** | OK | Automation config in Site Settings; layout normalization. |
| **compliance** | OK | Retention/archive commands (dry-run); reports generate only. |
| **communication** | OK | get_notification_channels; SiteSettings + UserPreference. |
| **requests** | OK | Pending-request reminder; sync pattern in place. |
| **automation** | OK | ExecutionLog, ApprovalQueue; Automation Hub at /accounts/workflow/automation/. |
| **api** | OK | Token cleanup; rate-limit cleanup. |
| **emis** | Partial | Generate export; submit manual. |

---

## 7. Reference

- **Module dependencies and gaps**: [ALL_MODULES_DEPENDENCIES_AUTOMATION_GAPS.md](ALL_MODULES_DEPENDENCIES_AUTOMATION_GAPS.md) (if present)
- **Guardrails and Eval–Reportcard**: [AUTOMATION_GUARDRAILS_AND_EVAL_REPORTS.md](AUTOMATION_GUARDRAILS_AND_EVAL_REPORTS.md)
- **Master plan (build order)**: [MASTER_PLAN.md](MASTER_PLAN.md)
- **Automation Hub**: `/accounts/workflow/automation/` — Execution Log, Approval Queue, Site Settings link.

# Automation, Guardrails, EVAL–Reportcard Linkage & Gaps

**Doc status: Closed.** Remaining gaps (warn/block publish when pending grade approvals; optional “approved grades only”; eval status on publish page; remove GradingDeadline refs) are **Closed (Phase 10 / deferred)**. See **`docs/PHASE_10_BACKLOG.md`** and **`docs/WHATS_LEFT_COMPLETE_BACKLOG_DEFERRED.md`**.

**Purpose**: Which modules benefit from automation, what to automate vs not, guardrails so automation cannot do things admin cannot override, EVAL ↔ Reportcard tie-in, gaps to close, and zero-cost MFA for compliance.

---

## 1. Which Modules Benefit from Automation

| Module | Good to automate | Prefer not to automate (or only with approval) |
|--------|-------------------|--------------------------------------------------|
| **accounts** | Password reset emails, session cleanup, preference sync. | User creation/deletion, role changes, MFA reset. |
| **academics** | Year/term rollover cloning (with dry-run + approval option). | Creating/deleting years, terms, classrooms. |
| **people** | Bulk export, sync from external source (with approval). | Student withdrawal, guardian unlink, status changes. |
| **evals** | Deadline reminders, bulk import validation, grade lock after publish. | Grade entry, approval decisions, changing weights after publish. |
| **finance** | Fee invoice generation (with optional approval queue), payment reminders, receipt verification, retry failed reminders. | Applying payment from receipt (can require approval), voiding invoices, refunds. |
| **payroll** | Scheduled payroll run **preview**; reminder to run. | Actual payroll run (always require explicit run or approval). |
| **reports** | Scheduled report **generation** (PDF) for already-published terms; cache refresh. | **Publishing** term results (should stay manual); report card content = from evals. |
| **portal** | Notification digest, cache invalidation. | Feature toggles, access changes. |
| **analytics** | Deadline reminders, cache refresh, ML batch predictions. | Changing thresholds that affect promotions. |
| **siteconfig** | Cache invalidation after settings change. | Changing settings that affect security/finance/evals. |
| **compliance** | Audit log retention, scheduled compliance reports. | Deleting logs, changing retention. |
| **communication** | Scheduled announcements, reminder sends. | Sending to entire school (prefer review). |
| **requests** | Reminder for pending access requests. | Approve/reject (stay manual). |
| **observability** | Health checks, metrics scrape. | N/A. |
| **api** | Rate-limit cleanup, token cleanup. | N/A. |
| **automation** | Execution logging, approval queue notifications. | Execution itself when queued for approval. |
| **emis** | Scheduled export generation (with approval to submit). | Submitting to government (manual). |

---

## 2. What to Automate vs Not Automate

**Do automate (with config + guardrails)**  
- Repetitive, rule-based, reversible or low-impact: reminders, invoice generation (with optional approval), receipt verification, report PDF generation for published data, deadline reminders, retry failed sends.  
- Always: make schedules, thresholds, and templates configurable (SiteSettings or admin).  
- Prefer: dry-run and/or approval queue for high-impact (e.g. bulk invoice generation).

**Do not fully automate (admin must decide)**  
- Irreversible or high-impact: void invoice, refund, withdraw student, publish term results, approve grade batch, payroll run, EMIS submit, role/permission changes.  
- Automation may **propose** (e.g. “these invoices are due”) or **prepare** (e.g. generate PDFs), but the “go live” action stays with a human.

**Guardrails (so automation cannot do what admin cannot override)**  
- **Approval queue**: High-impact automations (e.g. auto-generate invoices) can require `AutomationApprovalQueue`; admin approves/rejects.  
- **Configurable “require approval”**: e.g. `finance_auto_generate_require_approval`, `finance_receipt_require_admin_approval` so auto-apply is optional.  
- **Admin override**: Every automated financial action (apply payment, void, refund) must be overridable in admin with audit (who, when, reason).  
- **Audit trail**: All automation actions and overrides logged (AuditLog / AutomationExecutionLog / PaymentProofUpload status, etc.).  
- **No silent overwrite**: Automation must not delete or overwrite data that would hide history; use status flags and soft logic (e.g. deactivate reminder, don’t delete).  
- **Feature flags**: Critical automations (reminders, receipt auto-apply) gated by SiteSettings so they can be turned off.

---

## 3. EVAL and Reportcard (Tie-In and Gaps)

**Existing tie (already in place)**  
- **Reports** pulls grade data from **evals**:  
  - `apps/reports/services.py` uses `Evaluation`, `AssessmentWeights`, and `evals.services` (`classroom_term_rankings`, `school_term_rankings`) to build `term_report_context` and `annual_report_context`.  
- Report cards are therefore **already tied to evals**: same `Evaluation` rows drive both grading UI and report card content.  
- Term **publish** (`TermPublishStatus`) locks further grade entry for that term (evals checks `is_term_published` and disallows edits).  
- So: **data linkage** and **lock-after-publish** are in place.

**Gaps to close**  
1. **Publish vs grade approval**  
   - When `grade_approval_enabled` is True, staff can still **publish** a term from Reports even if some grades are not yet approved.  
   - **Recommendation**: On the publish-term page (or in the publish action), optionally **warn or block** if there are pending `GradeApprovalRequest` for that term (e.g. “N pending grade approvals for this term. Approve them before publishing?” or “Publish only after all grades are approved”). Make this configurable (e.g. `reports_require_approved_grades_before_publish`).  

2. **Report context “approved only”**  
   - Today report context includes **all** evaluations for the term. If a school uses approval workflow, you may want report cards to show only **approved** grades (e.g. exclude evaluations still in pending approval).  
   - **Recommendation**: Add a SiteSettings flag (e.g. `reports_use_approved_grades_only`) and in `term_report_context` / `annual_report_context` filter `Evaluation` by linked `GradeApprovalRequest` status when the flag is True (e.g. only include where approval status = APPROVED or no approval required for that submission).  

3. **Single source of truth**  
   - Keep report card content **read-only from evals**: no duplicate “report card grade” model; report always computed from `Evaluation` + `AssessmentWeights`. Already the case; document it and avoid adding parallel grade storage in reports.  

4. **Visibility**  
   - In Reports publish UI, show a short “Eval status” summary for the term (e.g. “All grades approved” / “N subjects pending approval”) so the person publishing is informed.  

**Summary**  
- EVAL is already tied to Reportcard via shared `Evaluation` data and report services.  
- Remaining gaps: enforce or warn on “approve before publish” when grade approval is enabled, optional “approved grades only” in report context, and clearer visibility of approval status on the publish page.

---

## 4. Potential / Existing Gaps to Close

**Evals**  
- Restore or replace **GradingDeadline**-based behaviour where needed (e.g. `SubjectAssignment.grading_deadline_at` or a dedicated deadline model) so deadline reminders and analytics are consistent (see CODE_REVIEW_GAPS_REDUNDANCIES.md).  
- Ensure no remaining references to deleted `GradingDeadline` model; use a single source for “grading deadline” (e.g. `SubjectAssignment` or a small evals deadline model).

**Reports**  
- **Publish guard**: When grade approval is on, require or strongly warn that all grades are approved before allowing publish (see above).  
- **Approved-only report context**: Optional filter so report cards only show approved grades when the school uses approval workflow.  
- **Audit**: Ensure every “Publish term” action is audited (e.g. ReportCardAudit or compliance AuditLog) with user and timestamp.

**Finance**  
- Already has strong guardrails: approval queue for auto-invoice generation, optional receipt approval, fraud checks, overpayment handling.  
- Ensure **void invoice** and **reject receipt** are always available in admin with mandatory reason and audit.

**Automation**  
- **Approval queue**: Use `AutomationApprovalQueue` for any automation that creates or modifies financial or academic records (e.g. bulk invoice generation); do not auto-execute without approval when configured.  
- **Dry-run**: Where possible (e.g. invoice generation, payroll preview), support dry-run and show summary before real run.

**Compliance / MFA**  
- **Zero-cost MFA**: Use **TOTP** (e.g. **django_otp** with `otp_totp`) as the default MFA. It is already in the stack and is **zero marginal cost** (no SMS/email). Recommend TOTP for compliance; SMS/email as optional second factor only if the school pays for those channels.  
- Document that MFA is available and recommended for admin/finance staff; optionally require MFA for sensitive roles via policy or a “require MFA for role” setting.

**Cross-cutting**  
- **Dashboard context**: Already consolidated with `get_dashboard_context()` (see CODE_REVIEW_GAPS_REDUNDANCIES.md).  
- **Role helper**: Use `get_user_role()` consistently.  
- **Config over code**: All automation thresholds, schedules, and “require approval” flags in SiteSettings or admin, not hardcoded.

---

## 5. Zero-Cost MFA for Compliance

**Recommendation: TOTP (django_otp)**  
- **django_otp** with **TOTP** is already in the project (`requirements.txt`, `config/settings.py`, `apps/accounts/views_mfa.py`).  
- TOTP is **zero marginal cost**: no SMS or email sending; users use an authenticator app (Google Authenticator, Authy, etc.).  
- Satisfies “something you have” (phone/app) + “something you know” (password) for compliance.  

**Use for compliance**  
- Enable MFA in SiteSettings; encourage or require it for **admin**, **finance**, and **staff** roles.  
- Keep SMS/email 2FA as optional extras if the school has budget; for “zero cost”, rely on TOTP only.  
- **SiteSettings.require_mfa_roles**: when set (e.g. `["ADMIN","BURSAR"]`), users with that role must have TOTP; middleware redirects to MFA setup. TOTP = zero marginal cost. MFA is available and recommended/required for admin and finance.

---

## 6. Quick Reference

- **Automate**: Reminders, receipt verification, invoice generation (with optional approval), report PDF generation for published terms, deadline reminders, retries.  
- **Do not automate without approval**: Publish term, payroll run, void/refund, grade approval, EMIS submit, user/role changes.  
- **Guardrails**: Approval queue for high-impact automations, configurable “require approval” for finance, admin override with audit for all critical actions, no silent overwrites.  
- **Eval ↔ Reportcard**: Already tied via `Evaluation` in report services; close gaps by optional “approve before publish” and “approved grades only” in report context.  
- **MFA**: Use existing TOTP (django_otp) as zero-cost option for compliance.

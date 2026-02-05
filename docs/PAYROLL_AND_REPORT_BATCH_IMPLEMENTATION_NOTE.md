# Payroll Reminder & Scheduled Report Batch – Implementation Note (Future)

**Purpose**: When adding "payroll reminder" or "scheduled report batch" features, follow the same automation pattern as finance and analytics so they are configurable, audited, and optionally approval-gated.

## Requirements (from Master Plan Phase 3.2)

- Implement with **AutomationExecutionLog** from the start: create a log at task start, call `mark_completed(SUCCESS|FAILED|PARTIAL, ...)` on exit.
- Use **AutomationApprovalQueue** when the action is high-impact (e.g. bulk report generation) and Site Settings say "require approval".
- **Config in Site Settings**: schedules, thresholds, and "require approval" flags in Site Settings (or env), not hardcoded.
- Add settings to the **Automation** section in the Site Settings sidebar (or link to existing finance/evals fields).

## Pattern to follow

1. **Celery task**  
   - Create `AutomationExecutionLog` at start (`task_name`, `execution_type=SCHEDULED` or `MANUAL`, `status=PENDING`).  
   - In `try`/`except`, call `execution_log.mark_completed(Status.SUCCESS|FAILED|PARTIAL, records_processed=..., summary=...)`.  
   - If approval required: create `AutomationApprovalQueue` entry and mark log as success with summary `pending_approval`; actual execution runs only after admin approval.

2. **Site Settings**  
   - Add fields such as: `payroll_reminder_enabled`, `payroll_reminder_interval_hours`, `report_batch_require_approval`, `report_batch_schedule` (JSON or similar).  
   - Expose them under Compliance & Payroll or a new "Automation" subsection.

3. **Celery Beat**  
   - Add the new task(s) to `CELERY_BEAT_SCHEDULE` in `config/settings.py` with an appropriate schedule; task body should check Site Settings and no-op when disabled.

## Reference implementations

- **Finance**: `apps/finance/tasks.py` – `send_payment_reminders_task`, `auto_generate_fee_invoices_task` (ExecutionLog + optional ApprovalQueue).  
- **Analytics**: `apps/analytics/tasks.py` – `send_deadline_reminders_task` (ExecutionLog; schedule from SiteSettings.teacher_deadline_reminder_days).  
- **Requests**: `apps/requests/tasks.py` – `remind_pending_assignees_task` (interval from SiteSettings.requests_reminder_interval_hours).

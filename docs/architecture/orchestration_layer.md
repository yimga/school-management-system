# Orchestration layer for long-running processes

**Purpose:** First-class orchestration for admissions, re-enrollment, migration, fee collection follow-up, intervention escalation, approval chains. Master Platform Checklist §7.3, §7.4.

## Current implementation

- **Migration:** `apps.automation.models.MigrationRun` — stateful run (status, started_at, completed_at, execution_summary, row counts); operator visibility at `/super/migration/` (super_migration_cloud); rollback via trigger_rollback. Reference flow: migration run is the canonical long-running process with state and visibility.
- **Automation execution:** `apps.automation.models.AutomationExecutionLog` — task_name, school, status, records_processed, records_failed, execution_summary, triggered_by. Tracks scheduled/manual/dry-run execution.
- **Approval queue:** `apps.automation.models.AutomationApprovalQueue` — pending/approved/rejected/executed; links to AutomationExecutionLog for runs that require approval before execution.
- **Workflow engine:** `apps.siteconfig.workflow_engine` — WorkflowConfig, run steps, emit_event action; triggers and actions are config-driven.

## Capabilities (implemented or stubbed)

| Capability | Status | Where |
|------------|--------|--------|
| Long-running state tracking | Done | MigrationRun, AutomationExecutionLog |
| Retries | Partial | DomainEvent.retry_count; consumer retries in events/tasks. Orchestration-level retry (e.g. re-run migration) via UI or API |
| Compensation/rollback | Done | MigrationRun.trigger_rollback, rollback_snapshot |
| SLA tracking | Stub | execution_summary can hold duration; no SLA alerting yet |
| Operator visibility | Done | /super/migration/ (MigrationRun list and context); AutomationExecutionLog in admin |

## Reference flow

Migration: profile selection → dry-run or run → MigrationRun created → state (running/completed/failed) → scorecard in execution_summary → operator sees list at super_migration_cloud. Rollback available for runs that support it.

## Extensions (future)

- Admissions: formal orchestration run for application pipeline (stages, decisions, notifications).
- Fee collection follow-up: workflow or automation run for reminder sequences.
- Intervention escalation: workflow-driven escalation with state and visibility.
- All orchestration runs: unified list/detail view in control plane with status, duration, retry, and rollback where applicable.

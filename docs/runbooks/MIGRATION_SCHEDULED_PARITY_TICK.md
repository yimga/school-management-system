# Migration scheduled parity tick (§0.1.5 Wave 5)

## Behavior

- Celery Beat task **`automation.migration_scheduled_parity_tick`** runs **daily** (`CELERY_BEAT_SCHEDULE`).
- Each run appends an **`AutomationExecutionLog`** with `task_name=migration.scheduled_parity_tick` and summary:
  - `open_exception_runs` — runs awaiting operator acknowledgement
  - `pending_quarantine_rows` — quarantine records still `PENDING`
  - `migration_runs_last_7d` — volume signal for ops

## Full CSV diff vs source

- Row-level CSV diff against an external SIS export remains **operator-driven** (migration wizard, BR internal APIs). This tick **does not** pull third-party files; it **schedules telemetry** so dashboards/alerts can be wired to log volume.

## Evidence

- Task: `apps/automation/tasks.py` — `migration_scheduled_parity_tick`
- Test: `apps/automation/tests/test_sot_0155_migration_queue_and_schedule.py` — `MigrationScheduledParityTickTests`

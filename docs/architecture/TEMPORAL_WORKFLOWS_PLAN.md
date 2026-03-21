# Temporal (or Celery durable chains) — long-running workflows

**Until Temporal:** Use Celery chains with idempotency keys on each step; store workflow state in `MigrationRun` / `WorkflowRunLog`.

**With Temporal:** Migrate pack-apply, bulk migration, and multi-step cutover to durable workflows with automatic retry and visibility UI.

**Trigger:** When migration runs exceed 15 minutes wall-clock or require human approval gates mid-flight.

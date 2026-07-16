# apps/automation

> Two engines under one label: the Salesforce-style visual workflow graph, and
> the Migration Cloud's profile / playbook / quarantine records.

**Tenancy:** SHARED (public schema; tenant-owned rows carry an explicit `school` FK — there is no per-tenant schema here)
**Scale:** 12 models · 21 migrations · 23 test modules · ~9.6k LOC

## What this app owns

Automation holds two distinct engines that share this app label for historical
reasons, and knowing which one you are in saves a lot of confusion.

**The workflow engine** is a relational visual graph — `Workflow` composed of
`WorkflowNode` + `WorkflowEdge`, drawn in a canvas, validated, published, and run.
It does not interpret the graph itself: `graph_compiler.py` compiles nodes/edges
into the condition/action DSL that `apps.siteconfig.workflow_engine` consumes. This
app owns the graph, the versioning, the validation guardrails, the trigger routing,
and the audit rows — not the execution semantics.

**The Migration Cloud records** (`MigrationProfile`, `MigrationPlaybook`,
`MigrationRun`, `MigrationQuarantineRecord`) are the platform-level registry and
audit trail for data-migration runs, plus the repair/quarantine engine for rows that
fail validation. The connectors and landers themselves live in
`apps/migration_cloud`.

The key design decision on the workflow side is that **a run is bound to the version
it was triggered on**. Publishing snapshots the graph into a `WorkflowVersion`, and
`WorkflowRunLog` binds to that snapshot — so an in-flight run keeps executing the
graph it started with even if the author edits and republishes mid-flight.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `Workflow` | `automation_workflow` | Tenant-scoped workflow graph; status `draft`/`published`/`paused`/`failed`/`archived` |
| `WorkflowNode` | `automation_workflownode` | One canvas node: trigger \| condition \| action \| delay |
| `WorkflowEdge` | `automation_workflowedge` | Directed edge between two nodes |
| `WorkflowVersion` | `automation_workflowversion` | Frozen graph snapshot taken at publish time |
| `WorkflowRunLog` | `automation_workflowrunlog` | Execution audit for `visual_executor.run_workflow`, bound to a `WorkflowVersion` |
| `WorkflowStepEvent` | `automation_workflowstepevent` | Append-only per-step event log for a `WorkflowRunLog` |
| `AutomationExecutionLog` | `automation_automationexecutionlog` | Task execution history; one row per handler invocation from `trigger_dispatcher.fire` |
| `AutomationApprovalQueue` | `automation_automationapprovalqueue` | Automations requiring approval before execution |
| `MigrationProfile` | `automation_migrationprofile` | Platform-level registry of migration connector profiles |
| `MigrationPlaybook` | `automation_migrationplaybook` | Ordered list of profile slugs run in sequence |
| `MigrationRun` | `automation_migrationrun` | Audit record for a migration run; `rollback_snapshot` drives reverts |
| `MigrationQuarantineRecord` | `automation_migrationquarantinerecord` | Rows that failed validation or need repair |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Celery task | `migration_scheduled_parity_tick` | Scheduled migration parity check |
| Module | `visual_executor` | Runs a `Workflow`; binds the run to the current version, writes `WorkflowRunLog` |
| Module | `graph_compiler` | Nodes/edges → DSL; `normalize_action_dict` maps Salesforce-style names to engine handlers |
| Module | `graph_validate` | `validate_workflow_for_publish` — publish guardrails (see below) |
| Module | `trigger_dispatcher` | In-process `trigger_key -> [handler]` registry; `@register_handler`; `fire(...)` |
| Module | `domain_event_bridge` | Bridges persisted `events.DomainEvent` rows to `fire()` |
| Module | `workflow_limits` | `MAX_DOMAIN_EVENT_CHAIN_DEPTH = 8` |
| Module | `visual_workflow_versioning` | Publish-time snapshot + `bind_run_to_current_version` |
| Module | `playbook_executor` | Runs profiles in sequence, one `MigrationRun` per step |
| Module | `quarantine_services` | Add to quarantine, mark repaired, replay the repaired subset |
| Module | `rollback_handlers` | Per-`migration_type` rollback registry driven by `run.rollback_snapshot` |
| Module | `schema_fingerprint` | Suggests a `MigrationProfile` from column headers, with a confidence score |
| Commands | `seed_migration_profiles`, `migration_legacy_data_audit` | |
| URLs | `visual_workflow_designer`, `visual_workflow_list`, `visual_workflow_save_graph`, `visual_workflow_validate_graph`, `visual_workflow_simulate`, `visual_workflow_publish`, `visual_workflow_rollback`, `visual_workflow_dispatch_test`, `workflow_template_gallery`, `workflow_template_dry_run`, `outcomes_console` | |

## Before you change this

- **Automations recurse, and the guard is the only thing stopping a storm.** A
  workflow action fires a domain event, which dispatches to a workflow, which fires
  an event. `MAX_DOMAIN_EVENT_CHAIN_DEPTH = 8` in `workflow_limits.py` bounds the
  chain, and `domain_event_bridge` dedups on the event pk via a cache key with a 24h
  TTL. Both are load-bearing. There is a dedicated recursion-guard test module —
  keep it green.
- **A run must keep its version.** `visual_executor` binds the run to the current
  `WorkflowVersion` at start. If you make runs read the live graph instead, an author
  editing mid-flight silently changes the semantics of executions already in progress.
- **The event-type → trigger-key map is an alias table, not a rename.** Both
  `payment_success` and `payment.success` and `payment_received` land on the same
  trigger key. Adding an event type without adding its alias means the trigger
  catalog lists it but nothing ever fires — that is exactly the gap
  `domain_event_bridge` was written to close.
- **A failing handler must not block its siblings.** `fire()` records failures as
  `FAILED` `AutomationExecutionLog` rows and only re-raises when
  `raise_on_first_error=True`. One broken workflow must not take down the dispatch of
  every other workflow on that event.
- **The dispatcher is import-safe on purpose**: no Django models at import time,
  `AutomationExecutionLog` is imported inside `fire`. Keep model imports out of
  module scope — `AppConfig.ready` registers the subscriber at app load.
- **Publish guardrails are deliberate, not bureaucracy.** `validate_workflow_for_publish`
  requires at least one trigger, one condition, and one action node; the graph to be
  weakly connected from the first trigger; and `workflow.trigger_event` to match the
  visual trigger node's config. A disconnected node is a node that will never run.
- **Rollback only reverts what the snapshot recorded.** `rollback_handlers` work off
  `run.rollback_snapshot` (`created_ids` / `updated_ids`). A migration type with no
  registered handler has no revert path — check before you promise one.
- **This app is SHARED but its workflow and migration rows are tenant-owned** via an
  explicit `school` FK. There is no schema boundary protecting you here: every query
  on `Workflow` / `MigrationRun` / `AutomationExecutionLog` /
  `MigrationQuarantineRecord` / `AutomationApprovalQueue` must be `school=`-scoped
  (`scan_tenant_queryset_safety.py`, baseline 0).
- Migration *connectors and landers* are in `apps/migration_cloud` — this app holds
  the profiles, playbooks, run audit, and quarantine only.

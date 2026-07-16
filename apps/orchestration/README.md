# apps/orchestration

> Long-running, multi-step processes (admissions, re-enrollment, fee follow-up)
> with retries, compensation, an event-sourced step log, and SLO rollups.

**Tenancy:** SHARED (public schema; runs are scoped by an explicit `school` FK, not by a Postgres schema)
**Scale:** 5 models · 4 migrations · 7 test modules · ~2.4k LOC

## What this app owns

Orchestration is the engine for work that cannot finish inside one request. A
`ProcessDefinition` declares a process type; an `OrchestrationRun` is one
execution of it, carrying state, retry count, and compensation status; every
transition appends an `OrchestrationStepEvent`. Domain apps supply the actual
logic by subclassing `BaseOrchestrationRunner` and implementing `run_step()` —
this app owns the driving loop, the durability, and the observability, not the
business rules.

Two design decisions define it. First, **it is event-sourced**: the step event log
is append-only and the aggregates on `OrchestrationRun` are *projections* over
those events, which is what makes a run replayable and auditable. Second, **runs
bind to a frozen definition version**. Publishing a `ProcessDefinition` snapshots
it into a `ProcessDefinitionVersion` and bumps `current_version`; a run captures
the version that was current when it was created. That is why a re-deploy or a
definition edit never breaks in-flight work — the run keeps executing the
contract it started under.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `ProcessDefinition` | `orchestration_processdefinition` | A process type (unique `code`), its config schema, and its monotonic `current_version`. |
| `ProcessDefinitionVersion` | `orchestration_processdefinitionversion` | Frozen snapshot of a definition at publish time. Runs bind here, not to the mutable definition. |
| `OrchestrationRun` | `orchestration_orchestrationrun` | One execution: state, retries, compensation. Carries the `school` FK — this is the tenant scope. |
| `OrchestrationStepEvent` | `orchestration_orchestrationstepevent` | Append-only event log. Every transition, retry, compensation, and external call lands a row. |
| `OrchestrationSLOMetric` | `orchestration_orchestrationslometric` | Rolled-up snapshot per definition per window: p50/p95/p99 latency, success rate, queue depth. |

All five models the app declares are listed.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Celery task | `process_due_runs` | Primary execution path; wraps the mgmt command so there is one code path |
| Celery task | `trigger_runs_for_definition` | Creates runs for a definition |
| Celery task | `aggregate_slos` | Rolls up `OrchestrationSLOMetric` rows |
| Mgmt command | `process_orchestration_runs` | Cron fallback for the drive loop |
| Mgmt command | `trigger_orchestration_runs` | Cron fallback for triggering |
| Mgmt command | `seed_process_definitions` | Seeds definitions |
| URL | `operator_workbench`, `retry_run` | Operator surface |
| URL | `api_runs_list_or_create`, `api_run_detail`, `api_run_events`, `api_run_retry`, `api_run_cancel`, `api_slo_snapshot` | JSON API |
| Module | `runners` | `BaseOrchestrationRunner` — subclass and implement `run_step()` |
| Module | `event_log` | `emit(...)` — the only correct way to append a step event |
| Module | `versioning` | `publish_new_version(...)` |
| Module | `auth_helpers` | Bearer-JWT acceptance alongside session auth |

**Doc drift, not a surface:** the `OrchestrationSLOMetric` docstring names an
`aggregate_orchestration_slos` management command. **No such command exists** —
the app ships only the three commands listed above. SLO rollup runs via the
`aggregate_slos` Celery task (`tasks.py`) calling `slo_aggregator`. Trust this
table over that docstring.

## Before you change this

- **Append step events through `event_log.emit()`, never `objects.create()`.**
  `sequence_number` is assigned in-transaction under `select_for_update()`
  precisely so concurrent writers do not collide. A direct create races and
  corrupts the ordering the whole replay/audit story depends on.
- **Aggregates on `OrchestrationRun` are projections.** If you add a counter or a
  status, derive it from the events — do not write it as an independent source of
  truth, or replay stops reproducing reality.
- **A run's definition version is frozen at creation and must stay frozen.**
  Re-pointing an in-flight run at `definition.current_version` to "pick up the
  fix" defeats the entire versioning move. Publish a new version; new runs get it.
- **`process_due_runs` deliberately wraps the management command** rather than
  reimplementing the loop. Keep it that way — the two paths existing (Celery
  primary, cron fallback) is only safe while they are literally the same code.
- **Its error handling is asymmetric on purpose:** transient DB errors re-raise so
  Celery retries; other errors are logged and swallowed because the next tick
  picks up where it left off. Do not make it uniformly fatal — a poison run would
  then stall every other tenant's work.
- **`auth_helpers` authenticates but does not authorize.** Accepting a Bearer JWT
  resolves a user; it does **not** bypass any view's checks, and the tenant-scope
  filtering in `api.py` still runs on `request.user` / `request.school`. If you
  add an endpoint, the scope filter is yours to write — the auth helper will not
  do it for you.
- **`OrchestrationRun.school` is `null=True`** — a run with no tenant is
  representable, so a queryset that forgets to filter returns other tenants' runs
  *and* platform-level ones. The boundary guard in `apps.tenancy` verifies an
  explicit `school_id` against the request pin, but it cannot help a query that
  never mentions a school at all. Filter explicitly; there is a
  `(school, definition, -created_at)` index for exactly this.
- **`definition_version` is also `null=True`**, so "every run is bound to a frozen
  version" is the intent, not a database guarantee — rows predating the versioning
  move carry `NULL`. Handle the unbound case rather than assuming it away.

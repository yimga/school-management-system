# apps/platform_runtime

> The platform's runtime substrate: the effective-config resolver, the workflow
> progress bus, the event bus, the in-process periodic scheduler, and the
> operator-side tenant fleet surfaces.

**Tenancy:** SHARED (public schema; rows are scoped by an explicit `school` / `tenant_schema` reference, not by a Postgres schema)
**Scale:** 53 models · 96 migrations · 286 test modules · ~91k LOC

## What this app owns

`platform_runtime` is the layer *underneath* the product apps. Where `finance`
owns invoices and `academics` owns lessons, this app owns the machinery all of
them run on: how a config value is resolved for a tenant, how a long-running
operation reports progress, how an event reaches an in-process subscriber and an
outbound webhook, how periodic work fires in a topology with no Celery beat, and
how a platform operator observes and acts on the tenant fleet.

The load-bearing design decision is the **config cascade**. `RuntimeDefaults` is
a singleton (`id=1`) holding platform-level defaults: ~116 typed first-class
columns plus a JSON `payload` for everything else. `helpers.get_effective_site_settings`
is the ONE merged, request/TTL-cached resolver, layering `RuntimeDefaults` base →
`School.settings` → the wizard overlay at `School.settings["runtime_defaults"]`.
First-class columns override `payload` for their keys, never duplicate it.
`config_resolver.get_effective_config(school, key)` is the canonical single-key
facade over that resolver — it delegates, it does not re-implement precedence or
re-query the ORM. A separate module, `precedence.py`, declares the wider runtime
chain (platform default → registry → blueprint → policy bundle → entitlement gate
→ tenant override → sandbox/preview) that blueprint and pack installs merge by.

The second decision worth knowing before you touch anything: **`periodic.py` is a
scheduler that assumes no worker exists.** Production runs web + Valkey + Postgres
with no Celery worker, so with `CELERY_BROKER_URL` unset Celery is EAGER and
nothing fires the ~90 `CELERY_BEAT_SCHEDULE` entries. This module hangs a
throttled, non-blocking auto-trigger off the constantly-pinged `/health/` view,
guarded by a shared `cache.add()` lock plus a cached `last_run` stamp so a job
does not double-fire across the worker fleet. Every registered job delegates to
the same callable its Celery task uses, so adding a real worker later is not a
rewrite.

## Key models

53 models live here. These are the ones that carry the app's core contracts —
the rest are operator navigation rows, snapshots, and per-surface link tables.

| Model | Table | Purpose |
| --- | --- | --- |
| `RuntimeDefaults` | `platform_runtime_runtimedefaults` | The `id=1` singleton at the base of the config cascade: ~116 typed first-class columns + a JSON `payload`. Saving it invalidates the effective-settings cache. |
| `WorkflowRun` | `platform_runtime_workflowrun` | One row per platform workflow invocation (`@track_workflow`). Carries `tenant_schema` + `school_id` + actor for scoping, status + heartbeat for stuck-detection, and `suggested_remediation` JSON. |
| `WorkflowStep` | `platform_runtime_workflowstep` | One ordered step inside a run — the "step train" the progress chip draws. Append-only by convention. |
| `WorkflowSlaBreach` | `platform_runtime_workflowslabreach` | Operator-visible breach row when a run exceeds the registry's `slo_seconds`. |
| `WorkflowDurationStat` | `platform_runtime_workflowdurationstat` | Rolling duration rollup per `workflow_key`, used for predictive degrading. |
| `WorkflowAutopilotPolicy` | `platform_runtime_workflowautopilotpolicy` | Per-workflow (optionally per-tenant) allowlist of fix kinds permitted to run unattended. |
| `WorkflowAutopilotApplyLog` | `platform_runtime_workflowautopilotapplylog` | Audit trail for every manual and autopilot fix application. |
| `PlatformEventLog` | `platform_runtime_platformeventlog` | The event store behind `event_bus.publish_event`. A proxy over the same table, `PlatformEvent`, is what the pub/sub and replay APIs import — same rows, no second table. |
| `EventWebhookSubscription` | `platform_runtime_eventwebhooksubscription` | A tenant/integration endpoint subscribed to platform events (POST JSON). |
| `EventWebhookDelivery` | `platform_runtime_eventwebhookdelivery` | One outbound attempt: retry state and dead-letter posture, tied to a logged event. |
| `OfflineAction` | `platform_runtime_offlineaction` | Server-stored durable queue for work captured offline (attendance, grading, payment proof) with a queued/syncing/synced/failed/conflict lifecycle. |
| `ScheduledJobHeartbeat` | `platform_runtime_scheduledjobheartbeat` | Last-known execution state of one registered periodic job — how the no-beat topology proves a job actually ran. |
| `TenantConnectivityHeartbeat` | `platform_runtime_tenantheartbeat` | Edge/tenant phone-home so operators can see whether a school is online. |
| `OperatorTenantAssignment` | `platform_runtime_operatortenantassignment` | Scopes which platform operators may access / impersonate which tenants. |
| `HealthRemediationLog` | `platform_runtime_healthremediationlog` | School-attributed audit trail for the health self-healing engine. |
| `BlueprintInstallation` | `platform_runtime_blueprintinstallation` | Tenant-scoped blueprint install state and rollback posture. |
| `PackInstallation` | `platform_runtime_packinstallation` | Tenant-scoped workflow/dashboard/policy pack install state. |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `helpers` | `get_effective_site_settings` — the ONE merged, cached config resolver. |
| Module | `config_resolver` | `get_effective_config(school, key)` — the canonical single-key facade over it. |
| Module | `runtime_defaults_first_class` | The first-class field-name tuple; must stay in lockstep with the model + migration. |
| Module | `precedence` | The 7-step runtime precedence chain and its merge helpers. |
| Module | `periodic` | In-process job dispatcher; `maybe_run_due_jobs()` (auto, via `/health/`), `run_due_jobs()` / `run_job()` (explicit). |
| Module | `event_bus` | `publish_event` / `register_subscriber` / `replay_event` + webhook fan-out with backoff `(5, 30, 120, 600, 1800)`, max 5 attempts. |
| Module | `workflow_registry` | In-process `WORKFLOWS` dict — code-truth, not a DB model, no migrations. |
| Module | `append_only` | `AppendOnlyManager` / `AppendOnlyModelMixin` — raises on ORM delete; also imported by `migration_cloud`. |
| Module | `offline_queue` | `OfflineAction` apply paths + the merged sync-bar state shared with `sync_engine`. |
| Celery task | `process_offline_queues_due` | Drains due offline queues. |
| Celery task | `deliver_event_webhook_task`, `sweep_event_webhook_deliveries_task` | Webhook delivery + dead-letter sweep. |
| Celery task | `scheduled_job_health_monitor_task` | Watches `ScheduledJobHeartbeat` staleness. |
| Celery task | `workflow_sla_breach_alert_sweep_task`, `workflow_stuck_alert_sweep_task` | Workflow SLA + stuck-run alerting. |
| Celery task | `workflow_failed_provision_auto_requeue_sweep_task` | Re-queues failed provisioning runs. |
| Celery task | `tenant_reactivation_sweep_task`, `database_connectivity_heartbeat`, `operator_visibility_heartbeat` | Fleet lifecycle + liveness. |
| Command | `run_periodic_jobs` | The explicit (cron / Render-cron) trigger for the periodic registry. |
| Command | `apply_platform_migration` | Drives a `SchemaRollout` apply cycle across DB aliases. |
| Command | `backfill_runtime_defaults`, `suggest_next_runtime_defaults_fields` | Cascade maintenance. |
| Command | `replay_platform_event` | Re-invokes subscribers (and optionally webhooks) for one stored event. |
| Command | `health_autopilot_sweep`, `monitor_scheduled_job_health`, `run_tenant_lifecycle_scheduler` | Fleet health + lifecycle. |
| URL | `platform_health_center`, `workflow_progress_*`, `health_autopilot_*`, `tenant_lifecycle_dashboard`, `remote_support_*`, `newsletter_*` | Operator + tenant runtime surfaces. |

## Before you change this

- **Adding a first-class config field is a five-step lockstep, not one edit.**
  A new typed `RuntimeDefaults` column needs: the model field, a migration, an
  entry in `RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES`, the `EXACT_FIELD_OWNERS`
  classification, and the `siteconfig` brand-payload tuple. Marketplace *secrets*
  additionally need a new tenant site-settings virtual key and follow the
  `0029`–`0037` migration pattern. Parity is enforced statically by
  `scripts/verify_marketplace_integration_first_class_parity.py` and
  `scripts/verify_runtime_defaults_model_parity.py` — the module docstring says
  so explicitly.
- **Do not add a second config resolver.** `get_effective_site_settings` is the
  only one; `get_effective_config` and `siteconfig.config_service` are the two
  facades over it, and they are complementary layers, not rivals.
  `scan_config_resolver_fragmentation.py` is a zero-baseline one-way ratchet:
  new code reads one key via `get_effective_config` or one domain object via
  `config_service`, never one more raw namespace grab. The resolver is
  deliberately fail-soft and may return `None` very early in boot or on a broken
  singleton — `get_effective_config` returns your `default` in that case, so do
  not "fix" that by raising.
- **`/health/` must never block.** `maybe_run_due_jobs()` does a pure in-memory
  monotonic-throttle check on the request thread and then spawns at most one
  daemon thread per `SCAN_THROTTLE_SECONDS` per process to do cache I/O and job
  execution. This shape is deliberate: a blocking health probe was already a
  502 crash-loop once. Do not move cache reads or job work onto the request path.
  Registered jobs must stay LIGHT and idempotent — the cross-worker `cache.add()`
  lock is genuinely cluster-wide only where the cache is Valkey; on LocMem (local
  dev) the guarantee degrades to per-process.
- **Every periodic job must delegate to the same callable its Celery task calls.**
  That equivalence is what makes turning on a real worker a no-op rather than a
  migration. Do not inline job logic into `periodic.py`.
- **Event-bus subscribers must not raise.** `_notify_subscribers` logs and
  swallows exceptions by contract; a failing subscriber must never break the
  publisher. Register subscribers from `AppConfig.ready`, which is itself written
  as a chain of independent `try/except` blocks precisely so one broken
  registration cannot take the whole app down at boot.
- **`WorkflowStep` and the audit/delivery logs are append-only.** They use
  `AppendOnlyManager`, so `.delete()` on an instance or a queryset raises
  `AppendOnlyDeleteError` (a `PermissionDenied` subclass). If you need to remove
  rows, that is a deliberate raw-SQL decision, not an ORM call.
- **`workflow_registry` is code-truth with no DB model and no migrations** — the
  same posture as `role_registry`, `wedge_line_registry`, and `rmc_os_nav_registry`.
  Its audience values are surface-kind labels (operator / tenant-admin / teacher /
  parent / student / founder / public), NOT role names; any actual role comparison
  must route through `role_registry` per the no-hardcoding contract.
- **This app is SHARED, so nothing is isolated for you.** Rows carry an explicit
  `school` FK or `tenant_schema` string; there is no Postgres schema doing the
  scoping. Any queryset you add needs `school=` / `school_id=` or a reviewed
  `# tenant-isolation-allow: <reason>` marker, and the reason must be a real
  hyphenated reason — `scan_tenant_isolation_marker_quality.py` fails lazy ones.
- **`test_batch947_platform_runtime_no_singleton_bypass` locks this app** against
  `SiteSettings.get_solo` / `.load` / `SiteSettings.objects` regressions. ORM
  access to the slim `siteconfig` row is centralized in
  `helpers.get_platform_site_settings_record`; re-export via
  `site_settings_read_access` rather than reaching for the model.

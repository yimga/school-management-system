# Migration Cloud — Partner Event Catalog

Migration Cloud publishes bundle-lifecycle events to every **active webhook
subscription** of a bundle's tenant. Events are emitted at the **service layer**
(`apps/migration_cloud/services/lifecycle_events.py`), so a migration driven from
the connector/customer UI fires the same events an API-driven migration does —
this closed audit gap **G-5** (previously only the REST advance/apply actions
emitted, so UI-driven migrations produced zero webhooks and `bundle.reconciled`
was never emitted at all).

Register a subscription self-serve at **`…/configure/migration/webhooks/`**
(tenant admin — audit G-4) or have an operator register one. Each delivery is
HMAC-signed; verify it with the `runmycampus-webhook-verifier` SDK
(`packages/`), keyed on the signing secret shown once at subscription creation.

## Events

| Event type | Emitted when | Producer (service layer) | Key payload fields |
|---|---|---|---|
| `bundle.advanced` | A bundle reaches **MAPPED** (profile → classify → map complete) | `pipeline.advance_bundle` | `bundle_id`, `status` |
| `bundle.applied` | Rows land in the tenant (apply succeeds) | `orchestrator.apply_bundle` | `bundle_id`, `created`, `updated`, `quarantined`, `status` |
| `bundle.failed` | Apply fails/aborts (e.g. financial-guardrail mismatch, a FAILED artifact) | `orchestrator.apply_bundle` | `bundle_id`, `reason`, `error` / `status` |
| `bundle.reconciled` | Reconciliation passes and the bundle is sealed (source blobs dropped) | `reconciliation.reconcile_bundle` | `bundle_id`, `overall_parity_pct` |
| `bundle.rolled_back` | An applied bundle's rows are reverted *(reserved — emitted by the rollback path as it lands)* | rollback handlers | `bundle_id` |
| `shadow.tripped` | A shadow-window drift tick crosses the parity threshold *(reserved)* | `shadow.refresh_shadow` | `bundle_id`, `drift_pct` |

The canonical type strings live in one place —
`apps/migration_cloud/services/lifecycle_events.py` (`EVENT_*` constants +
`LIFECYCLE_EVENT_TYPES`) — so producers and this catalog cannot drift.

## Subscription matching

A subscription's `event_types` list is matched by the dispatcher
(`api/webhook_dispatch.py::_event_class_matches`): an exact type, a
`<head>.*` glob (e.g. `bundle.*`), or an empty list (receive all migration
events). Deliveries retry on a fixed backoff schedule and park in a DLQ on
exhaustion; a delivery-time SSRF re-check and a 24h idempotency guard apply.

> Emission is **best-effort** and never blocks the primary apply / reconcile /
> rollback. A webhook-subsystem failure is logged, not raised.

# EdOS Event-Driven Workflow Fabric

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_EVENT_FABRIC_READY`

## Scope

Defines the canonical domain event catalogue, outbox pattern, idempotent handler contract, retry/dead-letter posture, audit timeline, workflow recipes, non-blocking UI actions, preview/simulation gate, tenant-safe rule execution, offline event queue, PWA sync event queue, compute quota enforcement, telemetry heartbeat events.

## Sections

### Canonical domain events (27 entries)

- student.enrolled — payload {tenant_id, student_id, enrollment_id, school_id}
- attendance.marked_absent — payload {tenant_id, student_id, date, period, marked_by_actor_id}
- attendance.hash_proof_created — payload {tenant_id, attendance_batch_id, root_key_signature}
- invoice.paid — payload {tenant_id, invoice_id, amount_minor_units, currency, rail, settlement_status}
- payment.failed — payload {tenant_id, invoice_id, rail, error_code, retry_count}
- payment.voucher_generated — payload {tenant_id, voucher_id, network, expiry_at}
- payment.mobile_money_split_requested — payload {tenant_id, parent_wallet_id, child_wallets[]}
- communication.sent — payload {tenant_id, channel, recipient_role, delivery_id}
- communication.held_for_right_to_disconnect — payload {tenant_id, recipient_id, release_at}
- report_card.ready — payload {tenant_id, student_id, term, signature}
- migration.quarantined — payload {tenant_id, batch_id, error_rows_count}
- template.applied — payload {tenant_id, template_key, version, override_payload_hash}
- workflow.rule_triggered — payload {tenant_id, rule_id, workflow_id, idempotency_key}
- school.launch_blocked — payload {tenant_id, school_id, blocker_codes[]}
- incident.logged — payload {tenant_id, incident_type, severity, redacted_summary}
- bus.arrival_delayed — payload {tenant_id, route_id, eta_delta_seconds}
- dropoff.parent_arrived — payload {tenant_id, parent_id, geofence_class, opt_in_proof}
- substitute.handover_created — payload {tenant_id, original_teacher_id, sub_id, class_ids[], expiry_at}
- asset.qr_scanned — payload {tenant_id, asset_id, scanner_role, location_note}
- lost_item.found — payload {tenant_id, item_id, finder_actor_id, parent_notified_at}
- homework.support_requested — payload {tenant_id, student_id, subject, configured_hint_id_or_null}
- reimbursement.submitted — payload {tenant_id, staff_id, amount_minor_units, currency, budget_code}
- edge.heartbeat_received — payload {tenant_id, edge_node_id, manifest_hash, last_sync_at}
- sync.conflict_detected — payload {tenant_id, queue_id, conflict_strategy}
- donor.impact_metric_published — payload {tenant_id, donor_program_id, metric_key, redacted_value}
- pwa.offline_queue_flushed — payload {tenant_id, queue_id, flushed_count, conflicts_count}
- ai.gateway_invoked — payload {tenant_id, gateway_key, tokens_in, tokens_out, redaction_count} (apicenter ai_helpers only)

### Handler contracts (non-negotiable)

- All handlers MUST be idempotent — keyed by (tenant_id, event_id) or (tenant_id, idempotency_key).
- All handlers MUST accept TenantContext + ActorContext (if applicable) explicitly; no implicit thread-local reads.
- All handlers MUST validate event payload schema BEFORE side-effecting.
- All handlers MUST emit derived events to the outbox in the SAME transaction as the originating side effect.
- All handlers MUST respect ResourceQuotaContext — quota exhaustion routes to hold queue, not silent drop.
- All handlers MUST NOT execute tenant-provided code — only operator-curated workflow rules from apps.automation registry.
- Failed handlers retry with exponential backoff capped at the workflow's retry_budget_remaining, then route to dead-letter.

### Offline + PWA event queue posture

- PWA offline queue (IndexedDB) accumulates events tagged with TenantContext + idempotency_key + clientside_at.
- On reconnect, queue flushes through apps.sync_engine offline_queue endpoint; server re-validates auth + tenant binding + replay-window.
- Conflicts resolved by OfflineSyncContext.conflict_resolution_strategy (server-wins default).
- PWA queue depth ≥ telemetry threshold emits pwa.offline_queue_flushed event with backpressure signal.

## Repo evidence (anchor paths)

- `apps/events/`
- `apps/orchestration/`
- `apps/automation/`
- `apps/policies_rules/`
- `apps/communication/`
- `apps/finance/`
- `apps/schoolops/`
- `apps/student360/`
- `apps/customersuccess/`
- `apps/observability/`
- `apps/sync_engine/offline_queue.py`
- `services/ai_helpers.py`
- `apps/migration_cloud/`

## Tests

- `apps/events/tests/test_edos_canonical_event_catalogue.py`
- `apps/orchestration/tests/test_edos_idempotent_handler_contract.py`
- `apps/sync_engine/tests/test_edos_offline_event_queue_contract.py`

## External blockers (deferred — repo cannot fix)

- live PSP settlement reconciliation per corridor
- SOC2 Type II PDF
- MoE / Ministry of Education per-country live integrations
- WhatsApp Business platform Meta verification
- USSD telecom partner agreements per country
- native push notification wrapper (Capacitor/Tauri) — deferred until first-100-schools proof
- live LiteLLM API keys on Render
- Render SHA parity live verification
- multi-corridor pilot ingestion
- Postgres RLS enforced in production (current local env is SQLite)

## PWA-first posture

PWA is the launch mobile strategy. Native iOS/Android apps are explicitly DEFERRED until web core stability + first-100-schools proof + PWA installability proof. Service worker + manifest + IndexedDB + offline queue shipped in prior batches; this re-architecture preserves and consumes that infrastructure rather than forking.

## Honesty notes

- Repo-scope contracts only — no live vendor integration claims.
- Existing canonical models preserved; metadata layer absorbs tenant variance per architecture correction.
- External blockers listed above remain unchanged by batch 1489.

# EdOS Edge Telemetry and Compliance Heartbeat Kernel

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_EDGE_TELEMETRY_KERNEL_READY`

## Scope

Re-architects observability + compliance + lifecycle + sync_engine + platform_runtime around encrypted telemetry packets, local offline telemetry buffer, sync error packet, compliance heartbeat, corruption warning, payment sync failure, bandwidth-aware upload priority, central cloud ingestion, operator alerting, no PII by default, edge node status dashboard, rural/low-connectivity proof model, PWA sync health, edge manifest health, School-in-a-Box heartbeat contract.

## Sections

### Telemetry packet contracts

- Encrypted at rest in apps.sync_engine.offline_telemetry_buffer (PWA IndexedDB)
- TenantContext.tenant_id + manifest_hash + edge_node_id_or_null + packet_type
- PII fields EXCLUDED by default; only redacted-class summaries (counts, hashes)
- HMAC-SHA512 signature + replay-window timestamp
- Bandwidth-aware priority — heartbeat > sync_error > corruption > payment_sync_failure > performance_sample

### Packet types

- edge_heartbeat — every 60s when online; queued offline
- sync_error — schema_drift, conflict_unresolvable, manifest_signature_mismatch
- compliance_heartbeat — RLS_policy_version + consent_count + erasure_request_queue_depth
- corruption_warning — checksum_mismatch + affected_table
- payment_sync_failure — rail_id + error_code + retry_count (NO amounts, NO account numbers)
- pwa_health — sw_version + install_state + indexeddb_quota_pct + queue_depth
- edge_manifest_health — manifest_hash + last_apply_at + apply_status

### Honest deferred posture

- Live edge node ingestion DEFERRED — contracts shipped, central ingestion endpoint live, edge node deployments external.
- School-in-a-Box hardware DEFERRED — heartbeat contract shipped, physical hardware pilots external.

## Repo evidence (anchor paths)

- `apps/observability/`
- `apps/compliance/`
- `apps/lifecycle/`
- `apps/sync_engine/`
- `apps/platform_runtime/`

## Tests

- `apps/observability/tests/test_edos_telemetry_packet_redaction_v2.py`
- `apps/sync_engine/tests/test_edos_offline_telemetry_buffer_v2.py`
- `apps/compliance/tests/test_edos_compliance_heartbeat_v2.py`

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

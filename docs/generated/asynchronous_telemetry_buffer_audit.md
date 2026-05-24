# Async Telemetry Buffer + Distributed Audit (Phase 8)

**Batch:** 1488 · **Verdict:** ASYNCHRONOUS_TELEMETRY_BUFFER_REPO_SCOPE_PASS

## Floor at Open (Batches 1399/1400 v3.39.0)
- [apps/observability/metrics.py](../../apps/observability/metrics.py) — 4 backends (`noop` / `structured-log` / `prometheus-client` / `statsd`)
- `_sanitize_labels` drops sensitive VALUES (`password`/`secret`/`token`/`signature_text`/`private_key`/`email`/`slug`); normalizes keys; truncates values to 64 chars
- `/metrics/` Prometheus view (anonymous-readable, firewall-protected)
- [apps/migration_cloud/metrics.py](../../apps/migration_cloud/metrics.py) — tenant slug ALWAYS hashed (sha256[:12]) before emission
- [apps/migration_cloud/models_audit.py](../../apps/migration_cloud/models_audit.py) — `MigrationCloudAuditEvent` append-only with HMAC-SHA512 `root_key_signature` + per-tenant `integrity_hash`/`prev_event_hash` chain
- [apps/observability/tracing.py](../../apps/observability/tracing.py) — Sentry boundary (apps MUST use this, NOT `sentry_sdk` directly); enforced by `scan_sentry_boundary.py` baseline 0
- [scripts/verify_sentry_alert_rule_drift.py](../../scripts/verify_sentry_alert_rule_drift.py) — drift detector

## Telemetry Packet Contracts
| Packet | Status |
|---|---|
| Local encrypted packet | contract |
| Edge heartbeat | contract |
| Sync error | contract |
| Data corruption | contract |
| Local payment sync failure | contract |
| Compliance heartbeat | contract |
| Low-bandwidth priority queue | shipped |
| Replay-safe upload | contract (idempotency key) |
| Central ingestion | `/metrics/` + `/super/migration/health/` |
| PII redaction | enforced via `_sanitize_labels` |
| Packet signing/checksum | contract |
| Operator alert routing | shipped (Sentry SOT) |

## Tests Added (Phase 18)
- `apps/observability/tests/test_telemetry_packet_redaction.py`
- `apps/observability/tests/test_edge_heartbeat_contract.py`
- `apps/sync_engine/tests/test_offline_telemetry_buffer.py`
- `apps/compliance/tests/test_compliance_heartbeat_ingestion.py`

## External Blockers (Honest)
- live edge node deployment (rural Pi-box hardware partner)
- Render production `/metrics/` endpoint behind firewall + Bearer auth (operator)
- Sentry operator snapshot file for drift detection (operator per [docs/OBSERVABILITY_METRICS.md](../OBSERVABILITY_METRICS.md))

**Verdict:** ASYNCHRONOUS_TELEMETRY_BUFFER_REPO_SCOPE_PASS

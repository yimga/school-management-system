# Runtime Test Depth Hardening (Batch 1506)

The audit found many tests assert artifact existence only. This batch adds runtime tests that exercise service logic.

## Before / after

| State | Count |
| --- | ---: |
| Pre-existing artifact-existence tests (preserved as contract pins) | many |
| New runtime tests added this batch | **109** |

## Modules covered (22)

Communication · Finance · Sync · Platform Runtime · Global Registries · Interop · Observability · Migration Cloud · Brand Experience · SiteConfig · Studio OS · Schoolops · API · Security

## What is now runtime-exercised (not just file-exists)

- Hash invariants (tenant_id is hashed before logging/audit emit)
- Idempotency rejection on diverging intent with same key
- Manual cash fallback rail behavior across currencies
- Webhook signature verify (HMAC-SHA256 + `compare_digest`)
- Capacity FIFO drop ordering in telemetry buffer
- Sensitive-key scrub in manifest + buffer payloads
- Time-boxed expiry on substitute handover packet
- Guardian threshold gate in permission-to-pay
- PII redaction in lost-belongings sighting notes
- Canonical-field validation rejecting unknown keys in transfer envelopes
- Auto-mapping credential rejection + human-review gate
- PWA manifest parses + display mode + icons
- Service worker registers install/activate/fetch handlers
- Service worker has no hardcoded secret assignments
- Template marketplace URL namespace resolves under tenant URLconf
- Operator-only templates 404 on tenant scope
- Studio OS navigation references experience/templates

## GraphQL safety contract pair

- `apps/api/tests/test_graphql_security_contract.py` (8 tests)
- `apps/security/tests/test_graphql_tenant_safety.py` (6 tests)
- 14 PASS

**Verdict:** RUNTIME TEST DEPTH HARDENED — REPO SCOPE.

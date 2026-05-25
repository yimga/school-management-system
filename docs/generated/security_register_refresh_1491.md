# Security Register Refresh (After Batch 1491)

Generated: 2026-05-24 (batch 1493)
Supersedes: security_exception_register generated 2026-05-19

## Surface totals (from security_surface_audit 2026-05-23)

| Pattern | Count |
| --- | ---: |
| AllowAny | 39 |
| csrf_exempt | 36 |
| subprocess | 407 |
| Needs review | 287 |
| Unsafe | 13 |
| Violation | 12 |

## Exception categories

### Signed webhook handlers (csrf_exempt × 12)
HMAC-SHA256 signature verification, constant-time compare, tenant resolution, idempotency window, replay guard, hashed-only logging. **Accepted.**

### Operator marketplace catalog (AllowAny × 3)
`apps/api/views_marketplace_catalog.py` — anonymous discovery of catalog metadata, IP-throttled, read-only. **Accepted.**

### Webhook catalog discovery (AllowAny × 2)
`apps/api/views_webhook_catalog.py` — lists event schema only; no tenant identifiers. **Accepted.**

### GraphQL gateway (`config/graphql_view.py`)
csrf_exempt + IP throttle + JSON-only + introspection disabled in production + audit logs op + authenticated only. **Accepted.** Phase 3 hardening artifact emitted this batch.

### Subprocess management scripts (380)
Verifier scripts + management commands invoked via argument arrays (no `shell=True`). **Accepted.** `scan_subprocess_shell_true.py` baseline 0.

### Subprocess runtime (27)
Liveness probes, verifier wrappers — argument arrays, captured streams, timeout-enforced. **Accepted.**

## Repo-side actions emitted with this refresh

- `csrf_exempt_targeted_review.{json,md}`
- `allowany_targeted_review.{json,md}`
- `subprocess_surface_review.{json,md}`

## External blockers (preserved as DEFERRED)

- FACTS / Skyward write paths — counsel docket
- MAA v2.0 promotion — counsel signoff PDF
- HSM bridge implementation for migration_cloud root-key signature

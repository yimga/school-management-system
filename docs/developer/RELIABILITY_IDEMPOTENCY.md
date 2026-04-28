# Reliability and Idempotency

Reliability helper primitives live in `apps/platform_runtime/reliability.py`.

## Guarantees
- Deterministic idempotency keys via `build_idempotency_key(...)`.
- Bounded retries via `should_retry_failure(...)` for transient failure classes only.
- Platform events support idempotency via `emit_platform_event(..., idempotency_key=...)`.

## Degraded-mode behavior
- Founder dashboard and observability surfaces degrade gracefully when generated JSON files are missing.
- Kill test and self-heal reports are treated as runtime evidence, not hard-coded constants.


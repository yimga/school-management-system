# Runtime Engine Module Mapping (Batch 1506)

The audit found 7 expected paths missing by name. Equivalents existed under other names; this batch adds the requested canonical paths as **runtime-real services**, not empty stubs.

| Expected path | Status | Tests |
| --- | --- | --- |
| `apps/communication/channel_adapter.py` | created | 4 PASS |
| `apps/finance/payment_rail_adapter.py` | created | 6 PASS |
| `apps/sync_engine/tenant_manifest_compiler.py` | created | 6 PASS |
| `apps/global_registries/schema_mapping.py` | created | 5 PASS |
| `apps/interop/transfer_envelope.py` | created | 6 PASS |
| `apps/observability/telemetry_buffer.py` | created | 5 PASS |
| `apps/migration_cloud/ai_auto_mapping.py` | created | 5 PASS |

37 runtime tests across the 7 modules — all PASS in <0.05s.

## AI gateway boundary

`apps/migration_cloud/ai_auto_mapping.py` ships a deterministic heuristic. The contract is structured so that a future AI scorer routes through `services.ai_helpers` per `scan_ai_gateway_boundary.py` baseline 0 — no direct `services.ai_gateway` import is permitted.

## Sensitive-key handling

All modules:
- Hash tenant IDs before logging or emitting audit rows
- Drop `password`, `secret`, `token`, `api_key`, `private_key`, `ssn`, `dob`, `email`, `raw_prompt`, `credential` keys from payloads
- Use `hmac.compare_digest` for any signature compare
- Use `Decimal` for money (finance modules)

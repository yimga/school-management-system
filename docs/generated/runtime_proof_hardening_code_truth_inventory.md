# Runtime Proof Hardening — Code Truth Inventory (Batch 1506)

Generated: 2026-05-24

## Branch / commit

- `main` @ `d2898a6f` (pre)
- 474 pending changes: 384 modified + 90 untracked (parallel-session work preserved untouched)

## Service worker

- Pre: `sms-v3.90.44-sidebar-disclosure-scroll-contract-2026-05-24`
- Post: `sms-v3.91.0-runtime-proof-hardening-2026-05-24` (monotonic bump)

## GEOS matrix — honest re-read required

| Field | Current | Honest reading |
| --- | --- | --- |
| `repo_pct` | 100 | Repo verifier checks pass — acceptable |
| `live_pct` | 100 | **Overclaim** — Lane 2 external blockers unproven |
| `composite_pct` | 100 | **Overclaim** — must downgrade pending live proof |

Hardening output: see `geos_scoring_semantics_hardening.{json,md}`.

## Security state (stale)

- `security_exception_register` generated 2026-05-19 — refresh required (batches 1485-1491 landed since)
- `security_surface_audit` 2026-05-23 reports: AllowAny 39 / csrf_exempt 36 / subprocess 407
- 287 needs_review / 13 unsafe / 12 violation findings — targeted reviews emitted this batch

## GraphQL

- View: `config/graphql_view.py`
- Posture: `@csrf_exempt` + IP throttle (60 GET/min, 120 POST/min) + JSON-only content-type + introspection-off-by-default in production
- Hardening contract artifact + test pair emitted this batch

## PWA

| Artifact | Bytes | Status |
| --- | --- | --- |
| `static/manifest.json` | 1,210 | present |
| `static/manifest-portal.json` | 1,033 | present |
| `static/js/service-worker.js` | 131,834 | present |
| `static/js/rmc-service-worker-registration.js` | 5,820 | present |

## Runtime engine modules (audit found "missing by name")

Equivalents existed under other names; this batch adds the requested canonical paths as runtime-real services, not empty stubs:

| Expected path | Status this batch |
| --- | --- |
| `apps/communication/channel_adapter.py` | created — protocol + registry + selection + audit-callback |
| `apps/finance/payment_rail_adapter.py` | created — protocol + registry + idempotency + signature contract |
| `apps/sync_engine/tenant_manifest_compiler.py` | created — deterministic compile + PII scrub + signed posture |
| `apps/global_registries/schema_mapping.py` | created — 20-field canonical registry + heuristic mapper |
| `apps/interop/transfer_envelope.py` | created — student/teacher envelopes + canonical-field validation |
| `apps/observability/telemetry_buffer.py` | created — offline buffer + capacity FIFO + signed flush |
| `apps/migration_cloud/ai_auto_mapping.py` | created — confidence-scored proposals + credential rejection + human review gate |

Full mapping: `runtime_engine_module_mapping.{json,md}`.

## Micro-friction workflows (audit-prioritized top 3)

| Workflow | Module | Notes |
| --- | --- | --- |
| Substitute handover blueprint | `apps/schoolops/substitute_handover.py` | time-boxed, medical/IEP gated by default |
| Permission-to-pay | `apps/finance/permission_to_pay.py` | guardian threshold + routes through payment_rail_adapter |
| Lost belongings QR loop | `apps/schoolops/lost_belongings_qr.py` | anonymous custody loop, PII-redacted notes |

## Tests

- 52 runtime tests added across 12 test modules
- All 52 pass in 0.047s
- `python manage.py check --settings=config.settings` clean

## Zero native mobile claims introduced

PWA-first stance preserved. Capacitor/Tauri/WebView wrappers remain DEFERRED.

## External blockers (preserved as DEFERRED — not faked)

- PSP live settlement reconciliation
- SOC2 PDF + counsel signoff
- Render SHA parity live verification
- Multi-corridor pilot ingestion
- Live LiteLLM key provisioning
- Postgres RLS production deployment
- WhatsApp Meta provider

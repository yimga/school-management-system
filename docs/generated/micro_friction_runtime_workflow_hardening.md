# Micro-Friction Workflow Runtime Hardening (Batch 1506)

Top 3 audit-prioritized workflows are runtime-real (not contract-only).

| Workflow | Module | Tests |
| --- | --- | --- |
| Substitute handover blueprint | `apps/schoolops/substitute_handover.py` | 6 PASS |
| Permission-to-pay | `apps/finance/permission_to_pay.py` | 4 PASS |
| Lost belongings QR loop | `apps/schoolops/lost_belongings_qr.py` | 5 PASS |

**15 tests, all PASS.**

## Substitute handover

- `build_packet(trigger, substitute_id, lesson_outline, seating_chart_ref, expose_medical_iep, grace_minutes)`
- All identities hashed before persistence
- Medical/IEP gated by default; explicit `expose_medical_iep=True` required to unblock
- `access_check(packet)` enforces time-boxed window with grace minutes

## Permission-to-pay

- `open_request → record_guardian_approval → authorize_payment` state machine
- Guardian gate triggers at tenant-configurable threshold
- Routes through `apps.finance.payment_rail_adapter` with `request_id` as idempotency key
- Manual fallback rail always available

## Lost belongings QR

- `mint_tag` produces tenant-scoped short code + sanitized label hint (rejects email-like data)
- `record_finder_sighting` is anonymous; notes are redacted on sensitive-token detection
- `record_staff_recovery` records hashed staff id

## Honest residuals

- Real WhatsApp / SMS notification awaits live channel credentials
- QR code printing is operator-side (svg generation pending)
- Live PSP payment authorization awaits live credentials

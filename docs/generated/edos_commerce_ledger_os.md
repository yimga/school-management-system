# EdOS Hyperlocal Commerce and Ledger OS

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_COMMERCE_LEDGER_OS_READY`

## Scope

Refactors finance + billing + payroll + marketplace into a commerce operating layer. PaymentRailAdapter interface + APM router + split ledger rules + local tax/e-invoice contracts + wallet/student spending limits + marketplace transaction model + manual cash/mobile-money fallback + offline payment intent + idempotency/replay safety + settlement reconciliation + usage/subscription entitlement linkage + LATAM fiscal router + voucher/barcode cash network + mobile-money split wallet + USSD payment + field-trip permission-to-pay + reimbursement ledger + cafeteria/POS wallet flow. NO fake PSP readiness.

## Sections

### PaymentRailAdapter contract

- interface — initiate(invoice, rail, idempotency_key) + verify_webhook(signed_payload) + reconcile(settlement_batch_id)
- 13 PSP rail registry entries — Pix/CoDi/Transbank/Boleto/OXXO/UPI/M-Pesa/MoMo/Orange Money/QRIS/PromptPay/USSD/cash
- Idempotency key required on every initiate
- Replay-window check on every webhook verification (300s window default)
- Signature verification REQUIRED for every webhook
- NO source credentials in logs / prompts / inventory

### Lifecycle events emitted

- invoice.paid + payment.failed + payment.voucher_generated + payment.mobile_money_split_requested
- Reconciliation events from settlement_batch ingestion

### Honest deferred posture

- Live PSP settlement reconciliation DEFERRED — adapter contracts shipped, live KYC + sandbox-to-prod flip external.
- Live multi-corridor pilots DEFERRED — corridor registry shipped, pilot ingestion external.
- Live USSD/IVR adapters DEFERRED — adapter contracts shipped, telecom partner agreements external.

## Repo evidence (anchor paths)

- `apps/finance/`
- `apps/billing/`
- `apps/payroll/`
- `apps/marketplace/`
- `apps/finance/regional_payment_profiles.py`

## Tests

- `apps/finance/tests/test_edos_payment_rail_adapter_v2.py`
- `apps/finance/tests/test_edos_split_ledger_routing_v2.py`
- `apps/payroll/tests/test_edos_reimbursement_ledger_v2.py`

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

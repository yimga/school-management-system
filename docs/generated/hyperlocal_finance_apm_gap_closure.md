# Hyper-Local Finance / APM Gap Closure (Phase 4)

**Batch:** 1488 · **Verdict:** HYPERLOCAL_FINANCE_APM_REPO_SCOPE_PASS

## Floor at Open
SFDP Phase 3 (batches 1452–1475 / 2026-05-23) closed 250 ISO2 payment profiles with rail taxonomy, risk tiers, local checkout rail cards, dispute helpers, demo schools seed. This phase audits + extends rather than rebuilds.

## Architecture Status

| Requirement | Status | Evidence |
|---|---|---|
| PaymentRailAdapter interface | shipped | [payment_rail_adapter.py](../../apps/finance/payment_rail_adapter.py) + [regional_payment_profiles.json](../../apps/finance/regional_payment_profiles.json) (250 ISO2) |
| APM router | shipped | [payment_corridor_contracts.py](../../apps/finance/payment_corridor_contracts.py) + [payment_gateway_health.py](../../apps/finance/payment_gateway_health.py) |
| Pix/CoDi/Transbank/Boleto/OXXO | documented | regional profiles |
| UPI / M-Pesa / MoMo / Orange / QRIS / GrabPay / PromptPay | documented | regional profiles |
| USSD payment | Africa regional adapter (Phase 15) | Wave 12+ memory |
| Split-ledger | shipped (counsel-gated) | [payment_marketplace_split.py](../../apps/finance/payment_marketplace_split.py) + `SFDP_PAYMENT_SPLIT_COUNSEL_TOKEN` |
| E-invoice / factura electrónica / Nota Fiscal | contract | LATAM profiles + e-invoice adapter |
| PSP webhook signature verification | shipped | [webhooks/normalizer.py](../../apps/finance/webhooks/normalizer.py) — Stripe/Paystack/Flutterwave/Razorpay via `hmac.compare_digest` |
| Idempotency + replay | shipped | canonical event_id dedupe (batch 1430) + per-provider timestamp window |
| Offline payment queue | shipped | OfflinePaymentIntent + bulk approve/CSV export (batch 1445) |
| Permission-to-pay | shipped | ParentApproval + Invoice gating |
| Student wallet spending limits | shipped | MealPlanBalance.is_low + schoolops wallet |
| Cash / manual fallback | shipped | [views_payments.py](../../apps/finance/views_payments.py) cash desk + ledger |

## Tests Added (Phase 18)
- `apps/finance/tests/test_payment_rail_adapter_contracts.py`
- `apps/finance/tests/test_apm_router.py`
- `apps/finance/tests/test_split_ledger_routing.py`
- `apps/finance/tests/test_mobile_money_split_wallet_contract.py`
- `apps/finance/tests/test_webhook_signature_idempotency.py`
- `apps/finance/tests/test_einvoice_tax_contracts.py`
- `apps/finance/tests/test_offline_payment_reconciliation.py`
- `apps/finance/tests/test_permission_to_pay_workflow.py`
- `apps/billing/tests/test_barcode_voucher_contract.py`
- `apps/schoolops/tests/test_student_wallet_spending_limits.py`

## External Blockers (Honest)
- live Stripe Connect live keys + Lane 2 evidence
- live Paystack / Flutterwave / MTN MoMo keys + KYC
- Razorpay / Pesapal / Mercado Pago / dLocal Lane 2 KYC
- Counsel signoff for split-ledger payouts
- Per-jurisdiction tax + revenue-recognition opinion (Wave E counsel-pending)
- Stripe settlement reconciliation evidence
- PSP webhook live signature verification on production traffic

## Compliance
- ✓ `scan_money_float` baseline 0; Decimal end-to-end
- ✓ no live PSP claims without evidence
- ✓ no certs/secrets logged
- ✓ `scan_pii_logging_smell` baseline 0

**Verdict:** HYPERLOCAL_FINANCE_APM_REPO_SCOPE_PASS

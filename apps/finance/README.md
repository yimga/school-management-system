# apps/finance

> Invoicing, payments, the regional payment-rail orchestration layer, and the
> fractional (partial-payment) sub-ledger that decides enrollment clearance.

**Tenancy:** TENANT (own Postgres schema under django-tenants)
**Scale:** 57 models · 79 migrations · 101 test modules · ~49k LOC

## What this app owns

Finance owns every path money takes through a school: a `FeePlan` becomes an
`Invoice`, an `Invoice` is settled by one or more `Payment` rows, and the
remaining balance drives dunning, clearance, and report-card visibility. Around
that spine sit the things a real school actually needs — offline cash capture
when the power is out, mobile-money and bank rails selected per ISO region,
suspense money that arrived without a name on it, split billing across two
guardians, scholarships and aid funds, and a double-entry journal.

Two design decisions dominate this app. First, **money is `Decimal`, never
`float`** — every amount column is `DecimalField(max_digits=12,
decimal_places=2)` and `json_decimal.py` exists because `json.dumps` silently
routes a `Decimal` through IEEE 754 and drifts ledger totals across a half-cent
boundary. Second, **balance is computed, not stored**: `Invoice.computed_balance`
derives from `total_amount - sum(payments)`, and the `balance_amount` column is
a deprecated denormalization that `reconcile_balance()` re-syncs for legacy
readers. Trust the property, not the column.

The app is designed for unreliable connectivity, not just for the happy path.
`OfflinePaymentIntent` lets a bursar bank a cash receipt with no network; the
intent is only real money once `payment_orchestration.reconcile_offline_payment_intent`
approves it, and that single function is the chokepoint where a queued intent
becomes a `Payment`, refreshes the invoice, and posts the fractional clearance
line — all in one atomic block.

## Key models

Finance declares 57 models. These are the ones that carry the core money flow —
the list is deliberately not exhaustive.

| Model | Table | Purpose |
| --- | --- | --- |
| `Invoice` | `finance_invoice` | The billing spine. `school` is **nullable** (platform/AP invoices carry no tenant). |
| `InvoiceLine` | `finance_invoiceline` | Line items summed into the invoice total. |
| `Payment` | `finance_payment` | A receipt against an invoice. Financially immutable once in a final state. |
| `FeePlan` | `finance_feeplan` | Per-year fee structure invoices are generated from. |
| `FeeItem` | `finance_feeitem` | An individual chargeable fee within a plan. |
| `FeeInstallment` | `finance_feeinstallment` | Scheduled instalment breakdown of a fee. |
| `FractionalPaymentLedger` | `finance_fractionalpaymentledger` | Append-only partial-payment lines; drives enrollment clearance. Idempotent on `(school, idempotency_key)`. |
| `OfflinePaymentIntent` | `finance_offlinepaymentintent` | Offline-queued payment awaiting bursar reconciliation. |
| `SuspensePayment` | `finance_suspensepayment` | Unidentified money awaiting manual claim/allocation. |
| `SuspensePaymentAllocation` | `finance_suspensepaymentallocation` | Splits one suspense payment across invoices. |
| `InvoicePayerShare` | `finance_invoicepayershare` | Split-billing obligation per guardian on one invoice. |
| `InvoicePayerSharePaymentAllocation` | `finance_invoicepayersharepaymentallocation` | Allocation rows that make payer-share application idempotent. |
| `ParentWallet` | `finance_parentwallet` | Per-guardian wallet balance for "Pay with wallet". |
| `WalletTransaction` | `finance_wallettransaction` | Audit trail for every wallet balance change. |
| `PaymentRail` | `finance_paymentrail` | A named regional rail (mobile money, bank, cash, …). |
| `RegionPaymentProfile` | `finance_regionpaymentprofile` | Per-ISO-region primary + backup rail pair. |
| `TenantPaymentPolicy` | `finance_tenantpaymentpolicy` | School-level rail selection and checkout UX policy. |
| `ComplianceProfile` | `finance_complianceprofile` | Finance/payroll compliance and regional settings, incl. `currency_code`. |
| `WebhookLog` | `finance_webhooklog` | Audit trail for payment webhook processing. |
| `RefundRequest` | `finance_refundrequest` | Refund workflow — corrections are new entries, never in-place edits. |
| `AwardSource` | `finance_awardsource` | Scholarship/grant fund bucket, tenant-scoped. |
| `Scholarship` | `finance_scholarship` | Scholarship definition; `eligibility_criteria` is JSON-Logic. |
| `JournalEntry` | `finance_journalentry` | Double-entry accounting entry header. |
| `JournalLine` | `finance_journalline` | Debit/credit lines belonging to a journal entry. |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `payment_orchestration` | `reconcile_offline_payment_intent` — the offline-intent → Payment chokepoint |
| Module | `fractional_ledger_services` | `post_partial_payment`, `enrollment_clearance_for_invoice`, `student_enrollment_blocked_for_unpaid` |
| Module | `json_decimal` | `quantize_money`, `amount_str`, `DecimalJSONEncoder` — use on every money path |
| Module | `security` | `WebhookSecurityValidator` (IP allowlist, rate limit, signature), `PaymentValidator` |
| Module | `subscription_gate` | HTTP 402 on finance writes when platform billing is inactive |
| Module | `schema_repair` | Idempotent tenant-schema drift heals; no-op on a healthy schema |
| URL | `offline_payment_intent_queue` / `_approve` / `_bulk_approve` | Bursar offline queue |
| URL | `payment_webhook` | PSP callback ingress |
| URL | `invoices`, `invoice_detail`, `invoice_receipt`, `payments`, `payment_receipts` | Core billing surfaces |
| URL | `claim_suspense_payment`, `cash_office_closure`, `scan_teller` | Cash-desk operations |
| URL | `payment_readiness_dashboard`, `global_payment_command_center` | Rail readiness / ops |
| Celery | `auto_generate_fee_invoices_task`, `update_invoice_statuses_task` | Invoice lifecycle |
| Celery | `send_payment_reminders_task`, `retry_failed_payment_reminders_task` | Dunning |
| Celery | `apply_split_late_fees_task`, `auto_copy_fee_plans_task` | Fee automation |
| Celery | `process_payment_receipt_upload_task`, `retry_bank_verification_task` | Proof / bank verification |
| Command | `seed_finance_defaults`, `check_payment_gateways`, `integration_preflight` | Setup + readiness |
| Command | `import_bank_statement`, `verify_bank_deposits`, `claim_suspense_payment` | Reconciliation ops |

## Before you change this

- **Never let money touch `float`.** Use `json_decimal.quantize_money` at write
  boundaries and `DecimalJSONEncoder` at serialization boundaries.
  `scripts/scan_money_float.py` enforces this; a legitimate `float()` (ratios,
  percentages, gateway int-cents) must carry a `# money-float-allow: <reason>`
  marker on the same line. This is not style — the drift only shows up when a
  sum crosses a half-cent, and then reconciliation fails.
- **`reconcile_offline_payment_intent` is the fractional ledger's only
  production producer.** `post_partial_payment` used to exist with no caller
  while the consumer was live, so the sub-ledger stayed permanently empty,
  `enrollment_clearance_for_invoice()` could never return True, and
  `reports.student_has_financial_clearance()` blocked every partial payer's
  report card forever. If you add a new cash-receipt path, it must post to the
  ledger too, or you re-open that bug.
- **The ledger write lives inside the reconcile atomic block on purpose.** The
  cash receipt and its clearance line are one financial event and must commit
  together — do not "helpfully" wrap it in a try/except. A swallowed ledger
  write is a silent money-integrity bug.
- **`Invoice.school` is nullable but `FractionalPaymentLedger.school` is NOT
  NULL.** The producer guards on `inv.school_id is not None`. That is correct,
  not an oversight: both clearance readers are school-scoped, so a school-less
  row would be unwritable *and* unreadable. Tenant enrollment clearance does not
  apply to platform/AP invoices.
- **`Invoice` has no `currency_code` field** — only the optional `currency` FK to
  the canonical registry. A `getattr(invoice, "currency_code", None)` read always
  falls through and stamps rows "USD", which is wrong for every non-USD tenant.
  Use `_resolve_currency_code` (currency FK → `ComplianceProfile.currency_code` →
  USD), the same fallback order as `Invoice.save()`.
- **Payments are immutable once final.** `_FINAL_PAYMENT_STATUSES` (`completed`,
  `failed`, `cancelled`, `refunded`) freeze a payment's financial identity —
  amount, invoice, method. Corrections are *separate* entries (soft-delete
  reversal, `RefundRequest`), never in-place rewrites. Status-only transitions
  stay allowed.
- **`_NON_RECEIVED_PAYMENT_STATUSES` deliberately excludes `pending`.** Only
  `failed`/`cancelled`/`refunded` are kept out of the paid total. Tightening this
  to require `completed` would change balance semantics for the many flows that
  create-then-process, and needs full ledger coverage first.
- **Read `computed_balance`, not `balance_amount`.** The column is a deprecated
  denormalization kept for backwards compatibility; `reconcile_balance()` syncs
  it after payment changes.
- **Idempotency is a contract, not a nicety.** `post_partial_payment` short-
  circuits on `(school, idempotency_key)` (DB-enforced by a partial unique
  constraint), and the offline producer keys on `offline-intent-<pk>` so a retry
  or webhook redelivery cannot double-post. Keep new money producers keyed.
- `webhook_security.py` is a **compatibility shim only**. Real webhook security
  is `security.WebhookSecurityValidator`, used by
  `views_payments.py::payment_provider_webhook`. `webhook_security_required` was
  retired in 2026-06 (it was dead and referenced a model that never existed).

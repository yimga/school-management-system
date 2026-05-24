# Finance subscription gate matrix (SFDP batch 1421)

Engine 1 platform billing (`BillingAccount` / `TenantSubscription`) gates **tenant tuition writes** (Engine 2) when the school is not in good standing.

## Allowed billing account statuses (finance writes)

| Status | Finance POST/PUT/PATCH/DELETE |
| --- | --- |
| `ACTIVE` | Allowed |
| `TRIAL` | Allowed |
| `PAST_DUE` | **402 Payment Required** |
| `SUSPENDED` | **402** |
| `CANCELED` | **402** |

Missing `BillingAccount` on a tenant host degrades to **allow** (dev / pre-billing environments).

## Paths always exempt (no 402)

| Pattern | Reason |
| --- | --- |
| `/finance/payments/webhook/` | Provider callbacks; signature-verified |
| `GET` / `HEAD` / `OPTIONS` | Read-only |
| Manager / super control-plane hosts | Platform operators |

## Cash / offline proof exception (batch 1426)

When `TenantPaymentPolicy.allow_manual_offline_proof` is true, these mutating paths remain allowed even if billing is inactive:

- `/finance/invoices/<id>/upload-receipt/`
- `/portal/api/offline/enqueue/` with `payment_proof` / `payment_receipt` action types

Rationale: guardians can queue proof while the school resolves platform billing; bursar reconciliation still requires staff RBAC.

## Implementation

- `apps/finance/subscription_gate.py` — `FinanceSubscriptionGateMiddleware`
- Tests: `apps/finance/tests/test_finance_subscription_gate.py`

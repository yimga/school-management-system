# Invoice balance: reconcile_balance on all paths

**Status:** Implemented (Phase 1.4)  
**Plan:** [PLAN_ENROLLMENT_FEE_IMPROVEMENTS.md](./PLAN_ENROLLMENT_FEE_IMPROVEMENTS.md)

## Rule

- **`Invoice.computed_balance`** — Property: `total_amount - sum(payments)`. Use this for display and logic when you need the current balance.
- **`Invoice.balance_amount`** — Denormalized field. Kept in sync by calling **`invoice.reconcile_balance()`** after any change that affects payments or totals.
- **All payment-apply paths** call **`reconcile_balance()`**: `recalculate_invoice()` calls it at the end, so any path that goes through `recalculate_invoice()` or `apply_payment()` is covered.

## Where it is called

- **`services.recalculate_invoice(invoice)`** — After updating total_amount and balance_amount from lines and payments, calls `invoice.reconcile_balance()` so `balance_amount` matches `computed_balance`.
- **`apply_payment(payment)`** calls `recalculate_invoice(payment.invoice)`, so all payment creation paths that go through `apply_payment` (including signals) are covered.

## Migration path

Long term, code can be migrated to use **`invoice.computed_balance`** instead of `invoice.balance_amount` for reads; `balance_amount` can remain for backward compatibility and for queries that filter/aggregate on it, as long as `reconcile_balance()` is called on every path that modifies payments or totals.

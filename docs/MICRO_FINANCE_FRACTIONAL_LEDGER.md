# Micro-finance fractional ledger — partial-payment clearance loop (SOT)

This is the reference for the **fractional / partial-payment sub-ledger**: the
micro-finance loop that lets a school accept irregular cash / mobile-money
instalments against an invoice and, once cumulative payment crosses a tenant-set
threshold, **clear the student to enroll and see results** — even before the
regular Payment ledger has been reconciled.

> **TL;DR** — `post_partial_payment(...)` appends a Decimal-precision line to
> `FractionalPaymentLedger`. When cumulative paid ≥ the tenant's
> `enrollment_clearance_percent` of the invoice total, that invoice stops
> blocking. Enrollment- and results-gating consult BOTH the regular invoice
> balance AND this sub-ledger, and the sub-ledger gets the last word. Posting is
> idempotent on `(school, idempotency_key)`.

---

## 1. The model

[`apps/finance/models_fractional_ledger.py`](../apps/finance/models_fractional_ledger.py)
— `FractionalPaymentLedger` (`:11`), append-only partial-payment lines, all money
as `DecimalField` (never float). Key fields:

| Field | Notes |
|-------|-------|
| `school`, `invoice`, `student` FKs | tenant-scoped; `student` is `SET_NULL`-nullable (`:31`) |
| `amount` | the partial post, `Decimal(12,2)` (`:38`) |
| `currency_code` | 3-char, defaults `USD` (`:39`) |
| `running_paid_total` | cumulative paid on the invoice after this row (`:40`) |
| `invoice_balance_after` | remaining invoice balance after this row (`:45`) |
| `source` | `Source` TextChoices: `cash_counter` / `gateway` / `wallet` / `adjustment` (`:14`) |
| `idempotency_key` | indexed; `""` means "no key" (`:51`) |
| `enrollment_clearance_met` | snapshot bool: true when this row's cumulative total met the threshold (`:52`) |

Idempotency is enforced at the DB level by a partial unique constraint:
`UniqueConstraint(fields=["school","idempotency_key"], condition=~Q(idempotency_key=""))`
(`models_fractional_ledger.py:65`) — so two rows can both have an empty key, but a
non-empty key is unique per school.

## 2. The services

[`apps/finance/fractional_ledger_services.py`](../apps/finance/fractional_ledger_services.py)

### `post_partial_payment(...)` (`:48`, `@transaction.atomic`)

Records one partial payment and returns the created (or pre-existing) ledger row.

- Rejects non-positive amounts (`ValueError`, `:59`).
- **Idempotent:** when `idempotency_key` is set, an existing row for
  `(school, idempotency_key)` is returned unchanged — no double-post
  (`:61`–`:66`).
- Computes invoice total (`_invoice_total`, `:14` — `total_amount`, else summed
  `lines`, else `amount`), adds the new amount to the prior ledger sum
  (`_ledger_paid_total`, `:40`), and stamps `running_paid_total`,
  `invoice_balance_after` (floored at 0), and `enrollment_clearance_met`.

### `enrollment_clearance_for_invoice(invoice, *, school)` (`:90`)

Returns whether the *cumulative* fractional posts on this invoice meet the
clearance threshold. This is the live read used by the gates below (the row's
`enrollment_clearance_met` is just a historical snapshot).

### `student_enrollment_blocked_for_unpaid(student, academic_year, *, school=None)` (`:97`)

The headline gate. A student is **blocked** when at least one non-VOID invoice
this year still has a positive **regular** balance (`Invoice.computed_balance`)
AND that same invoice has **not** met the fractional clearance threshold. An
invoice whose partial posts reached the threshold no longer blocks — even if the
regular Payment ledger is unreconciled. Tenant-scoped: `school` is resolved from
the student when not passed, and every query is constrained to it (`:115`–`:130`).

## 3. The clearance threshold (tenant config)

`_clearance_threshold(school, invoice_total)` (`fractional_ledger_services.py:26`)
reads `school.settings["finance"]["enrollment_clearance_percent"]` and returns
`invoice_total * pct / 100`. When the key is absent (or unparseable) it falls back
to **50%** (`:37`).

`School.settings` is a free-form JSON column, so configuration is a nested write
— not a declared model field. Example (from
`apps/finance/tests/test_fractional_ledger.py:203`):

```python
school.settings = {"finance": {"enrollment_clearance_percent": 80}}
school.save(update_fields=["settings"])
# now 600/1000 = 60% no longer clears; the student stays blocked.
```

## 4. Where it gates results visibility

[`apps/reports/services.py`](../apps/reports/services.py) —
`student_has_financial_clearance(student, academic_year)` (`:307`) gates term /
annual report-card download.

- If the school's `block_report_download_if_outstanding_balance` flag is off, it
  returns `True` immediately (`reports/services.py:318`).
- Otherwise it walks non-VOID invoices; an invoice with `computed_balance <= 0` is
  cleared, and an invoice that meets `enrollment_clearance_for_invoice(...)`
  (imported from the fractional services, `:321`) is also cleared. Any invoice that
  is neither blocks the report (`returns False`, `:343`).

So the same fractional-clearance decision drives both **enrollment** (via
`student_enrollment_blocked_for_unpaid`) and **results visibility** (via
`student_has_financial_clearance`).

## 5. The end-to-end loop

```
cash/mobile-money instalment
  → post_partial_payment(school, invoice, amount, idempotency_key=…)
      → FractionalPaymentLedger row (Decimal, idempotent)
  → cumulative paid ≥ enrollment_clearance_percent × invoice_total ?
      → enrollment_clearance_for_invoice(invoice) == True
          → student_enrollment_blocked_for_unpaid(...) == False   (can enroll)
          → student_has_financial_clearance(...)        == True   (can see results)
```

## 6. What is proven

[`apps/finance/tests/test_fractional_ledger.py`](../apps/finance/tests/test_fractional_ledger.py):

| Test | Proves |
|------|--------|
| `test_three_partial_posts_converge_and_idempotent` (`:52`) | three posts accumulate to the right running total; a repeated `idempotency_key` does not double-post |
| `test_clearance_helper_matches_ledger` (`:85`) | `enrollment_clearance_for_invoice` agrees with the cumulative ledger |
| `test_no_payment_blocks_enrollment_and_results` (`:152`) | zero payment ⇒ blocked |
| `test_partial_below_threshold_still_blocks` (`:163`) | under the threshold ⇒ still blocked |
| `test_partial_reaching_threshold_clears` (`:181`) | crossing the threshold ⇒ cleared |
| `test_custom_tenant_threshold_percent_respected` (`:201`) | a tenant raising `enrollment_clearance_percent` to 80 re-blocks a 60%-paid invoice |
| `test_gate_is_tenant_scoped` (`:218`) | a post booked under another tenant does NOT clear this school's invoice |

## 7. Honest scope / limitations

- This sub-ledger is **additive** to the regular Payment/Invoice model — it does
  not replace it. `computed_balance` still reflects the canonical Payment ledger;
  the fractional ledger only relaxes the *gate* once the tenant threshold is met.
- The threshold default is **50%** and lives in a JSON settings bucket
  (`school.settings["finance"]["enrollment_clearance_percent"]`), not a typed
  field — set it through whatever surface writes `School.settings`.
- `post_partial_payment` does not itself create a Payment row or reconcile the
  regular ledger; reconciliation of the cash against Payments is a separate
  finance task.

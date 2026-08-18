# Edge-sync finance hold (2026-08-17)

Full-parity **wave 4** was scoped as "finance (Invoice / Payment / proof, down-only) —
build + test; **hold + document if any doubt**". This is that document.

**What shipped:** `finance.Invoice` only, DOWN-ONLY.
**What is held out:** `finance.Payment` and `finance.PaymentProofUpload`.

The hold is not an oversight or a time-box. Two independent, verified reasons block those
two models, and either one alone is sufficient.

## Why Invoice could ship

- It already carries `updated_at` with `auto_now=True`, which the delta cursor requires.
- Its policy is now **declared explicitly** in `policy_registry.POLICIES` as
  `MANUAL_REVIEW` + `protected=True`, rather than inheriting protection from
  `get_policy`'s fail-closed default for unknown entities. Money must not depend on a
  default staying the way it is today.
- `protected=True` makes the direction guarantee absolute: `_conflict_decision` returns
  `apply` only for `cloud-pull`. A box push or an online edit returns `conflict` and lands
  in the Sync Center. **A box can never move an invoice amount.**
- Its two `FileField`s (`attachment`, `payment_proof`) are dropped by the FileField guard
  in `_derive_sync_fields`. A delta bundle carries column values, never file bytes, so a
  synced path would point the box at a file that does not exist there.

The product value is real and bounded: a bursar keeps working through an outage because
the box knows what is **owed**, while every write stays cloud-authoritative.

## Why Payment and PaymentProofUpload are held

### 1. No delta cursor exists on either table

Neither model has an `updated_at` column at all. `build_edge_delta_bundle` filters
`updated_at__gt=since` for every incremental sync, so registering them does not degrade —
it raises:

```
FieldError: Cannot resolve keyword 'updated_at' into field.
Choices are: amount, audit_logs, completed_at, compliance_checked, compliance_issues,
created_at, ...
```

This is verified, not predicted (see the audit in the wave-4 commit).

Adding the column is **not** a benign additive migration. `auto_now=True` rewrites the
value on **every save** of the platform's money ledger, which changes write behaviour on
`finance_payment` — the table most likely to be reconciled, audited, and trusted
byte-for-byte. That deserves its own reviewed change with its own reconciliation testing,
not a line inside a sync wave.

### 2. Payment holds live settlement state, which policy already forbids on this rail

`policy_registry.POLICIES` declares:

```
payment_settlement -> MergeStrategy.ONLINE_REQUIRED
  "Executing a charge against a gateway is a live transaction; offline evidence ..."
```

`ONLINE_REQUIRED` means `_conflict_decision` returns `reject` — such rows are *never*
applied through the offline/sync path. `finance.Payment` carries exactly that state:
`gateway_transaction_id`, `gateway_response`, `external_reference`, `completed_at`,
`failed_at`, `compliance_checked`.

So putting `Payment` on the two-way rail would contradict the platform's own declared
rule. The honest resolution is not to register it and hope the policy catches it — it is
to decide, deliberately, which *subset* of payment data (if any) is offline-replayable,
and give that subset its own entity and its own policy row.

## Conditions to revisit

Registering these is a **product + finance decision**, not a mechanical follow-up. Before
it happens:

1. Decide whether `finance_payment` may carry an `auto_now` `updated_at`, with sign-off
   from whoever owns ledger reconciliation. A monotonic, explicitly-set `synced_at` may be
   the safer shape than `auto_now`.
2. Split settlement state from the payment *record*. A receipt a bursar recorded offline
   is a different thing from a gateway charge, and only the former can ride.
3. Decide how the box learns about payments it must not author — a read-only projection is
   probably the right answer rather than a two-way entity.
4. Resolve the file-bytes channel for `receipt_file` (both held models have one), since
   syncing a path is not syncing a file.

## Enforcement

The hold is asserted by tests, not just written here — see
`apps/sync_engine/tests/test_edge_sync_finance_down_only_2026_08_17.py`:

- `test_payment_and_proof_are_not_on_the_rail` — they must stay off the registry.
- `test_payment_settlement_is_declared_online_required` — locks reason 2.
- `test_held_out_money_models_still_lack_the_delta_cursor` — a **revisit trigger**. If
  anyone adds `updated_at` to `Payment` or `PaymentProofUpload`, this test fails, forcing a
  conscious decision about this document instead of letting the hold quietly rot.

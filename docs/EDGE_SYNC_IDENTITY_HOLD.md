# Edge sync — identity, and why `TeacherProfile` rides only one way for some columns

Status: **shipped 2026-08-17** (Wave 5). Companion to
[`EDGE_SYNC_FINANCE_HOLD.md`](EDGE_SYNC_FINANCE_HOLD.md).

`people.TeacherProfile` is now a registered edge-sync entity. It was the last deferred
one, because it is three different kinds of data wearing one model: a staff **roster**, a
**payroll** record, and an **authorization** surface anchored to a login. Each needs a
different direction, so this entity is the first to use per-**field** direction policy as a
first-class mechanism rather than a one-field seed.

## What rides which way

| Columns | Direction | Why |
|---|---|---|
| `staff_id`, `phone`, `position_title`, `department_id`, `reports_to_id`, `custom_attributes`, `default_dashboard_view`, `mark_reminder_opt_in` | **two-way (CAUSAL_LWW)** | Ordinary roster/preference data. A phone number corrected during an outage should just merge. |
| `pay_grade`, `pay_scale_id`, `salary_amount`, `salary_cap`, `next_pay_date`, `paystub_notes`, `payment_method` | **down-only** | Payroll is computed and approved centrally, exactly like money. A box offline for a week holds a stale figure. `payment_method` decides where money is *sent*, so an upward edit is a payment-redirection vector. |
| `allow_finance_panel`, `allow_paystub_access`, `allow_leave_approvals` | **down-only** | These read like preferences and are not. `allow_finance_panel` gates the teacher payroll block — `PayrollEmployee`, payslips, net pay (`apps/portal/services.py::_teacher_finance_block`); `allow_leave_approvals` confers approval authority. A box able to push them could **grant payroll visibility or approval rights on the cloud**. `policy_registry` already states the rule for this class: `permission_grant` is `SERVER_AUTHORITATIVE` because "authorization changes must be validated by the server." |
| `is_active`, `merged_into_id` | **down-only** | Offboarding and duplicate-merge are governance actions. A stale box must not reinstate a staff member the cloud deactivated, nor redirect a merge pointer. |
| `user` / `user_id` | **never synced** | See below. |
| `profile_photo` | **never synced** | A `FileField`. The bundle carries no bytes, so a synced path would dangle. Dropped by the engine's FileField guard. |

Down-only means the box **receives** the value and can compute with it offline. It is a
direction rule, not an exclusion — that distinction is the whole reason this mechanism
exists. Excluding compensation entirely would leave a head teacher unable to see staffing
costs offline; leaving it two-way would let a stale box move pay.

## The identity problem, and the answer

`TeacherProfile.user` is a **non-nullable** `OneToOneField` to `accounts.User`, and
`accounts.User` is a **SHARED / public-schema** model. Its primary key is therefore *not
portable*: the same person is a different `user_id` on the box and on the cloud.

The engine already handles this correctly and it was verified by running
`_derive_sync_fields(TeacherProfile)` rather than assumed — `_is_sync_tenant_model` drops
any FK whose target lives outside the tenant apps, so `user_id` never enters the synced
field set. A test asserts this directly, and a second test asserts that a box which
*explicitly sends* `user_id` anyway has it ignored.

The consequence is deliberately asymmetric:

- **UPDATE is safe, and is what registration buys.** The tenant clone is pk-preserving, so
  a profile row matches by pk on both sides and each side keeps its own `user` link
  untouched. Roster edits converge; pay and authorization flow down.

- **INSERT is refused.** A teacher created offline on the box cannot be landed on the
  cloud, because doing so would require the sync rail to **mint an `accounts.User`** —
  deciding who may sign in, with what role, under whose authorization. That is an
  authentication decision, not a data merge. **A rail that can create identities is a rail
  that can grant access**, and this rail authenticates with a long-lived machine
  credential held on a physical box in a school office.

  The refusal is explicit (`_INSERT_HELD_ENTITIES`, HTTP 409 `insert_held_for_entity`, with
  the reason in the payload) rather than left to fail on the database constraint. Letting
  it reach the `NOT NULL` violation would report an opaque `IntegrityError` every cycle
  instead of the actual reason.

  **Operational path:** create the staff member on the cloud; the profile syncs down to the
  box on the next pull, and from then on the box may edit its roster fields.

## Enforcement is on every inbound path

The first version of this policy guarded only `_apply_changes_inner` (update-by-pk).
`apply_edge_inserts` (upsert-by-`client_offline_id`) filtered candidate fields by the
entity's allowed set and the model's settable names, and **not** by direction — so the
whole policy was bypassable by presenting an edit as a new row: the value the update path
refuses with 409 landed cleanly as an insert.

Direction is a property of the **field**, so both paths now apply the map, report the same
`rejected_down_only_fields` key, and are covered by
`apps/sync_engine/tests/test_edge_sync_down_only_insert_path_2026_08_17.py`, which proves
the hole against the pre-existing `subject_assignment.coefficient` seed so the regression
seal does not depend on this wave's new entity.

## Known behaviour worth understanding

**Convergence can need a second round trip.** Direction is per-field but the conflict
decision is per-**row**. If a box edits `phone` at T2 while the cloud edited
`salary_amount` at T1 (T1 < T2), the box's pull sees an older cloud row and records a
conflict rather than applying it, so the stale salary persists for that cycle. The box then
pushes T2 up, the guard strips the salary, the cloud applies the phone and its row becomes
T3 > T2 — and the next pull delivers the correct salary. It converges, one cycle later.
Making this immediate would require per-field conflict resolution (a column-level clock),
which is a much larger change than per-field *direction*.

**`pay_scale_id` points at `payroll.PayScale`, which is not itself a registered entity.**
`PayScale` is a tenant model, so its pk is stable across the pk-preserving clone and
shipping the id verbatim is correct for cloned rows. A `PayScale` **created offline** would
not be remapped (`_insert_fk_targets` only remaps FKs onto registered entities) — but
`pay_scale_id` is down-only, so a box-authored value is refused before it can matter.

## Conditions to revisit

1. **Offline-created staff.** Would need a provisioning handshake that is explicitly an
   authentication flow: the box submits a *request*, an authorized human on the cloud
   approves it, and the User is minted there. That is a feature, not a sync-policy change,
   and it must never be implicit in a bundle apply.
2. **Per-field conflict resolution.** Would remove the extra round trip described above.
3. **`custom_attributes` is two-way and whole-blob.** LWW on a JSON dict overwrites the
   whole value, so a cloud-side key added during an outage can be lost when the box's
   version wins. Splitting it per-key needs a merge strategy for JSON, not a direction rule.

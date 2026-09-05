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

  **The refusal is SYMMETRIC, and this document used to get that wrong.** The same check
  runs in `_create_from_cloud_pull`, so a teacher created on the CLOUD cannot be created
  on a box either. This paragraph previously read "create the staff member on the cloud;
  the profile syncs down to the box on the next pull" -- which is what the 409 payload
  also said, and neither was true. Measured 2026-08-29 on a rebuilt Gilead box: 39
  teachers on the cloud, refused on all 687 sync cycles of that day, ~39 rows of the
  26,598 "NOT applied" total per cycle.

  The tenant bundle does not rescue it either. `export_tenant_bundle` walks
  TENANT_APP_LABELS, which includes `people`, so `people.teacherprofile` IS exported --
  with `user_id` intact -- while `accounts` is not a tenant app, so the Users are not.
  `import_tenant_bundle` runs inside `transaction.atomic()`, so the dangling FK does not
  skip the teachers: it rolls the WHOLE tenant import back and nothing lands.

  **Operational path:** `export_tenant_staff` on the cloud, `import_tenant_staff` on the
  box (`apps/lifecycle/staff_portability.py`). It is pk-preserving, so once the rows
  exist on both sides ordinary delta sync converges by UPDATE-by-pk -- which is exactly
  what this hold permits -- and the per-cycle skip count for teachers falls to zero.
  Running that command is the explicit human act condition 1 below asks for; nothing on
  the sync rail can reach it, and it can never mint a superuser.

  **It must run BEFORE `import_tenant_identities`, and the order is not the obvious
  one.** That command matches Users by `username__iexact` and otherwise constructs
  `User(username=...)` with a fresh pk -- its `_USER_FIELDS` has no `id`, so it cannot
  preserve one. Run it first and the teacher logins land at box-local pks; the staff
  bundle then refuses (`staff_bundle_pk_collision`) rather than overwrite them, and the
  operational bundle still dies on the dangling FK because the `user_id` it carries is
  the cloud's. Staff first, identities second: identities then finds those same rows by
  username and updates them in place, adding memberships and MFA without touching pks.
  `apps/lifecycle/edge_onboarding.py` orders the two steps accordingly, and
  `apps/lifecycle/tests/test_edge_onboarding_staff_sequence_2026_08_30.py` drives the
  real step list rather than a copy, so a reorder fails there.

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

1. **Offline-created staff (box -> cloud).** CLOSED 2026-09-04, by exactly the
   handshake this entry specified: the box submits a *request*, an authorized human on
   the cloud approves it, and the User is minted there. It is a feature, not a
   sync-policy change, and it is not implicit in a bundle apply.

   This section said "Still open" while the mechanism was being built, and the reason it
   is being updated in the same change rather than afterwards is on the record: commit
   `38c45baea` exists because this file described a path that did not work, and an
   operator followed it and waited for a sync that could never happen. A stale doc here
   has already cost somebody a day.

   **What actually happens now.** `apply_edge_inserts` still refuses the insert, still
   returns 409 `insert_held_for_entity`, and still mints nobody — none of that moved. The
   refusal additionally writes a `people.ProvisioningRequest` (see
   `apps/people/provisioning_service.py`) carrying only portable DATA; `sanitize_payload`
   drops anything credential-shaped, so no password, hash, session or `is_superuser`
   crosses. Nothing is granted on arrival. `apps/people/views_provisioning.py` is the
   screen where a person holding `staff.provision` answers it, and the 409 now carries a
   `provisioning_request` block so the box can say "submitted for approval, asked N
   times" instead of repeating a refusal with no next step.

   Three properties are load-bearing, and each has a test:

   * the request is unique per `(school, entity_type, client_offline_id)`. A box
     re-submits every cycle; the measured Gilead case was 39 rows on 687 cycles in a
     day, which without this constraint is 26,000 copies of the same question;
   * approval carries the box's `client_offline_id` onto the created record, so the next
     ordinary sync matches the two rows by anchor and converges them. Without it,
     approval creates a SECOND person and the box keeps asking;
   * the account is created with `set_unusable_password()` and never `is_staff` /
     `is_superuser`. Approving a person and issuing them a credential stay two separate
     acts — collapsing them would rebuild the hole this document exists to describe.

   A `student_guardian` request is approvable too, but its student is **not** resolved in
   code. The row names a child by the BOX's pk, and a box-created student is assigned a
   fresh pk on the cloud, so that number may name a different child entirely. Approval
   requires its caller to name the student and the queue shows a candidate — looked up by
   that pk, within the school, by name — for a person to confirm. The ambiguous half is
   decided by a human who can see a name; the machine does the unambiguous half.

   The **cloud -> box** half was closed earlier by `staff_portability`, and it was always
   the easier half: the authentication decision has already been made, by a human, on the
   cloud. All the box needs is to be handed the result.
2. **Per-field conflict resolution.** Would remove the extra round trip described above.
3. **`custom_attributes` is two-way and whole-blob.** LWW on a JSON dict overwrites the
   whole value, so a cloud-side key added during an outage can be lost when the box's
   version wins. Splitting it per-key needs a merge strategy for JSON, not a direction rule.

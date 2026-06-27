# CRDT live rail — conflict-free offline sync (SOT)

This is the engineering reference for the **CRDT (Conflict-free Replicated Data
Type) live rail** — the path that lets multiple offline devices edit a small set
of approved, low-risk tenant state and converge to one durable answer no matter
what order their edits eventually reach the server.

It is a *third* offline mechanism, distinct from the two write rails described in
[`docs/OFFLINE_TWO_RAIL_ARCHITECTURE.md`](OFFLINE_TWO_RAIL_ARCHITECTURE.md)
(SODP/OfflineAction and WAL). Those two rails carry typed *intents* that the
server *applies*; the CRDT rail carries *operations* that the server *merges* into
a converged register/set/counter and persists.

> **TL;DR** — A client POSTs a batch of CRDT ops to `/api/v1/crdt/apply/`. The
> view merges them into per-tenant `School.settings['crdt_state']` inside a real
> `transaction.atomic()` guarded by `select_for_update()`. Merge is commutative +
> associative + idempotent, so delivery order and at-least-once redelivery do not
> change the result. Only entities that the policy registry marks as safe for a
> CRDT kind are accepted; everything financial/identity/auditable fails closed.

---

## 1. What converges (the three CRDT types)

Implemented in [`apps/sync_engine/crdt_wire_protocol.py`](../apps/sync_engine/crdt_wire_protocol.py).
All three merge functions are pure Python (no DB), so they run identically in a
service worker, a Tauri client, and the server.

| Type | Op dataclass | Merge | Invariant | Use |
|------|--------------|-------|-----------|-----|
| **LWW** — Last-Write-Wins register | `LWWOp` (`crdt_wire_protocol.py:94`) | `lww_merge` (`:107`) — pick the larger HLC | larger Hybrid Logical Clock wins; ties broken by actor | scalar drafts (`student_note`, `lesson_plan`) |
| **OR-Set** — Observed-Remove set | `ORSetOp` (`:125`) | `orset_merge` (`:145`) — add carries a unique tag; remove carries the tags it observed | an element survives a concurrent add+remove iff the remove did not observe that add's tag | tag sets (`lesson_plan_tags`) |
| **G-Counter** — grow-only counter | `GCounterOp` (`:192`) | `gcounter_merge` (`:210`) — component-wise max per actor cell; total = sum of cells | retry is idempotent (max, not +=); negatives rejected | non-authoritative telemetry (`telemetry_counter`) |

Total ordering for LWW comes from a **Hybrid Logical Clock**, `HLC`
(`crdt_wire_protocol.py:41`): `(physical_ms, logical, actor_id)` compared
lexicographically, wire-encoded as `"<physical>:<logical>:<actor>"`
(`HLC.to_wire`/`HLC.from_wire`, `:54`/`:58`; advance rule `hlc_tick`, `:78`).

## 2. The wire protocol

A request body is `{"ops": [ ... ], "device_id": "<str>"}`. Each op is a dict
parsed by `parse_wire_op` (`crdt_wire_protocol.py:236`):

```jsonc
// LWW
{"kind": "LWW", "entity": "student_note", "key": "student_note:draft-1",
 "value": "...", "hlc": "100:0:wire"}
// OR-Set add / remove
{"kind": "ORSET-ADD",    "entity": "lesson_plan_tags", "set_key": "lesson_plan_tags:plan-1",
 "element": "exam", "tag": "tag-A-exam", "observed_tags": []}
{"kind": "ORSET-REMOVE", "entity": "lesson_plan_tags", "set_key": "lesson_plan_tags:plan-1",
 "element": "quiz", "tag": "", "observed_tags": ["tag-A-quiz"]}
// G-Counter (ABSOLUTE per-actor value, not a delta)
{"kind": "GCOUNTER", "entity": "telemetry_counter",
 "counter_key": "telemetry_counter:offline-captures", "actor_id": "wire", "value": 3}
```

Notes the code enforces:

- **G-Counter is state-based, not delta-based.** `parse_wire_op` rejects a
  `GCOUNTER` op with no absolute `value` ("delta-only operations are not
  replay-safe", `crdt_wire_protocol.py:257`). This is what makes redelivery a
  no-op.
- **Every key must be namespaced to its entity.** The view's
  `_validate_key_namespace` (`views_crdt.py:163`) requires the `key`/`set_key`/
  `counter_key` to start with `"<entity>:"`, so one entity cannot write another's
  state.
- **The actor is server-bound, not client-trusted.** The view overwrites each
  op's actor with `u{user.pk}:{device_id}` (`_bound_actor_id`,
  `views_crdt.py:154`), so the G-Counter sums one cell per real device and LWW
  ties resolve to a real principal.

## 3. The server applier

[`apps/sync_engine/views_crdt.py`](../apps/sync_engine/views_crdt.py) —
`CRDTOpsApplyView` (`:17`), `@login_required` + `@csrf_protect`, routed at
`/api/v1/crdt/apply/` (`apps/api/urls_v1.py:66`, name `crdt-apply`).

Per request it:

1. Caps the batch at `max_ops_per_request = 200` (`views_crdt.py:20`).
2. Resolves the tenant from `request.tenant`/`request.school` (`:37`); 400 if absent.
3. Opens `transaction.atomic()` and `select_for_update().get(pk=tenant.pk)`
   (`:59`) — on Postgres this takes a real row lock so concurrent requests
   serialize through merge-then-persist.
4. Reads the durable `crdt_state` (`_read_state`, `:183`), validates each op
   against the policy registry, merges it into the in-memory state, and writes
   the whole state back (`_write_state`, `:197`) to `School.settings['crdt_state']`.
5. Returns `{"applied", "rejected", "materialized", "policy_version"}`. Bad ops
   are collected into `rejected` (with index + reason) and never abort the batch.

## 4. Conflict resolution / which entities are allowed

The policy registry [`apps/sync_engine/policy_registry.py`](../apps/sync_engine/policy_registry.py)
is the SOT for *which* entity may use *which* CRDT kind and *how* a non-CRDT
conflict is resolved. `validate_crdt_kind` (`policy_registry.py:160`) rejects any
op whose `kind` is not in that entity's `allowed_crdt_kinds`, raising
`crdt_kind_not_allowed:...`.

CRDT-eligible entities (the only ones the live rail will merge):

| Entity | Strategy | Allowed CRDT kinds |
|--------|----------|--------------------|
| `student_note` | `causal_lww` | `LWW` (`policy_registry.py:50`) |
| `lesson_plan` | `causal_lww` | `LWW` (`:56`) |
| `lesson_plan_tags` | `or_set` | `ORSET-ADD`, `ORSET-REMOVE` (`:67`) |
| `telemetry_counter` | `g_counter` | `GCOUNTER` (`:73`) |

Everything else **fails closed**. `grade_entry`, `fee_payment`,
`payment_proof_upload`, `invoice_line` are `manual_review` + `protected`; messages
and behavior events are `append_only`; identity/permissions are
`server_authoritative` (`policy_registry.py:79`–`:138`). Unknown entities default
to `manual_review` + `protected` (`get_policy`, `:147`). A protected policy cannot
be overridden by a caller-supplied strategy (`resolve_one`, `conflict_resolver.py:79`,
`override_blocked` at `:87`). Causal conflicts that are not CRDT-merged are decided
by Hybrid-Logical-Clock rank with "tie → prefer server" (`_causal_decision`,
`conflict_resolver.py:56`).

## 5. What is proven

[`apps/sync_engine/tests/test_crdt_live_rail_convergence.py`](../apps/sync_engine/tests/test_crdt_live_rail_convergence.py)
drives a fixed multi-device, multi-type op program **through the live view's DB
persistence path** (not the in-memory legacy `crdt.py` module the
`verify_crdt_convergence` management command checks). It is `@requires_postgres`
+ `@tag("tenants_rls")` and runs in `.github/workflows/django-tests-postgres.yml`,
because only on Postgres does the view's `select_for_update` take a real lock.

| Test | Proves |
|------|--------|
| `test_order_independent_convergence_on_persisted_rail` (`:241`) | three delivery orders (A,B,C / C,B,A / B,C,A) yield byte-identical persisted state, including the winning HLC stamps |
| `test_interleaved_per_op_delivery_converges` (`:266`) | per-op interleaving (each op its own request, re-reading durable state) converges to the same end state |
| `test_idempotent_redelivery_does_not_lose_or_double` (`:296`) | replaying the whole program twice equals one pass — no doubled counter, no resurrected/dropped tag |
| `test_concurrent_edit_to_same_key_keeps_higher_hlc_no_loss` (`:317`) | two devices clash on one key; the higher-HLC write wins, the same winner regardless of arrival order, the loser is not silently kept before merge |

## 6. Honest scope / limitations

- This proves **order-independent convergence on the live rail through DB
  persistence** (metric #25 deliverable). It is explicitly **not** the 5–7 day
  full-application offline E2E, which remains a separate deferred item — see the
  test module's own scope note (`test_crdt_live_rail_convergence.py:24`) and the
  adjacent `apps/platform_runtime/tests/test_offline_multiday_replay_simulation`.
- State lives in `School.settings['crdt_state']` (a JSON column), not a dedicated
  per-op table. The rail is sized for the small, approved namespaces above; it is
  not a general document store.
- Anything money/identity/grade/audit-shaped is **deliberately excluded** from
  CRDT merge and routed to `manual_review` / `server_authoritative` / `append_only`.
  Do not add such an entity to `allowed_crdt_kinds`.
- There is a separate legacy in-memory module (`apps/sync_engine/crdt.py` +
  `crdt_wallet.py`) exercised by the green `verify_crdt_convergence` management
  command. It is **not** the rail that ships; the live rail is the view + wire
  protocol documented here.

## 7. Sibling docs

- Two write rails (SODP + WAL): [`docs/OFFLINE_TWO_RAIL_ARCHITECTURE.md`](OFFLINE_TWO_RAIL_ARCHITECTURE.md)
- Offline capability CI gate: `scripts/verify_offline_capability_implementation.py`

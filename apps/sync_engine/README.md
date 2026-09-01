# apps/sync_engine

> The offline-first convergence layer: the versioned conflict-policy registry,
> the CRDT wire protocol, signed delta bundles, and the tenant offline manifest.

**Tenancy:** SHARED (public schema; the app declares no models at all, so it owns no tables in either schema)
**Scale:** 0 models · 0 migrations · 18 test modules · ~4.0k LOC

## What this app owns

Sync engine is what makes an edge device — a phone in a compound with no signal, a
LAN-only terminal, a data mule walking a USB stick between sites — able to make
changes and have them converge with the cloud without a human adjudicating every
collision. It owns the *rules and the algebra* of that convergence: which entity
merges by which strategy, the typed wire format ops travel in, the merge functions
themselves, and the signed bundle format for offline transport.

The defining decision is stated in `crdt.py`: **on the CRDT rail, conflict
resolution is by logical clock, never by wall clock.** Wall-clock last-write-wins
was explicitly rejected there — two devices with skewed clocks would silently destroy
each other's data. Instead, ordering is by Lamport clock with a replica-id
tiebreak (`crdt.py`) or a Hybrid Logical Clock with an actor-id tiebreak
(`crdt_wire_protocol.py`), so merges are deterministic and causal. The compat
alias `ResolutionStrategy.LAST_WRITE_WINS` still exists for old callers, but it
now points at `CAUSAL_LWW` — the name lies, the behavior does not.

**That claim is about the CRDT rail, and the CRDT rail is four entities.** This is
the correction the sentence above needs, because for a long time it said "enforced
everywhere" and it is not. `validate_crdt_kind()` authorizes exactly `student_note`,
`lesson_plan`, `lesson_plan_tags` and `telemetry_counter`; every other entity has an
empty `allowed_crdt_kinds` and is refused at the door.

**The rail that carries the school's data — students, enrolment, attendance, marks,
invoices — is the signed delta rail, and it resolves by WALL CLOCK.**
`apps.api.sync_services._conflict_decision` compares `client_updated_at < server_dt`
and keeps the newer timestamp. Three things bound that, and they are the reason it is
a defensible design rather than the thing `crdt.py` rejected:

* **Protected and authoritative domains never reach the comparison.** Money, grades and
  identity are `protected` in the policy registry: a `cloud-pull` applies, and anything
  travelling the other way becomes a `SyncConflict` for a human. `ONLINE_REQUIRED`
  domains are rejected on the sync path outright. Skewed clocks cannot touch these.
* **A row that cannot prove it is newer does not win.** A missing or unparseable
  `client_updated_at` against a timestamped server row is a conflict, not an overwrite.
* **The cursor's own tolerance is stated and finite.** `get_sync_cursor_for_request`
  re-asks from `RMC_EDGE_SYNC_CURSOR_OVERLAP_SECONDS` (120s) behind the stored
  high-water, which closes the commit-after-read race and the tie-at-a-boundary case for
  any transaction shorter than that window — and no longer.

What is left after those bounds is real and should not be written away: for an
unprotected LWW entity, a box whose clock is FAST can overwrite a genuinely newer cloud
row and the apply path will record it as an ordinary success. That is a wall-clock race,
on the rail that carries most of the data, and the honest mitigation is operational
rather than algebraic — which is why the pull leg now measures the box/cloud offset from
the response `Date` header on every cycle (`clock_offset.py`) and says so on the run
when the drift has grown past the overlap the cursors depend on.

The second decision is that **the CRDT primitives are pure Python with no Django
import**, so byte-identical code runs in a service worker, a Tauri shell, and the
cloud. That is also why they are testable in `SimpleTestCase` without a database.

The third — and the one that keeps this app honest — is that **most domains are
not allowed to converge automatically at all.** The policy registry is a
conservative allowlist, not a permissive default. Grades, payments, invoice lines,
and payment evidence are `MANUAL_REVIEW` or `ONLINE_REQUIRED`: a human decides, or
the operation simply is not permitted offline.

## Key models

**None — this app declares no Django models and ships zero migrations.** That is
deliberate. `models.py` is a one-line pointer: domain logic lives in `services.py`,
and the actual offline queue rows are `apps.api.mobile_api.OfflineSyncQueue`
(device-scoped replay API), owned by `apps.api`. The persisted CRDT state written
by the live rail goes into the `School.settings["crdt_state"]` JSON bucket, not a
table of its own. If you are looking for a `SyncOp` or `CRDTState` model, there
isn't one, and adding one would move the tenant boundary — think hard first.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `policy_registry` | `POLICY_VERSION = 2`; the per-entity `SyncPolicy` table and `validate_crdt_kind()`. The authority on what may sync |
| Module | `crdt_wire_protocol` | The live protocol: `HLC`, `LWWOp`, `ORSetOp`, `GCounterOp` + `lww_merge` / `orset_merge` / `gcounter_merge` |
| Module | `crdt` | Legacy in-memory primitives (`lamport_tick`, `LWWRegister`, `GSet`); parallel to the wire protocol, not the live rail |
| Module | `crdt_wallet` | Grow-only op-set wallet for multi-terminal offline debits; Decimal-safe |
| Module | `conflict_resolver` | `resolve_one()` — policy-governed strategy dispatch for queued replay |
| Module | `event_envelope` | Canonical offline envelope, capped at `MAX_ENVELOPE_BYTES = 1024`. Queued sync, **not** CRDT |
| Module | `delta_bundle` | HMAC-signed NDJSON bundles for LAN / data-mule transport (`application/x-rmc-sync-bundle+ndjson`) |
| Module | `compression` | Gzip on the sync wire, per-endpoint. Read its docstring before reaching for `GZipMiddleware` |
| Module | `clock_offset` | Box-vs-cloud wall-clock drift, measured from the pull response's `Date`. Records and warns; never corrects |
| Module | `tenant_manifest_compiler` | Deterministic offline manifest (schema version 2): route allowlist, data policies, PWA cache hints |
| Module | `services` | Pending-change reads and visible sync state over `OfflineSyncQueue` |
| Module | `views_crdt` | `CRDTOpsApplyView` — the live rail. Mounted by `apps.api` (see below), not by this app |
| Command | `verify_crdt_convergence` | Asserts the merge algebra converges under reordering. Read its scope docstring before citing it |
| Command | `verify_sync_semantics` | Asserts protected policies have not been weakened (e.g. grades still `manual_review` with `override_blocked`) |

This app has **no `urls.py`**. Its one HTTP surface, `CRDTOpsApplyView`, is routed
by `apps/api/urls_v1.py` as `crdt/apply/` (name `crdt-apply`).

**Which entities may actually use the CRDT rail:** only four, and only with the
kinds their policy allows — `student_note` (LWW), `lesson_plan` (LWW),
`lesson_plan_tags` (ORSET-ADD / ORSET-REMOVE), and `telemetry_counter` (GCOUNTER).
Every other entity has an empty `allowed_crdt_kinds`, so `validate_crdt_kind()`
rejects it at the door. The CRDT machinery is general; its live authorization is
narrow, on purpose.

## Before you change this

- **Never reintroduce wall-clock ordering ON THE CRDT RAIL.** This is the app's
  founding rejection. `conflict_resolver.py` keeps the comment on the compat alias:
  it "now means causal logical-clock ordering, never a raw wall-clock race." If a
  CRDT merge needs a tiebreak, use the logical clock and the replica/actor id. Do not
  read this bullet as a statement about the delta rail — that one already orders by
  `updated_at` (`sync_services._conflict_decision`) and always has. Moving IT to a
  logical clock is not a refactor: it would need a monotonic sequence column written in
  the same transaction as the business row, on every synced table.
- **A pull page boundary may never split rows that share one `updated_at`.**
  `page_delta_rows` (`edge_outbox.py`) cuts only BETWEEN groups, so a page can come
  back smaller than the requested limit — and, when one timestamp group is bigger than
  the whole limit, larger. Both are deliberate. `get_sync_cursor_for_request` closes the
  tie-at-a-boundary hole for a whole CYCLE with a 120-second overlap; paging inside a
  cycle would open it far wider than that overlap can close, because a first sync pages
  across years of history in one cycle and its cursor ends months past the split, not
  120 seconds past it. Do not "optimise" the cut to `rows[:limit]`.
- **`crdt.py` is not the live rail; `crdt_wire_protocol.py` is.** They are parallel
  implementations, and `verify_crdt_convergence` calls the legacy one "the parallel
  legacy toy" in its own docstring. `CRDTOpsApplyView` calls the *wire protocol*
  merges. Fixing a bug in one does not fix it in the other.
- **`verify_crdt_convergence` proves the algebra, not the persistence.** Its
  docstring is explicit and worth honoring: it deliberately does not touch the
  `select_for_update` + `transaction.atomic()` write to
  `School.settings['crdt_state']`, because a fast no-DB self-check must not assume
  a database. The convergence proof *through* the persisted rail is the Postgres
  test `tests/test_crdt_live_rail_convergence.py`. Neither claims a multi-day
  full-application offline E2E — that remains a separate deferred item. Do not
  upgrade that claim in any doc, changelog, or scorecard.
- **The overdraft honesty in `crdt_wallet` is a CAP theorem, not a gap.** You
  cannot prevent an overdraft across partitioned terminals without coordination.
  The wallet therefore *detects* the deficit at reconciliation and surfaces it,
  rather than pretending to prevent it; `reserve_debit` only rejects locally when
  the balance is actually known. Do not "fix" this into a distributed lock.
- **`ONLINE_REQUIRED` is not `SERVER_AUTHORITATIVE`.** The v2 comment draws the
  line: under `SERVER_AUTHORITATIVE` an offline attempt is accepted and the
  server's copy later wins; under `ONLINE_REQUIRED` the domain may not be *queued*
  offline at all — a live transaction is the only valid path. Collapsing them would
  silently start accepting money operations offline.
- **`protected=True` policies exist to be un-weakenable.** Grades, invoice lines,
  fee payments, payment proof, messages, and behavior events are protected with a
  recorded `rationale` each ("concurrent grade changes require an accountable human
  decision"). `verify_sync_semantics` fails the build if a protected policy loses
  its guard. Changing one is a product decision, not a refactor.
- **Bump `POLICY_VERSION` when you change the policy table.** It is stamped into
  every envelope, every delta bundle header, and the persisted CRDT state, so
  clients and bundles can be reasoned about after the rules move. Editing policies
  without bumping it makes old and new bundles indistinguishable.
- **The live rail enforces a key namespace and rebinds the actor.**
  `_validate_key_namespace` requires every op key to start with `"<entity>:"`, and
  `_bound_actor_id` overwrites the client-supplied actor with
  `u<user.pk>:<device>` derived server-side. A client cannot claim to be another
  actor or write outside its entity's namespace. Both guards are load-bearing.
- **The manifest compiler must never leak secrets.** It exposes only what the edge
  PWA needs (routes, policies, cache hints, schema version, signature posture) and
  filters `_SENSITIVE_KEYS` — passwords, tokens, api keys, private keys, SSN, DOB.
  Anything you add to the manifest ships to every offline device.
- Offline envelopes are capped at 1KB (`MAX_ENVELOPE_BYTES`) and delta bundles are
  HMAC-signed with `RMC_SYNC_BUNDLE_SIGNING_KEY` (falling back to `SECRET_KEY`).
  An unsigned or oversized payload is rejected, not truncated.

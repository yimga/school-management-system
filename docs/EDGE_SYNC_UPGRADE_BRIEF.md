# Edge↔Cloud Sync: the upgrade brief

> **STATUS — 2026-08-20: this brief has been executed.** G1–G7 and the replay-defence
> item are implemented, tested and landed; the sections below are kept as the record of
> WHY each was built, with a `DONE` line naming where each now lives and what is
> genuinely still open. Read `## What shipped` at the foot of this file first if you only
> want the current state.

**Purpose.** A copy-pasteable prompt for a Claude Code session tasked with making
RunMyCampus sync between the internet-facing cloud and any intermittently-connected
appliance *provably* correct. It is written against what this repo **actually has**, so a
session does not spend its budget rebuilding parts that already exist or applying a
generic blueprint that would regress deliberate design.

Read `docs/EDGE_SYNC_OPERATIONS.md` for operations, `docs/EDGE_SYNC_FINANCE_HOLD.md` and
`docs/EDGE_SYNC_IDENTITY_HOLD.md` for the two deliberate hold-outs, and the
`## 2026-08-19` entry in `docs/CSS_RETIREMENT_DOCKET.md` for the referential-integrity
defect class that motivated this brief.

---

## The prompt

> You are hardening the edge↔cloud synchronisation engine of RunMyCampus so that a school
> running an on-premise appliance with intermittent or absent internet converges with the
> cloud completely, automatically, and verifiably — with no silent divergence and no
> operator guesswork.
>
> **Work the standard execution loop** (`docs/RMC_STANDARD_EXECUTION_LOOP.md`):
> AUDIT → IDENTIFY → FIX → TEST → RE-AUDIT → IMPROVE → REPORT. Audit by **running** the
> engine — execute the cycle, hit the endpoint, print the computed value. Reading tells you
> intent; running tells you behaviour, and on this subsystem the two have diverged on every
> serious finding so far. Every fix ships a test that **fails before it**. Do not exit until
> the sync suites and `python scripts/pre_push_boundary_check.py` are green and a
> from-scratch re-audit confirms each finding closed.
>
> ### Ground truth — what already exists. Do not rebuild it.
>
> | Concern | Where it lives | State |
> |---|---|---|
> | Delta protocol | `apps/sync_engine/edge_outbox.py`, `delta_bundle.py` | HMAC-signed NDJSON bundles, school-bound, paged at the receiver's cap |
> | Direction + authority | `apps/sync_engine/policy_registry.py` | Per-entity merge strategy; money `ONLINE_REQUIRED`, grades/invoices down-only, master data LWW |
> | Per-field direction | `apps/api/sync_services.py::_DOWN_ONLY_FIELDS_PER_ENTITY` | Enforced on **both** inbound paths |
> | Cursors | `apps/sync_engine/models.py::EdgeSyncCursor` | Durable per-direction high-water, advanced only over confirmed work |
> | Echo suppression | `SyncApplyLedger` | Provenance-based, not clock-compare |
> | Clocks / CRDT | `apps/sync_engine/crdt*.py` | HLC, LWW/ORSet/GCounter for the CRDT rail |
> | Cadence | `apps/sync_engine/cadence.py`, `connectivity.py` | HOT/STEADY/BACKOFF + cheap TCP probe + restore wake; ~15s worst case when busy |
> | Full replay | `EdgeSyncDirective`, `reset_sync_cursors` | Cloud-queued, collected on the box's own next download |
> | Referential integrity | `_unresolvable_fk`, `_create_from_cloud_pull`, `_force_immediate_constraints` | Preflight + cloud-authored create-by-pk + immediate constraints (2026-08-19) |
> | Evidence | `apps/siteconfig/views_sync_center.py::sync_center_status` + `_sync_live_panel.html` | Live link/cadence, run history, and the **records that landed** with direction |
>
> ### Non-negotiables. Violating any of these is a regression, not an upgrade.
>
> 1. **Do not make everything Last-Write-Wins.** Generic blueprints say LWW everywhere; this
>    platform deliberately does not. Money is cloud-authoritative, marks are down-only, and
>    `ONLINE_REQUIRED` domains (credentials, lifecycle, payment settlement) never travel the
>    sync rail at all. A stale appliance must never be able to move a salary, reopen a locked
>    year, grant a permission, or overwrite a mark. Every new entity gets an explicit
>    `POLICIES` row or an explicit `_LWW_SAFE_ENTITIES` entry — the registry fails **closed**
>    on purpose.
> 2. **Do not append a node id to a business identifier to dodge a unique constraint.**
>    `INV-2026-001-CAMPUS_WEST` is a corrupted invoice number, not a resolved conflict. A
>    natural-key collision on a human-meaningful identifier is a conflict for a human.
> 3. **Do not stall writes to take a batch.** A school is using the appliance while it syncs.
>    Snapshot by cursor/id range; never block the application's write path.
> 4. **Do not convert the platform to UUID primary keys as a side quest.** The appliance is a
>    **pk-preserving clone**, and rows created offline carry a `client_offline_id` anchor —
>    that is this platform's answer to key collision and it is already load-bearing across 15
>    entities. If you believe UUIDs are still required, write the migration plan and the
>    cutover risk as a document and stop; do not start it inside another task.
> 5. **A green local test suite is not evidence.** Tests run on SQLite; production is
>    PostgreSQL, where Django emits every FK as `DEFERRABLE INITIALLY DEFERRED` so violations
>    surface at COMMIT and no per-row savepoint can catch them. Anything constraint-shaped
>    must be proven against Postgres semantics explicitly.
> 6. **Never let one bad row cost the cycle, and never let a skipped row be invisible.** Those
>    are the two halves of the same failure: a wedge, or a silent divergence that reads green.
>
> ### The gaps, in priority order. Each has an acceptance test.
>
> **G1 — Deletions do not propagate at all.** — **DONE (2026-08-20).** `apps/sync_engine/tombstones.py` + `SyncTombstone` + `sync_services.apply_deletes`; tombstones ride the existing rail as `op="delete"` rows. Implemented as a `post_delete` TOMBSTONE TABLE rather than the `is_deleted` columns this brief originally proposed — see *Why tombstones, not soft-delete columns* below. The delta is built by scanning
> `filter(updated_at__gt=since)`. A row **deleted** on either side leaves no row to scan, so
> the other side keeps it forever: a withdrawn student stays enrolled on the appliance, a
> revoked invoice stays payable. This is the largest correctness hole in the engine.
> Introduce soft deletion (`is_deleted` + `deleted_at`) on the synced entities, make it ride
> the existing rail, and give it **delete-dominance** against a concurrent edit — but route it
> through `policy_registry`, because a delete on a money or grade entity is a governance act
> and must be cloud-authoritative like every other write to those entities.
> *Accept when:* a row soft-deleted on the cloud disappears from the appliance within one
> cycle; a row soft-deleted on the appliance is refused for `ONLINE_REQUIRED` entities and
> propagates for master data; and a delete racing an edit resolves identically regardless of
> which side is asked first.
>
> **G2 — The delta can miss a change entirely.** — **DONE, with a stated bound (2026-08-20).** `models.get_sync_cursor_for_request` re-asks from behind the cursor; `push_ledger` keeps the re-ask from costing bandwidth. A transaction open LONGER than the overlap can still slip through — the honest limit, asserted by a test. A true sequence column is still the complete answer and still costs a migration on fifteen live tenant tables. `updated_at`-scanning has two holes a real
> transactional outbox does not: two writes inside the same clock tick collapse to one
> observable state, and a write whose transaction commits *after* a concurrent cycle read the
> high-water is skipped and never re-offered (the cursor has already moved past its
> timestamp). Evaluate a monotonic per-school change sequence (a `BIGSERIAL`/sequence column
> or a real outbox table written in the same transaction as the business row) and cursor on
> **that**, not on wall-clock time. Note the appliance and cloud clocks are independent — this
> also removes the engine's remaining dependence on them agreeing.
> *Accept when:* a test that commits a write concurrently with a cycle proves the write is
> still delivered, and a test that writes twice within one clock tick proves both are
> observable.
>
> **G3 — Files never sync.** — **DONE (2026-08-20).** `apps/sync_engine/file_manifest.py`, `file_sync.py`, `apps/api/sync_files_api.py`, `SyncFileTransfer`, `manage.py edge_sync_files`. Resumable by durable offset, sha256-verified before commit, budget-bounded, and on its own command so it can never delay a data cycle. `_derive_sync_fields` drops every `FileField` — correctly, since
> a bundle carries column values and a synced path would dangle. The consequence is that
> student photos, scanned report cards, and payment proofs simply do not exist across the
> boundary. Build a separate resumable pipeline: a `file_sync_queue` keyed by SHA-256, chunked
> upload with resume, hash verification before marking done, and a bounded local cache on the
> appliance. Keep it **off** the row rail so a large upload can never delay or fail a data
> cycle.
> *Accept when:* a 50 MB attachment survives three simulated connection drops and lands with a
> matching hash, while data cycles continue uninterrupted throughout.
>
> **G4 — No schema-version handshake.** — **DONE (2026-08-20).** Per-APP migration heads exchanged in `X-RMC-Sync-Schema-Head`; the cloud withholds only the entities owned by an app the box is behind on and names the skew in `X-RMC-Sync-Schema-Advice`. Degrades to a compatible subset, never refuses a whole cycle. An appliance running last month's build can receive a
> bundle referencing a column it does not have. Add a version exchange as the first step of
> every cycle: the appliance sends its migration head; the cloud refuses with a specific,
> actionable status when the appliance is behind, and **degrades to a compatible entity subset**
> rather than refusing everything outright — a school with an out-of-date box must still get
> its attendance through. Surface "update required" in the Sync Center with the version delta.
> *Accept when:* a simulated version skew produces a named, actionable operator message and
> zero applied rows for the incompatible entities only.
>
> **G5 — Conflicts are recorded but not resolvable.** — **DONE (2026-08-20), and it was worse than "not resolvable": it was a BYPASS.** "Keep client" wrote the value the rail had just refused, ignoring per-field direction entirely. `conflict_actions.may_resolve` now gates it on the same authority a direct write needs, `_client_updates_for` strips cloud-governed columns, and the review screen shows an aligned field-by-field comparison with a recorded reason. `SyncConflict` rows accumulate with no
> operator path to a decision. Build the side-by-side resolution surface — the two versions,
> field by field, with which side and when — plus **Keep local / Keep cloud / Edit**, and a
> `Skip & log` dead-letter valve so one structurally broken row can never block the queue
> behind it. Every action is audited with who and why. Respect authority: a protected entity's
> conflict may only be resolved by someone who could have made that write directly.
> *Accept when:* an operator with no database access can clear a conflict end to end, and the
> audit row names them.
>
> **G6 — Cloud→box latency is poll-bound (~15s).** — **DONE (2026-08-20).** `apps/api/sync_changes_api.py` long-poll + `change_beacon` + `manage.py edge_sync_watch`. Carries no row data; the cadence remains a complete fallback. The appliance is behind NAT so the cloud
> cannot call it. Implement a long-poll changes feed (the CouchDB `_changes` pattern): the
> appliance holds a request open ~25s and the cloud answers the instant a change exists.
> Works through NAT on plain HTTP, and collapses cloud→box to ~1s without a persistent socket.
> Keep the existing cadence as the fallback when long-poll is unavailable.
> *Accept when:* a cloud write is observable on the appliance in under two seconds, and
> killing the feed mid-flight degrades to the current cadence with no lost rows.
>
> **G7 — Prove convergence, do not assert it.** — **DONE, with its limits stated (2026-08-20).** `apps/sync_engine/convergence_harness.py` + `manage.py verify_edge_sync_convergence` (always rolled back, safe against a live box). It proves the PROTOCOL converges against one real database and a modelled peer; it does NOT prove two independent Postgres databases agreeing, which is the one thing a single-database suite cannot show. Build a repeatable harness that runs a real
> appliance and a real cloud through: a clean sync, a 14-day outage with writes on both sides,
> a restore, a mid-bundle connection drop, a power cut between apply and cursor advance, a
> clock skewed 10 minutes, and a duplicate/replayed bundle. After each, assert **both sides
> hold identical state** for every synced entity, and that money/grade/permission invariants
> were never violated in either direction. This harness is the deliverable that makes "no
> errors allowed" a measurable claim rather than an aspiration.
>
> ### Security posture — **replay defence DONE (2026-08-20)**
>
> `apps/sync_engine/replay_guard.py` + `SyncBundleReceipt`: every bundle carries a random nonce inside the SIGNED header, and a nonce already seen for that school is refused. mTLS for appliance identity remains open (it is an infrastructure change, not a code one).
>
> Current: HMAC-signed bundles over HTTPS with a bearer edge credential. Add replay defence
> (a nonce or a rolling timestamp window — a signature alone does not stop a captured bundle
> being sent twice), and evaluate mTLS for appliance identity. Do **not** weaken the existing
> school-binding check in `verify_and_parse_bundle`; it is what stops one school's bundle
> applying to another.
>
> ### How to report
>
> For every gap: what you found by running it, what you changed, the test that failed before
> and passes after, and the measured before/after. State plainly what you did **not** do and
> why. If a fix would require a migration on a live tenant, say so and give the rollback.

---

## Why this brief rejects parts of the standard blueprint

A generic offline-first blueprint is right about the shape (hub-and-spoke, edge-initiated,
outbox, high-watermark, quarantine, operator UI) and wrong about three specifics that matter
here, because it assumes a greenfield system with no authority model:

- **LWW as the universal rule.** Fine for a contact phone number, catastrophic for a fee
  balance or a published mark. This platform's per-entity policy registry is strictly stronger
  and must survive the upgrade.
- **UUID primary keys everywhere.** The correct default for a new system; an enormous,
  risk-bearing migration for one with 15 synced entities already converging on pk-preserving
  clones plus `client_offline_id` anchors.
- **Appending a node id to break a unique constraint.** Silently corrupts human-meaningful
  identifiers. Invoice numbers are read aloud to parents.

What the blueprint is right about, and this engine genuinely lacks, is **G1 (deletes)**,
**G3 (files)**, **G4 (schema guard)** and **G5 (conflict UI)**. Those, plus the outbox
sequencing in **G2**, are the real work.


---

## What shipped (2026-08-20)

Executing this brief closed all seven gaps plus replay defence, and turned up four
defects that were not on the list — three of them found only by RUNNING the new paths.

| Area | Where it lives |
|---|---|
| Deletion propagation | `sync_engine/tombstones.py`, `SyncTombstone`, `sync_services.apply_deletes` |
| Delete dominance | tombstone index consulted on all three inbound paths, resolved by timestamp |
| Cursor overlap + sent memory | `models.get_sync_cursor_for_request`, `sync_engine/push_ledger.py` |
| File transfer | `sync_engine/file_manifest.py`, `file_sync.py`, `api/sync_files_api.py`, `SyncFileTransfer` |
| Schema handshake | `schema_guard.{local_migration_heads,compare_heads,describe_skew}`, download view |
| Conflict authority | `conflict_actions.{may_resolve,_client_updates_for,field_comparison}` |
| Long-poll feed | `api/sync_changes_api.py`, `sync_engine/change_beacon.py`, `edge_sync_watch` |
| Replay defence | `sync_engine/replay_guard.py`, `SyncBundleReceipt` |
| Convergence harness | `sync_engine/convergence_harness.py`, `verify_edge_sync_convergence` |

---

## G8: the parity seal (2026-08-21)

Everything above is a guarantee about the JOURNEY — the cursor is honest, the bundle is
signed, a replay is refused, a deletion does not come back, and the harness drives real
bundles through the real apply path. What none of them do is ask the other side what it
actually HOLDS. The harness drives ONE database against a modelled `Mirror` and says so in
its own docstring.

So a row that went missing for a reason the protocol does not model — a restore from an
old dump, a hand-run `DELETE` on the box, an apply that failed on a column the handshake
had not yet learned to withhold — stayed missing forever. An incremental delta only ever
offers what changed since the cursor, and **an absent row has no `updated_at` to be
greater than anything.** Every status screen read green while it was gone.

| Area | Where it lives |
|---|---|
| Per-entity digest | `sync_engine/parity.py` |
| Handshake (cloud half) | `api/sync_bundle_api.py::_parity_handshake` + `X-RMC-Sync-Parity*` |
| Sweep + repair (box half) | `sync_engine/sync_runner.py::_flush_drifted_entities` |
| Operator command | `verify_sync_parity` (read-only; exit 1 on drift, so it can gate a cutover) |

### Four decisions worth not relitigating

**Digest the RAIL FIELDS, never `updated_at`.** `updated_at` is `auto_now`, so when the
box applies a row the cloud sent, the local save stamps a new timestamp: two perfectly
converged sides hold different `updated_at` for the same row, permanently. A digest over
it reports drift on every row on the first cycle and never stops, and a monitor that is
always red is one nobody reads. Echo-suppression exists precisely because this skew is
normal.

**Identity is `client_offline_id` when set, else the pk.** A cloud-authored row is created
on the box by `_create_from_cloud_pull`, which PRESERVES the operator's pk; a box-authored
row is upserted by `(school, client_offline_id)` and the cloud mints its own pk. Keying on
pk alone reports every offline-created row as drift forever; keying on the anchor alone
collapses every cloud-authored row onto one empty key.

**Hash one school's rail data, not "the database".** The two deployments do not have the
same database — the cloud is schema-per-tenant (`USE_DJANGO_TENANTS=1`), a sovereign box
is shared-DB + RLS with `SINGLE_TENANT`. Table sets, sequences and `django_migrations` all
differ legitimately. Scoping by the same `school=` kwarg the delta builder uses is what
makes this one piece of code correct on two different topologies.

**Repair per entity, not by rewinding the cursor.** The cursor is per
`(school, direction)`, so the existing healing move replays the ENTIRE corpus to fix one
table — a bill on a metered link and an hour on a large school. Parity already knows which
entity is wrong, so the repair re-pulls exactly that one with `since=None`, over the same
endpoint, signature and idempotent apply as any other pull. One entity per request, for
partial progress: a repair runs on the link that was unreliable enough to lose rows in the
first place, so a drop mid-repair should cost the last entity, not all of them. (Not for
the row cap — `RMC_SYNC_BUNDLE_MAX_ROWS` is enforced on the upload receiver, not the pull;
the existing full-resync path depends on that.)

### What it costs

A sweep READS EVERY ROW of every entity, so it is rate-limited independently of the sync
cadence (`RMC_SYNC_PARITY_INTERVAL_SECONDS`, default 1h; at a 20-second tick an
unthrottled sweep is a continuous table scan on a mini-PC). A box that sends no digest
costs the download endpoint one dictionary lookup, and the cloud digests only the entities
the box actually reported. Measured against the dev corpus: 15 entities, 448-byte header.

`RMC_SYNC_PARITY_MAX_FLUSH_ENTITIES` (default 3) caps auto-repair per cycle — a box that
has lost its database reports everything as drifted, and flushing all of it at once is a
full corpus re-pull wearing a repair's clothes. Above the cap the cycle repairs the worst
few and NAMES the rest as still drifted; a silent truncation would read as "all fixed".

Entities withheld by the G4 schema handshake are excluded from the parity answer: there
the difference is already explained and re-pulling would not fix it.

### Why tombstones, not the `is_deleted` columns this brief first proposed

The brief said soft deletion on each synced entity. Building it showed that to be the
worse design here, for three concrete reasons:

* it needs a migration on fifteen live TENANT business tables, and every existing
  `.delete()` call site in the product would have to be rewritten or the column would
  simply never be set — a silent, partial rollout of the exact guarantee being sought;
* a database CASCADE (deleting a department removes its curriculum links) fires
  `post_delete` for every child but would never set anyone's `is_deleted`, so cascades —
  the most common way rows actually disappear — still would not travel;
* `.delete()` already happens throughout the product. One `post_delete` receiver captures
  all of it, cascades and queryset deletes included, with no change to a single call site.

The cost is honest: tombstones only grow, so `prune_tombstones` trims past the retention
window. And because a wrongly propagated delete destroys data the far side cannot
re-offer, deletion is the only operation here with three guards — policy, a per-bundle
flood cap, and a kill switch.

### Found while building, not on the list

1. **A classroom could not be CREATED across the rail in either direction.** The curated
   field set was `{name, academic_year_id}`, but `Classroom.department` is NOT NULL and
   `code` is a required UNIQUE column. A class created on the cloud in September died on
   the box's create path as a per-row 422 and simply did not exist offline; a class
   created offline could never be pushed up. Only UPDATES worked, which is exactly why it
   went unnoticed — the clone already had every classroom that existed at clone time.
2. **A retried pull manufactured conflicts out of the engine's own writes.** After
   applying a pulled row, this side's `updated_at` is newer than the cloud's. Re-offering
   that row — after any failed cycle, and routinely once the overlap existed — graded the
   apply as a local edit and raised a `SyncConflict`, asking an operator to adjudicate
   between a value and itself. The apply ledger already knew better; it is now consulted.
3. **An identical re-apply still bumped `updated_at`,** re-entering the row into the delta
   in the other direction. Churn the engine manufactured itself.
4. **`Invoice.delete()` is a SOFT delete** for legal traceability. `apply_deletes` calls
   the INSTANCE's `delete()`, never a queryset delete, so the rail cannot overrule a
   model's own deletion semantics — and it then clears the tombstone, because a row that
   still exists must not be treated as buried.

### Still open, deliberately

* **mTLS for appliance identity** — infrastructure, not code.
* **A true monotonic change sequence** (the complete form of G2) — still a migration on
  fifteen live tenant tables; the overlap closes the race for any transaction shorter than
  the window, and the bound is asserted by a test rather than assumed.
* **A two-database convergence drill.** The harness proves the protocol against one
  database. The property it cannot show is deferred-FK behaviour, where SQLite is the
  WEAKER environment — which is precisely how the 2026-08-19 wedge stayed invisible. That
  drill belongs in `docs/EDGE_SYNC_OPERATIONS.md`, run against a real box.
  **G8 narrows this but does not close it.** Parity answers "do the two databases hold the
  same rows" continuously, in production, which is the part the harness structurally
  cannot reach — and `verify_sync_parity --against` makes the drill's final assertion a
  one-line command instead of a manual comparison. What it still does not exercise is the
  deferred-FK behaviour itself: parity compares OUTCOMES, so it reports that a box is
  short of rows without reproducing the constraint timing that lost them.
* **Multi-box relay.** Echo suppression is peer-agnostic, so a hub relaying box A's change
  to box B can suppress it. Not a regression — it predates this work — and the deployment
  model is one appliance per school.

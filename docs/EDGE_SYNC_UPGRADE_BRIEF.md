# Edge↔Cloud Sync: the upgrade brief

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
> **G1 — Deletions do not propagate at all.** The delta is built by scanning
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
> **G2 — The delta can miss a change entirely.** `updated_at`-scanning has two holes a real
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
> **G3 — Files never sync.** `_derive_sync_fields` drops every `FileField` — correctly, since
> a bundle carries column values and a synced path would dangle. The consequence is that
> student photos, scanned report cards, and payment proofs simply do not exist across the
> boundary. Build a separate resumable pipeline: a `file_sync_queue` keyed by SHA-256, chunked
> upload with resume, hash verification before marking done, and a bounded local cache on the
> appliance. Keep it **off** the row rail so a large upload can never delay or fail a data
> cycle.
> *Accept when:* a 50 MB attachment survives three simulated connection drops and lands with a
> matching hash, while data cycles continue uninterrupted throughout.
>
> **G4 — No schema-version handshake.** An appliance running last month's build can receive a
> bundle referencing a column it does not have. Add a version exchange as the first step of
> every cycle: the appliance sends its migration head; the cloud refuses with a specific,
> actionable status when the appliance is behind, and **degrades to a compatible entity subset**
> rather than refusing everything outright — a school with an out-of-date box must still get
> its attendance through. Surface "update required" in the Sync Center with the version delta.
> *Accept when:* a simulated version skew produces a named, actionable operator message and
> zero applied rows for the incompatible entities only.
>
> **G5 — Conflicts are recorded but not resolvable.** `SyncConflict` rows accumulate with no
> operator path to a decision. Build the side-by-side resolution surface — the two versions,
> field by field, with which side and when — plus **Keep local / Keep cloud / Edit**, and a
> `Skip & log` dead-letter valve so one structurally broken row can never block the queue
> behind it. Every action is audited with who and why. Respect authority: a protected entity's
> conflict may only be resolved by someone who could have made that write directly.
> *Accept when:* an operator with no database access can clear a conflict end to end, and the
> audit row names them.
>
> **G6 — Cloud→box latency is poll-bound (~15s).** The appliance is behind NAT so the cloud
> cannot call it. Implement a long-poll changes feed (the CouchDB `_changes` pattern): the
> appliance holds a request open ~25s and the cloud answers the instant a change exists.
> Works through NAT on plain HTTP, and collapses cloud→box to ~1s without a persistent socket.
> Keep the existing cadence as the fallback when long-poll is unavailable.
> *Accept when:* a cloud write is observable on the appliance in under two seconds, and
> killing the feed mid-flight degrades to the current cadence with no lost rows.
>
> **G7 — Prove convergence, do not assert it.** Build a repeatable harness that runs a real
> appliance and a real cloud through: a clean sync, a 14-day outage with writes on both sides,
> a restore, a mid-bundle connection drop, a power cut between apply and cursor advance, a
> clock skewed 10 minutes, and a duplicate/replayed bundle. After each, assert **both sides
> hold identical state** for every synced entity, and that money/grade/permission invariants
> were never violated in either direction. This harness is the deliverable that makes "no
> errors allowed" a measurable claim rather than an aspiration.
>
> ### Security posture
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

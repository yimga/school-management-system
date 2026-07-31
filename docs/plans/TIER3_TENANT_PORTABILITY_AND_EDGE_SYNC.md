# Tier 3 — Full-fidelity tenant portability + edge↔operator sync

Status: **Slices 0-5 DONE + tested** — clone engine; persisting receiver; edge outbox
producer; machine credential + authenticated outbound transport; offline-created
inserts (upsert by client_offline_id); FK id-remapping for new-references-new
(Slice 5 — the honest residual, now closed). Author: platform.
Supersedes the "manual DR export/restore only" gap called out in
`docs/LOCAL_HUB_MODE.md` and the sync verdict in
`finding_sovereign_edge_selfhost_state_2026_07_31` (memory).

## Why this exists

Moving a **running** school (e.g. `gilead-tech`, months of real data) onto an
on-prem mini-PC — and later syncing it back to the cloud operator when the box
gets internet — is blocked on one thing: **there is no full-fidelity way to move
a tenant's data between deployments.** The only built cross-deployment path is
`apps/lifecycle/tenant_dr_snapshot.py`, which is deliberately **config-core only**
(~13 tables: School, users, students, teachers, invoices, payments, academic
config). It does NOT carry attendance, grades, messages, analytics, or payroll.

So the box config work (Tier 1) is done, but the box would arrive **empty of
operational history**. This tier builds the data layer.

## Two distinct operations (do not conflate them)

| | **A. CLONE (move)** | **B. SYNC (ongoing)** |
|---|---|---|
| Purpose | Seed a fresh box with the whole tenant | Reconcile edge ↔ operator over time |
| Target | **Empty** schema/box | **Existing**, independently-mutated tenant |
| Keys | **pk-preserving** (identity move) | natural-key upsert + conflict resolution |
| Direction | one-shot, either way | bidirectional, incremental (deltas) |
| Hard part | completeness + FK ordering | conflict resolution, causality, auth |

**A is tractable now and unblocks the move. B is the harder, staged build.** This
doc's engine implements **A** and defines the payload format **B** will reuse.

## The bundle format (`.rmcbundle`)

Reuses the DR snapshot's proven envelope verbatim (no new crypto):
`apps.lifecycle.tenant_dr_snapshot.encrypt_blob / decrypt_blob / sign_payload /
verify_signature` — Fernet encryption + HMAC-SHA256, **encrypt-then-MAC**, both
keys domain-separated from `SECRET_KEY` mixed with the school id. Fail-closed:
the signature (and the bound school id) is verified BEFORE decrypt/parse/write.

Container (a single JSON file):
```json
{ "format": "rmc-tenant-bundle/1", "school_id": "<uuid>", "sig": "<hmac-hex>",
  "blob_b64": "<base64 fernet(ciphertext) of gzip(json(payload))>" }
```
Inner payload (gzip'd, encrypted):
```json
{ "format": "rmc-tenant-bundle/1", "tenant_slug": "gilead-tech",
  "school_id": "<uuid>", "created_at_iso": "...", "mode": "schema|rls",
  "counts": { "people.studentprofile": 412, ... },
  "tables": { "<app_label>.<model_name>": [ <django json-serialized rows> ] } }
```
Row data is `django.core.serializers.serialize("json", qs)` — the same
type-faithful serializer the DR snapshot uses (dates/decimals/JSON/FK-by-pk/m2m).

## Scoping — the schema boundary does the work

- **Schema-per-tenant (`USE_DJANGO_TENANTS=1`, production):** the tenant's data
  lives in its OWN Postgres schema, so a full export is simply "serialize every
  row of every TENANT_APPS model within the schema" — no per-row filtering, and
  pks are globally meaningful within the target's fresh schema.
- **Shared/RLS (`USE_DJANGO_TENANTS=0`, SQLite/dev, small single-box):** there is
  one schema, so rows are scoped by the model's `school` FK. Models with a direct
  `school` FK export cleanly; models reachable only via a parent are a **known v1
  limitation** in RLS mode (they are fully covered in schema mode) and are logged,
  never silently dropped.

`TENANT_APP_LABELS` is the canonical tenant-app set (mirrors `settings.TENANT_APPS`,
declared as a constant so it resolves in BOTH tenancy modes — `TENANT_APPS` itself
is only defined in the django-tenants settings branch).

## FK ordering on load — deferred constraints, not topological sort

Restore preserves pks into an empty target inside ONE transaction with
`connection.constraint_checks_disabled()` (portable: `SET CONSTRAINTS ALL
DEFERRED` on Postgres, `PRAGMA foreign_keys=OFF` on SQLite), then
`connection.check_constraints()` at the end. This makes load **order-independent**
and handles self- and circular FKs without a fragile dependency sort. Re-import is
idempotent: a colliding pk is an UPDATE of the same identity.

## What the bundle does NOT carry (and why that's correct)

- **School / SchoolMembership / entitlements / RuntimeDefaults / blueprints** —
  operator-authoritative PUBLIC-schema rows. On the box these are created by
  `provision_sovereign_school` (Tier 1c) + the DR snapshot's config-core; the
  operational bundle layers on top. Keeping them out avoids fighting the
  public-vs-tenant authority split.
- **Redis/WAL transient state** — regenerated, never authoritative.

## Roadmap — slices (each shipped + tested independently)

- **Slice 0 (this change):** `tenant_portability.py` export/import engine +
  `export_tenant_bundle` / `import_tenant_bundle` commands + round-trip test.
  → unblocks the CLONE / move.
- **Slice 1 (DONE):** make `apps/api/sync_bundle_api.py::SyncBundleUploadView`
  actually PERSIST. It used to verify the signed bundle then return
  `{ok, imported: <count>}` **without writing**. It now routes the verified rows
  through `apps.api.sync_services.apply_changes` — the SAME tested path the online
  `DeltaSyncAPI` uses — so writes land and per-record conflicts create `SyncConflict`
  (updated_at check) for Sync Center resolution. **Correction to the original plan:**
  the receiver takes a *delta* bundle (NDJSON rows, `apps.sync_engine.delta_bundle`),
  NOT the full-fidelity `.rmcbundle` clone container — so it routes into the delta
  apply path, NOT `import_tenant_bundle` (those are two different payload formats:
  clone = whole-tenant seed, delta = incremental row changes). Also fixed a latent
  bug: `delta_bundle.verify_and_parse_bundle` compared school ids with `int()`, which
  500'd on the platform's UUID `School.pk`; the binding now compares as strings
  (backwards compatible with integer ids). 5 receiver tests + the 2 delta-bundle
  backwards-compat tests green.
- **Slice 2 — capture half (DONE):** `export_edge_delta_bundle` management command
  packages a tenant's records changed since a cursor (`--since`) into a signed delta
  bundle — exactly what the Slice-1 receiver consumes. It syncs **UPDATES to records
  that already exist upstream**, which is coherent precisely because Slice 0's clone
  is **pk-preserving** (a row edited on the box carries the same pk on the operator).
  Semantics: last-writer-wins per record (whole allowed-field snapshot + `updated_at`;
  the receiver applies only when the bundle is newer, else records a `SyncConflict`).
  Entity set + field allowlist are read from `apps.api.sync_services` (the same SOT
  the receiver validates against) so producer and applier never drift. **Correction
  to the original plan:** the operator's `apply_changes` is UPDATE-only, so this does
  NOT handle brand-new edge rows ("append-only" inserts like a new enrollment) — that
  is new-row upsert + reconciliation in Slice 4. Tested by a producer→receiver
  round-trip (edge changes applied onto a rewound stale copy) + cursor-exclusion +
  unknown-entity guard.
- **Slice 2 — transport half (folds into Slice 3):** the authenticated HTTP POST of
  that bundle to the operator's `/api/v1/sync/bundle/upload/` when connectivity
  returns (queue-and-forward) needs the per-box **machine credential** to
  authenticate, so it is built together with Slice 3 rather than before it.
- **Slice 3 — identity + transport (DONE):** the per-box **machine credential** +
  the authenticated upstream POST, edge-initiated / outbound-only.
  - Credential reuses `accounts.OfflineCapabilityToken` (sha256-fingerprinted,
    revocable via the token AND its `DeviceRegistration`, with an expiry) tagged
    `EDGE_SYNC_SCOPE` so an ordinary mobile offline token can't drive server↔server
    sync. **No new model / migration** — a sovereign box registers as a device.
    Bound to a service user that can operate on the school (the operator's apply runs
    AS that user, so its permissions gate the writes). Minted by
    `mint_edge_credential` (operator).
  - `EdgeCredentialAuthentication` (DRF) on `SyncBundleUploadView`: resolves the
    `Bearer` credential → `(user, school)`, scopes the request, and falls through to
    Session/JWT when the header isn't an edge credential, so online uploads still work.
  - `post_edge_outbox` (box) builds the Slice-2 bundle and POSTs it with the
    credential; **queue-and-forward is idempotent** — the cursor advances ONLY on a
    successful post, so an offline run keeps the cursor and the next run re-sends the
    same window (LWW makes a re-send harmless); the failed bundle is also dropped in
    an outbox dir for manual replay.
  - **Reachability solved by direction:** the box calls OUT to the operator, so the
    operator never needs to reach a box behind a private LAN — no inbound tunnel. The
    core (`apps/sync_engine/edge_outbox.py`) shares one bundle-builder with Slice 2.
    10 tests (credential auth accept/reject-missing/garbage/revoked/non-scope through
    the receiver; mint↔resolve; poster success-advances / offline-keeps-cursor-and-
    queues / rejection-raises-and-keeps-cursor / nothing-to-send).
- **Slice 4 — offline-created inserts (DONE):** sync records CREATED offline on the
  box, via **natural-key upsert by `(school, client_offline_id)`** — never by pk.
  - Migration `academics/0073` adds `client_offline_id` (+ partial-unique
    `(school, client_offline_id)`) to `Attendance` and `Classroom`, matching the
    existing field on `StudentProfile`/`TeacherProfile`.
  - **Why not by pk:** these entities use integer autoincrement pks, so a box-local pk
    for a new record can collide with a *different* operator record. The receiver
    therefore **splits** rows: those with an empty `client_offline_id` are cloned
    records (pk stable across the clone) → update-by-pk (`apply_changes`); those with a
    non-empty `client_offline_id` are box-created → `apply_edge_inserts`, which upserts
    by `(school, client_offline_id)` under a per-row savepoint (one bad row never rolls
    back the batch) and is admin-gated.
  - **FK safety:** a foreign key that points at *another* insert-row's untrustworthy
    local pk is dropped, so a new record can only link to already-present (cloned,
    pk-stable) records; if that FK was required, the row fails cleanly and is reported
    (never silently mis-linked). Phantom allow-list fields are ignored; a row that
    can't be constructed (e.g. a `Classroom`, which needs `department` + a unique
    `code` not carried in the sync field set) is reported failed, never dropped.
  - **What works cleanly today:** new **students** (no required FK to another new
    record — the primary new-enrollment case) and **attendance/classroom edits or
    inserts that reference already-cloned records**. 7 tests.
  - **Superseded by Slice 5:** the "full FK id-remapping so a new record can reference
    *another* new record" was deferred here and is now implemented — see Slice 5.
- **Slice 5 — FK id-remapping for new-references-new (DONE, the honest residual):**
  the case Slice 4 deferred — a record created offline that references *another*
  offline-created record in the same bundle (e.g. **attendance for a brand-new
  student**, or a new student assigned to a new classroom).
  - **How:** `apply_edge_inserts` now processes rows in **dependency order**
    (`_insert_dependency_order` — a Kahn topological sort over the `_INSERT_FK_TARGET`
    FK graph, so referents are created before dependents: classroom → student →
    attendance), records each new row's freshly-assigned **operator pk** in a
    `(entity_type, box_local_pk) → operator_pk` map, and **remaps** a dependent FK
    onto that operator pk instead of dropping it. Results are returned in the caller's
    **original** bundle order regardless of the internal processing order.
  - **Still fail-clean:** if a referent could not be created (or isn't in the bundle),
    the FK is still dropped — so the dependent row links only to real records or, if the
    FK is required (e.g. `Attendance.student`), fails cleanly and is reported (422),
    never mis-linked to the box's local pk. A new `Classroom` remains uninsertable via
    the sync field set (needs `department` + a unique `code`), so a student referencing a
    new classroom drops that (nullable) FK and still lands.
  - **Safety of the split is unchanged:** a pk is only remapped when it belongs to a NEW
    (insert) row in the same bundle (`new_local_pks`); a reference to a **cloned**
    (pk-stable) record is passed through verbatim, because the box preserves cloned pks
    and assigns fresh autoincrement pks above them, so a new-row local pk can never
    collide with a cloned pk on the box. 3 new/updated tests (remap, order-independence,
    fail-clean fallback) → **10 edge-insert tests**.
  - **Not attempted (correctly out of scope):** the richer CRDT/policy conflict
    machinery (`policy_registry.py`, `conflict_resolver.py`) for concurrent divergent
    edits — Slice 5 is deterministic id-reconciliation, not multi-writer merge. LWW +
    `SyncConflict` (Slices 1-2) remains the update-conflict story.

## Security notes

- Fail-closed: verify signature + bound school id before any decrypt/write.
- The bundle is PII-dense (student/teacher records, ledger). It is ciphertext at
  rest exactly like the DR snapshot; treat `.rmcbundle` files as secrets in
  transit (the Slice-1 upload is authenticated + TLS to the operator).
- Import is transactional and rolls back on any constraint failure (no partial
  tenant).

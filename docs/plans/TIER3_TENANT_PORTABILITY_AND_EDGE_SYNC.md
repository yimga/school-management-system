# Tier 3 — Full-fidelity tenant portability + edge↔operator sync

Status: **IN PROGRESS** (Slice 0 = this doc + the portability engine; Slice 1 = the
persisting bundle receiver — both DONE + tested). Author: platform.
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
- **Slice 2:** edge **outbox poster** — a hub-side command/task that packages an
  incremental delta (start with append-only domains: attendance, grades) into a
  bundle and POSTs it to the operator when connectivity returns. One-way, highest
  value, no conflict resolution needed for append-only rows.
- **Slice 3:** edge **identity + reachability** — a per-box machine credential the
  operator issues (so the hub can authenticate its upstream POST), plus the
  operator-managed tunnel/registration for a box behind a private LAN.
- **Slice 4:** **incremental deltas + reconciliation** — change-tracking
  (updated_at / an outbox cursor), natural-key upsert on the operator side, and
  conflict resolution wired onto the existing CRDT/policy machinery
  (`apps/sync_engine/policy_registry.py`, `conflict_resolver.py`,
  `crdt_wire_protocol.py`). This is operation **B** and the largest slice.

## Security notes

- Fail-closed: verify signature + bound school id before any decrypt/write.
- The bundle is PII-dense (student/teacher records, ledger). It is ciphertext at
  rest exactly like the DR snapshot; treat `.rmcbundle` files as secrets in
  transit (the Slice-1 upload is authenticated + TLS to the operator).
- Import is transactional and rolls back on any constraint failure (no partial
  tenant).

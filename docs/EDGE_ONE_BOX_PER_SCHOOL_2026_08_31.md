# One box per school — the recorded decision (G5, 2026-08-31)

## The finding, verified

Two sovereign boxes bound to one school do not fail. They half-work, and the half that
does not work is invisible.

Traced through the deployed call path, not inferred:

1. Box A pushes a changed row. The cloud applies it through
   `apps/api/sync_services.py::_apply_changes_inner` with `sync_origin="edge-push"`.
   Every applied row calls `record_sync_apply(school_id, entity_type, pk, updated_at,
   origin)` (`apps/api/sync_services.py:1507`, `:1572`, `:1785`, `:2119`).
2. That writes a `SyncApplyLedger` row. Its unique key is
   `(school, entity_type, local_pk)` (`apps/sync_engine/models.py:64-68`). There is no
   device column, and the `origin` field states of itself: *"Observability only; the
   suppression logic does not depend on it."*
3. Box B pulls. The cloud serves it from `SyncBundleDownloadView.get`
   (`apps/api/sync_bundle_api.py:593`) → `build_edge_delta_bundle` →
   `build_edge_delta_rows` (`apps/sync_engine/edge_outbox.py:58`).
4. `build_edge_delta_rows` loads `sync_echo_updated_at_map(school, entity_type)`
   (`apps/sync_engine/models.py:679`) — filtered by school and entity only — and drops
   any candidate whose current `updated_at` still equals the recorded value
   (`edge_outbox.py:113-115`).

Box A's row matches. It is dropped as an "echo" of a write box B has never seen. No
exception, no conflict, no counter: an absence.

**CONFIRMED.** Reproduced end to end in
`apps/sync_engine/tests/test_one_box_per_school_2026_08_31.py::EchoStarvationTests`.

Two consequences that make it worse than "a row arrives late":

* **A full pull does not rescue it.** `since=None` is what a full-resync directive and a
  parity-driven repair both fall back to, and echo-suppression runs before the cursor
  filter. `build_edge_delta_bundle` applies the parity `keep_buckets` narrowing *after*
  `build_edge_delta_rows` has already dropped the row (`edge_outbox.py:204-217`), so the
  repair path cannot reach it either. Parity would report the entity as permanently
  drifted and never converge it.
* **It self-heals for exactly the rows nobody cares about.** Echo-suppression compares
  provenance, so any later local edit moves `updated_at` off the recorded value and the
  row ships. Actively edited records recover; records written once and left alone — a
  student's admission number, a closed invoice, an archived classroom — stay missing.

`EdgeFleetState.school` being a `OneToOneField` (`models_fleet.py:36`) and
`EdgeSyncCursor` being unique on `(school, direction)` are the same limitation in two
more places. The cursor is the least of them in practice: it lives in the BOX's own
database and the cloud is stateless about it (the box sends `since` as a query
parameter), so two boxes do not in fact share one cursor row. The ledger is the real
defect.

## The decision

**(b) — refuse the second binding, loudly.** Implemented 2026-08-31.

**(a) — support multi-box properly — was considered and NOT taken in this pass.** It is
the better end state and is written up below so the next person starts from the analysis
rather than from scratch.

### Why (b) now

A hard refusal at install time is strictly better than a configuration that diverges
silently for months. The refusal reaches the technician standing at the box, at the
moment the mistake is made, in the same session that would otherwise have "succeeded".

### What (b) does

`apps/sync_engine/pairing_service.py` gains two functions —
`bound_edge_device_ids(school)` and `adoption_conflict(school, device_id)` — enforced at
**four** gates, because each closes a different way in:

| Gate | Closes |
|---|---|
| `start_pairing` | the technician learns at the box, immediately, and no request row is written |
| `approve_pairing` | a request opened while the school was unbound cannot be approved after another box binds |
| `collect_pairing` | a **claim ticket auto-approves inside `start_pairing`** and never passes through `approve_pairing` — so the credential mint itself must be fail-closed |
| `mint_claim_ticket` | pre-authorising an adoption of an already-bound school is pre-authorising what the other three refuse |

**Ground truth is the credential, not the pairing audit trail.** `bound_edge_device_ids`
asks the same question `resolve_edge_credential` asks — a live (unexpired, unrevoked)
`EDGE_SYNC_SCOPE` token on an unrevoked device — because a box installed before pairing
existed was bound by `manage.py mint_edge_credential` and has no `EdgePairingRequest`
row at all. That population is the one most likely to be handed a second box.

**A blank device id is never an identity.** `EdgePairingRequest.device_id` is
`blank=True`, and `mint_edge_credential` derives `edge-<slug>` when a box sends nothing —
so two anonymous boxes would look identical if the check compared what was *sent*. It
compares what is *bound*, and `""` matches nothing.

**The release path is revocation**, which the product already has as an explicit, audited
operator action (`/portal/super/devices/`, `apps/portal/views_device_governance.py`), and
which `mint_edge_credential` already honours by refusing to re-arm a revoked device. An
expired credential also releases the school: a binding is a live credential, not a
historical fact.

**Same-box re-pairing stays possible.** A box that lost its own database is the same box;
identity, not novelty, is what is checked.

## What (a) would cost

Not a sketch — the specific edits, so the estimate is arguable rather than a feeling.

1. **A device dimension on `SyncApplyLedger`.** Add `device_id` (char, indexed) and
   change the unique key from `(school, entity_type, local_pk)` to
   `(school, device_id, entity_type, local_pk)`. This is a migration on a SHARED/public
   table, so it is one migration, not fifteen — materially cheaper than the tenant-table
   migration `get_sync_cursor_for_request` and `SyncTombstone` both decline. The row
   count multiplies by the number of boxes, which is the honest storage cost.
2. **Every writer must know which device it is writing for.** `record_sync_apply` is
   called from four sites in `_apply_changes_inner` / `apply_edge_inserts`, which take
   `sync_origin` but not a device. The bundle header already carries `device_id`
   (`export_delta_bundle(..., device_id=...)`), and `EdgeCredentialAuthentication`
   resolves the token's `DeviceRegistration` — so the identity exists at the receiver and
   has to be threaded down through `apply_changes` to the ledger write.
3. **Every reader must ask for a device.** `sync_echo_updated_at_map(school, entity_type)`
   becomes `(school, device_id, entity_type)`, and `build_edge_delta_rows` needs the
   identity of the box it is building FOR — which today it does not take at all.
4. **The suppression predicate changes meaning.** Today "sync wrote this" is one fact per
   row. With devices it becomes "this box's own write", which is the correct semantics
   and is what makes box B receive box A's row. Worth stating: the cloud must NOT
   suppress a row for box B merely because box B once pushed it, if box A has since
   changed it — the existing `updated_at` equality already handles that, but it needs
   re-deriving rather than assuming.
5. **`EdgeFleetState.school` `OneToOneField` → `ForeignKey`,** plus a unique
   `(school, device_id)`, plus every reader of `school.edge_fleet_state` (a reverse
   one-to-one accessor) rewritten. The fleet console renders one row per school today.
6. **`EdgeSyncCursor`** needs `(school, device_id, direction)` only if the CLOUD ever
   starts keeping cursors; it does not today (the box sends `since`), so this is the one
   item on the list that may be no work at all. Confirm before budgeting it.
7. **Parity** is per-school and per-entity and would need to be asked per-device, or it
   will report drift for whichever box it is not looking at.

Items 2 and 3 are owned by another agent in this pass (`apps/sync_engine/models.py`,
`apps/api/sync_services.py`), which is the immediate reason (a) was out of scope here.

**Do not half-implement (a).** A ledger with a device column that some writers populate
and some do not is worse than no column: the suppression predicate would then be
device-aware for some rows and device-blind for others, and the resulting starvation
would be intermittent instead of total — which is harder to find, not easier.

## How to tell this document is out of date

`EchoStarvationTests` in
`apps/sync_engine/tests/test_one_box_per_school_2026_08_31.py` pins the starvation
itself. If (a) ever lands, those tests SHOULD start failing. That is the signal that the
refusal has become unnecessary, and it is the right way to find out.

# Edge sync — how it actually runs, and how to get a stale box caught up

Written 2026-08-17 after a reported "sync from the cloud fails consistently". Read the
direction section first; most confusion about this rail comes from expecting it to work in a
direction it cannot.

## Direction: the box always calls out

A sovereign box sits on a school's private LAN behind NAT. **The cloud can never open a
connection to it.** Every transfer is box-initiated:

```
box  --POST /api/v1/sync/bundle/upload/-->  cloud     (push local changes up)
box  --GET  /api/v1/sync/bundle/download/-> cloud     (pull cloud changes down)
```

Consequences that are not optional:

- A "Sync now" button **on the cloud** cannot reach the box. It used to be rendered on every
  deployment, so pressing it on the cloud failed 100% of the time and wrote a red
  `EdgeSyncRun` row — which is what "Last sync failed / Sync is not enabled on this
  deployment" in the Sync Center was reporting. The cloud panel now offers **Queue full
  resync** instead, which is a request the box collects on its next call-out.
- `RMC_EDGE_SYNC_ENABLED` being **off on the cloud is correct**, not a misconfiguration. Only
  the box sets it.

## Auto-sync: what makes it run

The box syncs itself; no cron setup is required. Every automatic trigger converges on
`edge_scheduler.run_edge_sync_now`, which is flag-gated, never raises, and resolves the
box's own school with no arguments:

| Trigger | Where |
|---|---|
| In-process periodic job (fires on the `/health/` tick) | `apps/platform_runtime/periodic.py::_maybe_register_edge_sync_job` |
| Celery beat `edge-sync-cycle` → task `sync_engine.edge_sync_cycle` | `config/settings.py` `CELERY_BEAT_SCHEDULE` |
| Boot reconcile on container start | `deploy/selfhost/entrypoint.web.sh` (guarded by the flag) |
| Manual | `python manage.py edge_autosync` |

Cadence: `RMC_EDGE_SYNC_INTERVAL_SECONDS`, default **180s**, floored at 60s.

There is deliberately **no connectivity pre-probe**. An attempt made while offline is a
cheap no-op that leaves both cursors where they were and retries on the next tick, so the
first tick after the network returns reconciles both directions. A probe would add a way to
be wrong (a probe that succeeds while the real request fails, or vice versa) and buy nothing.

### Required box configuration

| Setting | Purpose |
|---|---|
| `RMC_EDGE_SYNC_ENABLED=1` | Turns the rail on. Off ⇒ every path is a hard no-op. |
| `RMC_EDGE_OPERATOR_BASE` | Cloud base URL (falls back to `RMC_HUB_BASE_URL`). |
| `RMC_EDGE_CREDENTIAL` | The minted edge machine credential (see `mint_edge_credential`). |
| `RMC_EDGE_SCHOOL_SLUG` | Only needed if the box serves more than one active school. |

If the rail is on but unconfigured, cycles record `push failed` / `pull rejected` with the
reason — check `EdgeSyncRun` rows in the Sync Center rather than guessing.

## Why a stale box used to stay stale

Two defects, both fixed 2026-08-17, both provable by running the cycle
(`apps/sync_engine/tests/test_edge_sync_backlog_paging_2026_08_17.py`):

1. **The push deadlock.** The runner built ONE bundle containing *every* row (`since=None`)
   and POSTed it whole. `SyncBundleUploadView` caps a bundle at
   `RMC_SYNC_BUNDLE_MAX_ROWS` (default **500**) and rejects an oversized one with
   `400 bundle_too_large`, applying **nothing**. So the further behind a box was, the more
   certain every future attempt was to fail — identically, forever. A box that had never
   synced could essentially never start.

2. **No cursor.** `since=None` in both directions, and the `X-RMC-Sync-High-Water` header the
   download endpoint already returns was discarded. Every 180s tick re-scanned and re-shipped
   the whole corpus. (The `post_edge_outbox` / `pull_edge_inbox` **commands** did keep file
   cursors — only the runner, which the button and every automatic trigger use, did not.)

### How the push works now

- Rows are built from the durable push cursor and **paged** at the receiver's cap.
- Offline-**created** rows (those carrying `client_offline_id`) are sent **first and, wherever
  they fit, whole**. `apply_edge_inserts` remaps a new-references-new FK from an in-bundle
  map and *drops* the FK when the referent is not in the same bundle, so splitting them
  would silently unlink a child from the parent it was created with. When inserts genuinely
  exceed the cap they are still sent — refusing would restore the deadlock — but the split is
  reported as a `WARNING` in the run message rather than being silent.
- Sending inserts first is what makes an update page's high-water a valid cursor: by then
  every older row, insert or update, is already on the wire.
- The cursor advances **only over pages the cloud confirmed**. A rejected page, an
  unreachable operator, or the per-cycle page ceiling
  (`RMC_EDGE_SYNC_MAX_PAGES_PER_CYCLE`, default 20) all leave the remainder for the next
  cycle. Progress is durable and incremental, so a large backlog converges in steps.
- If the cloud's cap is lower than the box's page size, the box believes the cloud: the
  `400` response carries `max_rows`, which is surfaced in the run error telling you to set
  `RMC_SYNC_BUNDLE_MAX_ROWS` to match.

## Getting a stale box caught up

Pick whichever end you are standing at. Both do the same thing: rewind the cursor and let
the ordinary, idempotent apply path replay the corpus. **Neither hand-patches rows.**

### From the cloud (no access to the box needed)

Sync Center → **Queue full resync**. The request is recorded and rides back to the box as
`X-RMC-Sync-Directive: full-resync` on its own next download; the box then rewinds both
cursors and replays everything on the following cycle.

- Safe to press while the box is offline — the directive waits.
- Pressing twice does not queue two resyncs.
- One-shot: a directive is marked served when collected, so one request cannot cause a
  resync loop.
- The panel shows *queued, waiting for the box to connect* versus *collected at &lt;time&gt;*, which
  distinguishes "the box is offline" from "the box has it".

### On the box

```bash
python manage.py edge_sync_resync                 # rewind; next scheduled cycle replays
python manage.py edge_sync_resync --run           # rewind and drain now
python manage.py edge_sync_resync --direction pull  # one direction only
```

`--run` drives normal cycles until nothing is left, stopping on the first error (cursors are
unmoved past a failure, so re-running resumes safely) and bounded by `--max-cycles`.

## Verifying a deployment

```bash
python manage.py check_edge_sync_deploy_readiness
```

Read-only, safe on production. It checks the two things a green test suite cannot:

1. **The anchor columns and their partial-unique constraints really exist — in every tenant
   schema.** `evals.Evaluation` and `finance.Invoice` are TENANT_APPS models, so their tables
   exist once per schema and the columns arrive via `migrate_schemas`, which applies per
   schema and can succeed for some tenants and not others. A tenant missing the column does
   not fail loudly; it fails the first time that tenant's box syncs. A column present without
   its constraint is worse than a missing column — duplicate `client_offline_id` values are
   accepted, so one offline record lands as several.
2. **`accounts_accessrole` is populated.** Granular RBAC resolves through that table, so an
   empty one denies every gated surface while looking like a permissions misconfiguration.
   Migration `accounts.0029` seeds it idempotently, but **it is recorded as applied**, so a
   plain `migrate` will not repair a table emptied afterwards. That "applied but empty" state
   is exactly what a persisted test database ends up in — verified locally: `0029` recorded
   applied, table at 0 rows, while the ordinary dev database has all 25 rows. Use
   `--strict-seeds` to make this fail rather than warn.

## Money and marks stay cloud-authoritative

Nothing here changes conflict or direction policy. Invoices and Evaluations are `protected`
in `policy_registry`, so they apply on a cloud-pull and raise a Sync Center conflict on a box
push. `TeacherProfile` compensation, its payroll/leave authorization switches, and its
offboarding/merge pointers are **down-only** per field — see
[`EDGE_SYNC_IDENTITY_HOLD.md`](EDGE_SYNC_IDENTITY_HOLD.md). `finance.Payment` and
`PaymentProofUpload` remain held out entirely — see
[`EDGE_SYNC_FINANCE_HOLD.md`](EDGE_SYNC_FINANCE_HOLD.md).

## Known limitation

The **pull** direction is not paged. `SyncBundleDownloadView` has no row cap, so a first
full resync of a very large tenant downloads and applies one large bundle. That works (there
is no cap to trip) but it is one big transaction rather than incremental progress. Adding a
`limit` parameter is a protocol change on the cloud side — the box cannot page what the
server will not page — and is deliberately not bundled with this fix.

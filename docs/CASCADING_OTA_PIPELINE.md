# Cascading OTA — code and UI/UX delivery over the sync rail

Operator (cloud base) → Tenant (cloud workspace) → Edge (offline local box).

This document is the map. The reasoning for each decision lives in the module docstrings;
what is here is the shape, the contract, and the things that will bite you.

---

## 0. The one-paragraph version

Every deployment records what it is made of in `system_manifest.json` — the SHA-256 of
every shippable file, its category, and the per-app migration heads, hashed down to one
value. A box declares that value in a header on a sync request it was already making. The
cloud compares, and when they differ it names the target on the response. The box then
fetches only the files that actually changed, over the same HTTPS lane with the same
bearer credential, verifies every byte against the manifest before anything is promoted,
dry-runs the migrations, swaps, and must answer its own `/health/` within 60 seconds or it
puts everything back.

---

## 1. Phase 1 — Operator: packaging

| What | Where |
|---|---|
| `SystemManifestGenerator` | `apps/sync_engine/system_manifest.py` |
| `manage.py generate_system_manifest` | `apps/sync_engine/management/commands/` |
| Run at build time | `build.sh` (Render), `deploy/selfhost/Dockerfile` (appliance) |

Categories: `APP_CORE`, `UI_TEMPLATE`, `STATIC_ASSET`, `MIGRATION`, `CONFIG`, `LOCALE`,
`DATA_ASSET`. `ASSET_CATEGORIES` = the four a box can swap without reloading the
interpreter (`UI_TEMPLATE`, `STATIC_ASSET`, `LOCALE`, `DATA_ASSET`).

`DATA_ASSET` is the fall-through: anything that is not python and did not match an earlier
rule. It exists because classifying that bucket as `APP_CORE` made a **gate run on the
operator** indistinguishable from a code change. 3261 files on this tree are non-python
data — 1713 of them regenerated audit output under `docs/generated/` and `var/` that
`pre_push_boundary_check.py` rewrites — so every boundary-gate run would have sent the
whole fleet through the full lane (write freeze, worker pause, migration precheck, tree
swap, health gate) to deliver a json recording a test duration. They cannot simply be
dropped from the manifest: `super_views_enterprise_security` renders nine of those json
files into an operator dashboard and `country_matrix_service` reads the governance shards
at request time, so they are product surface. `.py` never reaches the fall-through, so
nothing in `DATA_ASSET` can require an interpreter reload.

**The manifest hash is content-only.** It is computed over the file map plus the migration
heads, and deliberately *not* over `generated_at` or the root path. Two builds of identical
source produce an identical hash — that is what makes "we are in parity" a fact rather
than a guess, and it is why a rebuild of unchanged source ships nothing.

**Excluded, permanently:** databases and their sidecars, `media/`, `staticfiles/` (it is a
*product* of `static/`), `.git`, virtualenvs, caches, the staging root, and the test suite.
A manifest is the shippable surface, not a backup of the checkout.

**CI check:** `generate_system_manifest --check` exits non-zero when the committed manifest
no longer matches the tree.

---

## 2. Phase 2 — Tenant: handshake and delta

### Headers (all on the existing bundle rail)

| Header | Direction | Carries |
|---|---|---|
| `X-RMC-Sync-Manifest` | box → cloud | the box's manifest hash |
| `X-RMC-Sync-Engine` | box → cloud | the box's build commit (advisory) |
| `X-RMC-Sync-Manifest-Target` | cloud → box | the manifest the operator is serving |
| `X-RMC-Sync-Manifest-Advice` | cloud → box | one human sentence for the Sync Center |
| `X-RMC-Sync-Upgrade-Failure` | box → cloud | why the last upgrade did not land |

`X-RMC-Sync-Upgrade-Failure` is how a box nobody is standing next to reports a failed
upgrade: it rides the next ordinary request and the cloud logs it at `WARNING` against the
school. Logged rather than stored — the durable record already exists on the box, and a
cloud table for a diagnostic string would add a write to the hot path of every pull.

Emitted by `edge_outbox.local_manifest_headers()`, compared by
`sync_bundle_api._manifest_handshake()`, which is the exact sibling of the existing
`_schema_handshake` — that one compares what the *database* has applied, this one compares
what the *deployment is built from*. Two boxes on identical migration heads can still be a
whole UI release apart.

### Routes

| Route | Purpose |
|---|---|
| `GET /api/sync/upgrade/manifest/?since=<hash>` | target identity + delta |
| `GET /api/sync/upgrade/chunk/?path=&offset=&length=` | one resumable byte range |

Same mount, same bearer credential, same shape as `sync/files/`. **No new port, no new
hostname, no SSH, no object-store URL** — a school's firewall has already approved exactly
one lane, and an upgrade channel that needs a firewall change is one that never runs.

`path` is authorised by being a **key in the manifest**, not by string sanitisation, and
the resolved location is re-checked against the manifest root so a planted symlink cannot
widen the set. This mirrors `file_manifest.servable_paths`.

### The delta

`apps/sync_engine/upgrade_delta.py`. Content-addressed (a file is "changed" only when its
SHA-256 differs) and category-bounded (`categories=ASSET_CATEGORIES` gives the lane a box
can apply without a reload). Capped by `RMC_OTA_DELTA_MAX_FILES` / `_MAX_BYTES`.

`complete: bool` is the field that must never be guessed at downstream — it is `True` only
when applying this delta whole lands the box exactly on `target_hash`. A truncated or
category-filtered delta sets it `False`, and the rollout manager refuses to stamp a
manifest it did not fully receive.

---

## 3. Phase 3 — Edge: the blue-green guard

`apps/sync_engine/local_upgrade.py::LocalRuntimeUpgradeManager`. Six steps, in this order
for these reasons:

1. **drain** — freeze user writes, pause background workers, hold the rail, then let
   in-flight cycles finish. Bounded; a cycle that outlives the budget is recorded, not
   fatal. See §3.1 — every one of these is undone on **every** exit path.
2. **stage** — every byte into an isolated directory. The running tree is untouched, so an
   abort here costs nothing.
3. **verify** — re-hash everything against the manifest. **This is the step that makes the
   rest safe.** A truncated download, a corrupted chunk and a tampered file are
   indistinguishable from a good one afterwards; all three die here.
4. **precheck** — the migration plan is scanned for destructive operations (reusing
   `platform_runtime.schema_rollout.DANGEROUS_OP_TYPES`) and, where the backend supports
   transactional DDL and django-tenants is off, actually executed inside a transaction that
   is then rolled back. The manager reports which tier it got: `transactional` or
   `plan-only`. It does not imply the stronger one.
5. **activate** — two shapes, chosen by whether `RMC_OTA_RELEASE_ROOT` is set:
   * **release layout** — `<root>/releases/<hash>` is assembled by copying the current
     release and overlaying the verified staged files, the *assembled* tree is re-verified
     against the whole manifest (a `copytree` that silently dropped a file must not reach
     traffic on the strength of a check that only looked at what we fetched), then
     `<root>/current` is repointed with an atomic rename. Nothing serving changes until
     that one call, and going back is the same call.
   * **single tree** — per-file `os.replace` (atomic on POSIX and Windows), with every
     overwritten file copied into the release's `rollback/` set *first*.

   Either shape then runs `collectstatic` (only when a `STATIC_ASSET` actually changed),
   flushes caches, and asks the web workers to reload (§3.2).
6. **health** — poll `/health/` for `RMC_OTA_HEALTH_TIMEOUT_SECONDS` (60). No 200 → the
   **schema is reversed first, then the files** (§3.3), and `EdgeDeploymentHistory` records
   `ROLLED_BACK`.
7. **revive** — on success the box fires one GET at the upgrade-manifest endpoint with its
   new hash, which releases the cloud-side hold immediately instead of a cadence interval
   later. A failed callback never turns a successful upgrade into a failure.

### 3.1 Quieting the box — `apps/sync_engine/upgrade_runtime.py`

| Control | How | If unavailable |
|---|---|---|
| user writes | writes the cache key the **existing** `MaintenanceModeMiddleware` consults before the DB — no new middleware, no new 503 template, no DB write while the schema is moving | reported, upgrade proceeds |
| background workers | Celery `cancel_consumer` over the broker they are already on (a drain, not a shutdown — shutdown abandons in-flight work) | "no broker configured", stated plainly |
| web workers | §3.2 | |

The freeze **deletes** its key to thaw rather than writing `False` — writing `False` would
pin the box out of a maintenance mode an operator turned on deliberately before the
upgrade. It also carries `RMC_OTA_WRITE_FREEZE_TTL_SECONDS`, so a process that dies
between freeze and thaw cannot leave a school locked out.

### 3.2 Worker reload

`RMC_OTA_WORKER_RELOAD_COMMAND` (shlex-split argv, never a shell) → else
`RMC_OTA_WORKER_RELOAD_PIDFILE` (SIGHUP = gunicorn graceful reload) → else it **reports**
that the swap lands on the next container restart. It does not hunt for a plausible parent
process to signal: a wrong guess kills a school's web server.

### 3.3 Rollback unwinds the schema, not just the files

`EdgeDeploymentHistory.migration_floor` records the per-app heads **before** anything ran.
On rollback the schema is reversed to that floor *first*, then the files — restoring code
while the database still carries new columns is the same split-brain arrived at from the
other direction. Only apps this attempt advanced are touched. A migration Django cannot
reverse is **reported and left applied**: there is no safe automatic way to undo a data
migration on a school's live database, and a rollback that destroys records to restore a
schema has done more damage than the failure it was cleaning up.

### What it does not pretend to do

Python that is already imported stays imported. The **assets lane** genuinely takes effect
immediately (templates and static are re-read per request / per collectstatic). The **full
lane** needs a worker reload, and where the deployment is not laid out for a symlink swap —
the ordinary `COPY . .` image is not — it stages, verifies, prechecks, records, and reports
`activation="deferred"`. It does not claim a swap it did not perform.

`RMC_OTA_RELEASE_ROOT` names that layout. On the selfhost image you do not have to build
it by hand — the entrypoint seeds `releases/<id>/` and `current` on first boot (§4d) —
but it must point at a **mounted volume**, or every restart discards the releases and
re-seeds, throwing away the one thing a rollback needs. On any other deployment, set it
only where that layout already exists.

---

## 4. The interlock with data sync

`sync_runner._execute_sync_transport` checks the local hold **before any data moves**. A
held cycle returns `held_for_upgrade=True`, `ok=True`, zero rows, one `EdgeSyncRun` row,
and **cursors unmoved** — a hold defers work, it never drops it.

`SYNC_STATE_HELD_FOR_UPGRADE` lives in the **cache**, never a table
(`apps/sync_engine/upgrade_lock.py`). The state it describes is "the database may be
mid-migration"; reading it from a row means the sync worker asks the very database being
altered whether it is safe to talk to that database, and a migration that takes a lock
hangs the worker on its own status check.

### Three ways a hold ends — all of them required

* **parity** — the next handshake sees equal hashes and releases on that same request;
* **TTL** — `RMC_OTA_HOLD_TTL_SECONDS` (default 3600, floored at 60). Past it the rail
  resumes on the *old* code, which is a state the box is known to survive;
* **acknowledgement** — once the box has carried a target as far as its mode allows (an
  assets-only lane, or a code lane needing an image rebuild), it stops blocking. The
  upgrade stays visible on every cycle via `result["upgrade_available"]`.

And it is **armed only for the `full` lane**. That is the whole of it — not "any mode that
is not off".

The hold exists because the *database* may be mid-migration. An `assets` lane carries no
migration and no importable python, by construction: `ASSET_CATEGORIES` cannot contain a
`.py` file, because `categorise()` returns `APP_CORE` for `.py` before the fall-through. So
there is no schema to be mid-anything, and pausing a school's records to deliver a
stylesheet would be pure cost. With `off`, nothing on the box would act on the hold at all,
and a school whose records stop syncing because a code update is pending is worse off than
a school running one release behind.

The skew case that *does* need care is handled precisely, one layer up: the cloud's
`_schema_handshake` withholds exactly the entities owned by an app the box is behind on and
lets everything else through — it degrades, it does not refuse.

A `mode="dry"` probe is exempt — it writes nothing in either direction, and it is the one
tool that answers "can this box still reach the cloud" while the box is held.

---

## 4b. Rollout rings — who may move, and when

`apps/sync_engine/models_rollout.py`, migrations `0019` + `0020_rollout_rls`.

A manifest existing on the operator is not the same as a school being allowed to move to
it. Before rings, the first box to sync after a deploy took the new release and so did
every box behind it — so a release wrong in a way no test caught reached the whole fleet
before anyone had looked at the first one. The failure being guarded against is not "a box
gets a bad release"; it is "every box gets it at once and there is no healthy peer left to
compare against".

| Record | Scope | Holds |
|---|---|---|
| `EdgeRolloutPolicy` | per school (`school` FK → RLS-enumerated in `0020`) | `ring` (canary \| stable), `paused` |
| `ManifestRelease` | per manifest, **no** `school` FK | which `rings` that manifest is released to |

`ManifestRelease` is deliberately not tenant-scoped: how far a release has been promoted is
identical for every school, so a `school` FK would both misdescribe it and enrol it in the
tenant RLS gate for data it does not hold — the same call `EdgeDeploymentHistory` makes.

**A missing row is never a refusal.** A school with no policy is on `stable`; a manifest
with no release row is on `RMC_OTA_DEFAULT_RELEASE_RINGS` (default `canary`). Requiring an
operator to pre-create a row per school before anything could ship would make a fresh
install silently dead. Nothing writes on the read path — rows appear only when an operator
decides something.

Enforced in **two** places, on purpose: the handshake declines to *advertise* an unreleased
manifest (a box told "upgrade available" and then refused the bytes retries forever and
looks stuck), and `sync_upgrade_api._guard` refuses to *serve* one — 409 `not_released`,
not 403, because nothing is wrong with the box or its credentials.

    manage.py ota_rollout --status
    manage.py ota_rollout --ring <school> canary
    manage.py ota_rollout --promote canary stable
    manage.py ota_rollout --pause <school>

Promotion is not monotonic: `--promote canary` after `--promote canary stable` pulls a bad
release back while a fix is prepared.

---

## 4c. What the cloud keeps, and where an operator reads it

`apps/sync_engine/models_fleet.py` (`EdgeFleetState`), migrations `0021` + `0022`,
console at `/super/edge-fleet/`.

Every box already told the cloud what it was: `X-RMC-Sync-Manifest` on every handshake,
`X-RMC-Sync-Engine` naming the build, `X-RMC-Sync-Upgrade-Failure` carrying a stopped
upgrade. All three were read and **discarded** — the hash was compared and dropped, the
failure went to a logfile. So "which school is on which release, and which one is stuck"
had no answer, and the honest way to get one was to ring the school.

`EdgeDeploymentHistory` cannot answer it and that is not a defect: it is written on the
**box**, in the box's own database, behind that school's link. `EdgeFleetState` is the
other half — what the *cloud* observed. One row per school, overwritten; the durable
history stays on the box, because a row per handshake per school is millions of rows a
year to answer "what is it on now".

Three distinctions the console is careful about:

* **Seen ≠ moved.** A box that checked in four minutes ago and last changed manifest in
  June is healthy on the network and stuck on the upgrade. Separate columns.
* **Waiting ≠ stuck.** A school not yet promoted to is behaving correctly. Painting it
  like a failure teaches an operator to ignore the colour.
* **A resolved failure stops being shown**, or the operator chases a ghost.

Read-only: promotion is `manage.py ota_rollout`, because a button that releases a build to
every school is a button that gets clicked by accident.

---

## 4d. Release layout — how the full lane becomes real

`deploy/selfhost/release_layout.sh`, `RMC_OTA_RELEASE_ROOT`.

The stock image is one tree, so a code swap cannot be atomic and the manager refuses:
`deferred — apply with an image rebuild`. Set `RMC_OTA_RELEASE_ROOT` (and mount a volume
there) and the box gets `releases/<hash>/` plus a `current` symlink; the entrypoint serves
**from the symlink**, which is the part that makes it real — a symlink nothing serves from
is decoration. Opt-in: unset, the box boots exactly as before.

### It has to fit, on the box the school could actually afford

A release is a whole tree. The app measured ~496MB across 16333 files on 2026-08-22, so a
box on this layout is committing roughly a gigabyte to hold two of them. That is fine on a
mini-PC with a real disk and completely wrong on a small appliance, and the failure is not
"the upgrade did not apply" — it is a **full filesystem**, which stops Postgres writing, so
the school loses its data sync, its portal and its offline shell along with an upgrade it
never wanted that badly.

So nothing copies a tree without measuring first:

* **On boot** (`release_layout.sh`) the seed is skipped unless `df` reports
  `RMC_OTA_RELEASE_HEADROOM_PCT` of what `du` says the tree costs. Every failure path —
  no volume, short disk, broken copy, no symlink support — falls back to serving the live
  tree and says so. **The function cannot fail the boot.** A school whose box does not
  start is in far more trouble than one whose box needs an image rebuild to take a code
  upgrade, and the boxes most likely to hit a short disk belong to the schools least able
  to absorb an outage. The copy goes to `<seed>.partial` and is renamed only on success,
  so an interrupted copy can never be mistaken for a complete release.
* **On upgrade** (`local_upgrade._require_disk_headroom`) the same measurement runs before
  `copytree`, and a short disk raises `UpgradeAborted` — the box stays on its current code
  and keeps syncing. If the copy fails anyway, the half-built tree is removed rather than
  left holding down the space that ran out.
* **After a successful flip**, `_prune_old_releases` deletes everything but the current
  release and the rollback target. Without it the layout is a slow disk leak: every
  upgrade adds a tree and nothing removes one, so the box eventually fails the check above
  having spent its disk on releases nobody will ever roll back to.

Neither measurement is allowed to be fatal by itself. If `du`/`df`/`disk_usage` cannot
answer, the upgrade proceeds — refusing on "I could not tell" would strand every box with
an unusual filesystem.

And the half that is easy to forget: **a swapped file changes nothing until the process
reloads.** gunicorn writes `GUNICORN_PIDFILE`, both entrypoint paths export it, and
`RMC_OTA_WORKER_RELOAD_PIDFILE` falls back to it — two env vars that must name the same
file is a trap where a wrong path degrades silently to "reload NOT configured".

---

## 5. `EdgeDeploymentHistory`

`apps/sync_engine/models_deployment.py`, migration `0018`. Append-only
(`AppendOnlyManager` — a rollback target that can be edited is not a rollback target).
**No `school` FK**: the code a box runs is a property of the box, not of the school it
serves, and adding the FK would enrol the table in the tenant RLS coverage gate for data it
does not hold.

`revert_target()` returns the newest `SUPERSEDED` row — a manifest that actually *booted* —
never the attempt that just failed.

A **failed** row is the most valuable row in the table: it says the box tried, why it
stopped, and which manifest it is still serving.

---

## 6. Settings

| Setting | Default | Notes |
|---|---|---|
| `RMC_OTA_ENABLED` | `1` | cloud half; read-only, costs nothing until a box asks |
| `RMC_OTA_AUTO_APPLY` | `assets` | `off` \| `assets` \| `full` — `assets` is the default so the pipeline is not ceremonial; `full` stays opt-in |
| `RMC_OTA_MANIFEST_PATH` / `_ROOT` | `""` | default `BASE_DIR` |
| `RMC_OTA_STAGING_ROOT` | `""` | default `<BASE_DIR>/.rmc_ota_staging` |
| `RMC_OTA_RELEASE_ROOT` | `""` | unset ⇒ code swap defers rather than pretends |
| `RMC_OTA_RELEASE_HEADROOM_PCT` | `140` | free space required before a release copy starts, as a % of the tree; floored at 100 |
| `RMC_OTA_RELEASES_KEPT` | `2` | release trees left on disk; floored at 2, because the second one is the rollback target |
| `RMC_OTA_HEALTH_URL` | `http://127.0.0.1:10000/health/` | |
| `RMC_OTA_HEALTH_TIMEOUT_SECONDS` | `60` | blue-green budget |
| `RMC_OTA_HOLD_TTL_SECONDS` | `3600` | floored at 60 |
| `RMC_OTA_COLLECTSTATIC` | `1` | required under `ManifestStaticFilesStorage` |
| `RMC_OTA_DELTA_MAX_FILES` / `_MAX_BYTES` | `5000` / `256 MiB` | |
| `RMC_OTA_ALLOW_DANGEROUS_MIGRATIONS` | `0` | there is no safe automatic answer to "may I drop this column on a school's live database" |
| `RMC_OTA_FREEZE_WRITES` | `1` | reuses the existing maintenance middleware |
| `RMC_OTA_WRITE_FREEZE_TTL_SECONDS` | `1800` | floored at 60 |
| `RMC_OTA_WORKER_RELOAD_PIDFILE` / `_COMMAND` | `""` | unset ⇒ reload is reported, never guessed |
| `RMC_OTA_WORKER_PAUSE_COMMAND` / `_RESUME_COMMAND` | `""` | unset ⇒ Celery remote control |
| `RMC_OTA_REVERSE_MIGRATIONS_ON_ROLLBACK` | `1` | irreversible migrations are reported, not forced |

---

## 7. Operating it

```bash
# operator, at build time (already wired into build.sh + the selfhost Dockerfile)
python manage.py generate_system_manifest --channel stable
python manage.py generate_system_manifest --check      # CI drift gate

# box
python manage.py edge_apply_upgrade --status           # change nothing
python manage.py edge_apply_upgrade --mode assets      # templates/static/locale
python manage.py edge_apply_upgrade --mode full        # + python and migrations
python manage.py edge_apply_upgrade --from /mnt/usb    # LAN data-mule, no network
```

The `--from` path is not a convenience: the verification gate is a property of the
manifest, not of HTTP, so a USB stick carried to a school with no link at all goes through
byte-for-byte the same gates as a network transfer.

---

## 8. The three platform rules this respects

1. **Unified transport.** Upgrade bytes travel the pre-approved HTTPS lane with the
   existing bearer credential. No second port.
2. **Static isolation.** Production already serves through
   `ForgivingCompressedManifestStaticFilesStorage`; the manager runs `collectstatic` after
   an asset swap, because under a manifest storage uncollected bytes are unreachable by any
   URL a template can build.
3. **Ephemeral locks.** `SYNC_STATE_HELD_FOR_UPGRADE` is cache-only — see §4.

---

## 9. Tests

| File | Runs |
|---|---|
| `test_ota_manifest_2026_08_22.py` | no database (18) |
| `test_ota_sync_interlock_2026_08_22.py` | `UpgradeRouteContractTests` + `NoDatabaseInterlockTests` no database (17); `HeldCycleIntegrationTests` needs one |
| `test_ota_runtime_controls_2026_08_22.py` | no database (21) |
| `test_ota_corrupt_bundle_2026_08_22.py` | needs a database |
| `test_ota_default_lane_2026_08_22.py` | the assets-only default and the re-gated hold (12) |
| `test_ota_rollout_rings_2026_08_22.py` | ring policy, promotion, reversibility (20) |
| `test_ota_rollout_command_2026_08_22.py` | every `ota_rollout` flag, incl. query-count scaling (24) |
| `test_ota_fleet_console_2026_08_22.py` | what the cloud keeps and how it classifies it (22) |
| `test_ota_release_layout_2026_08_22.py` | the deployment wiring and the reload (12) |
| `scripts/tests/test_verify_ota_pipeline_wiring.py` | the wiring gate itself, stdlib (10) |

The corrupt-bundle suite is the load-bearing one. It writes a real tree, truncates one JS
bundle exactly the way a dropped link does, and asserts the guard detects it, that the
running tree is **byte-identical** afterwards, that the failure is recorded, and that the
box keeps syncing on its old code. It is paired with a clean-bundle calibration test —
without that, "it stopped on corruption" proves nothing.

`test_ota_rollout_command_2026_08_22.py` exists because `ota_rollout` is the **only** path
from "the canary looks fine" to "everybody gets it" — the console is read-only on purpose.
A crash in that command would not fail a gate and would surface for the first time when an
operator reached for it during an incident. It also pins the cost of the fleet listing as
*independent of fleet size*, which is not a micro-optimisation: `may_receive` does two
lookups per call, which is right for the handshake (one school) and 600 avoidable queries
for a 300-school console page.

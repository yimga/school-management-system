# Edge ↔ Cloud sync + going live with real data (operator runbook)

How to load a school's real data (student records, specialties/trades, staff, finance)
and keep a self-hosted **edge box** and the **cloud** converged — in the correct order.

Companion docs: `EDGE_LAN_HOSTNAME_DNS.md` (reaching the box).

**Single source of truth for the ordered steps, `runs_on`, copy-paste commands, and
validators:** `apps/lifecycle/edge_onboarding.py` (`EDGE_ONBOARDING_STEPS`).
The operator console is `/super/edge-onboarding/` (`super:edge_onboarding_runbook`).
Box verify command: `python manage.py edge_onboarding_verify --slug <slug> [--include-gate]`.
This markdown is the narrative SOP; if it disagrees with the engine, the engine wins.

---

## The one thing to get right first

**Delta sync is a convergence rail, not a data loader.** It keeps a *fixed, limited* set
of operational entities in step once both sides already hold the data. It will **not**
carry your initial bulk import from cloud to box. Use the right tool for each job:

| Job | Tool | Runs on |
|---|---|---|
| Bulk-import the school's real files | **Migration Cloud** connector (the "TVET ingest") | Cloud |
| Seed the box with that data (initial) | **sovereign bundle** export → import | Cloud → Box |
| Keep the two converged, ongoing | **delta sync** (`edge_sync_cycle` / "Sync now") | Box ↔ Cloud |

---

## What delta sync carries — and what it deliberately does NOT

Source of truth: `_get_entity_config(include_derived=True)` in `apps/api/sync_services.py`.

**Two-way synced (Class-A operational entities):**
`student` (incl. `specialty_id`), `classroom`, `attendance`, `applicant`, `student_note`,
`academic_year`, `term`, `department`.

**Excluded on purpose — do NOT expect sync to move these:**

- **Finance / money** — cloud-authoritative, **down-only**. The box never overwrites the
  cloud's financial records; on a money conflict the cloud wins.
- **Teacher records** (`TeacherProfile`) — deferred, because they carry salary/pay-grade
  fields; two-way last-writer-wins would let a box edit override cloud compensation.
- **Grades / marks** (`Evaluation`) — not on the two-way rail.
- **Specialty / trade catalog, documents, and most master data** — loaded by the bulk
  importer + the sovereign seed, not by delta sync.
- Governance columns like `academic_year.is_locked` / `enable_gce_registration` — the
  cloud owns these; a box can never reopen a year the cloud locked (MEMORY M29).

If you load your whole dataset onto the cloud and just wait for sync, most of it stays
stranded on the cloud. That is why the bulk import + sovereign seed steps below exist.

---

## Step 0 — Unlock the box ("Do your next action")

The box shows an **Activation First Action** screen and a **conversion lock**: *"Saving
attendance, marks, a report, or a payment records your first value and unlocks the full
workspace."* Until then the workspace UI is gated.

Source of truth: `apps/schools/conversion_lock_state.py` +
`apps/academics/signals.py::conversion_first_action_on_attendance_saved`.

- The lock unlocks the instant the school records **one** first value — **save one
  attendance record, one mark, one report, or one payment**. It is idempotent and
  one-time. The pink **"Do it now · 1 CLICK"** button on the activation screen does exactly
  this.
- The lock only gates **UI navigation** — it never blocks server-side imports. You can run
  the cloud-side bulk import (Step 1) before or after clearing it.

**Do this first** so the box UI is usable; it takes one action.

---

## Step 1 — Bulk-load the real data on the CLOUD (Migration Cloud)

The cloud is the system of record, and finance **must** originate cloud-side, so the
authoritative bulk import happens here.

1. On the cloud tenant, open **Migration Cloud** → the connector upload flow.
2. Upload the school's files (student roster, specialties/trades, staff, finance, etc.).
3. Map columns, review the bundle, and **apply** it.
4. If a live apply lands rows you need to undo, the review page has a **"Revert this
   import"** panel; operators have **Resume** + **"Revert the entire import"** on
   `/super/migration/<id>/`.

Nothing blocks this step — start it whenever the files are ready.

---

## Step 2 — Seed the box from a cloud snapshot (sovereign bundle)

The box was brought up empty (`import_sovereign_tenant --fresh` skips data). To put the
real data on the box the **first** time, seed it from a full cloud snapshot — **not** delta
sync. The bundle is **pk-preserving**, so foreign keys (e.g. `student.specialty_id`) line
up on both sides and later delta sync converges cleanly.

On the **cloud**, export the tenant bundle:

```bash
python manage.py export_tenant_bundle --slug gilead-tech --out /srv/rmc/gilead-tech.rmcbundle
```

Move the bundle to the box, then on the **box** import it (data-carrying, i.e. **without**
`--fresh`):

```bash
python manage.py import_tenant_bundle --in /srv/rmc/gilead-tech.rmcbundle --expect-school-id <school-uuid>
# equivalent: import_sovereign_tenant WITHOUT --fresh after the shell exists
```

> Confirm the exact flags with `--help` on the box's deployed build. `--fresh` is the
> empty-shell path used for first bring-up; omit it to carry data.

---

## Step 3 — Turn on ongoing delta sync

Prerequisites on the **box** (`.env`) — sync is flag-gated; with the flag off every sync is
a silent no-op:

| Env var | Purpose |
|---|---|
| `RMC_EDGE_SYNC_ENABLED=1` | Master switch. Off → sync does nothing. |
| `RMC_EDGE_CREDENTIAL=<token>` | Edge bearer token the cloud checks. Mint with `python manage.py mint_edge_credential`. |
| `RMC_EDGE_OPERATOR_BASE=https://<cloud-url>` | Cloud base URL the box pushes/pulls against (falls back to `RMC_HUB_BASE_URL`). |

Two ways to run a cycle (both push local changes UP, then pull cloud changes DOWN and
apply — each direction independent, offline-safe, idempotent):

**A. The button — Sync Center (on demand).** In the tenant, **Settings → Sync Center**
(`siteconfig:sync_center`), click **Sync now**.
- Defaults to **dry mode**: a no-write probe — counts pending local changes and confirms
  the cloud is reachable + the credential is accepted, writing nothing. **Run this first.**
- **Live mode** does the real push-up-then-pull-down-and-apply.
- Every click records one `EdgeSyncRun` row and flashes `pushed N, pulled N, conflicts N`;
  it never crashes the page even if the cloud is unreachable.

**B. The command — `edge_sync_cycle` (continuous).** On the box:

```bash
python manage.py edge_sync_cycle --slug gilead-tech
```

For hands-off continuous sync, run it on a timer (cron every few minutes):

```cron
*/5 * * * * cd /path/to/app && python manage.py edge_sync_cycle --slug gilead-tech >> /var/log/rmc-edge-sync.log 2>&1
```

---

## Step 4 — Prove sync works

After the box is seeded (Step 2) and the flag is on (Step 3):

1. Sync Center → **Sync now** in **dry mode** → expect *"cloud reachable, credential
   accepted."*
2. Make one small change to a synced entity (e.g. edit a student's classroom on the box,
   or add an attendance row on the cloud).
3. Run a **live** cycle (button or `edge_sync_cycle`) and confirm the flashed
   `pushed`/`pulled` counts reflect the change on the other side.

Testing convergence with a **small edit after seeding** is the correct test — not watching
the bulk load travel over sync (it won't; see the exclusion table above).

---

## Choosing when the box syncs

By default the box syncs continuously and adapts — faster when there are changes, backing
off when the cloud is unreachable. A school that wants specific times instead sets them in
**Sync Center → Sync schedule**: *every 30 minutes, 7:00 AM to 6:00 PM, Monday to Friday*,
or *at 6:00 AM and 10:00 PM, every day*, or both. Times are the SCHOOL's local time.

Three things worth knowing before you promise anything to a school:

1. **A schedule change lands on the box's NEXT cycle, not instantly.** The cloud cannot
   open a connection to a box, so the schedule travels down as a row and the box evaluates
   its own copy. Saving raises a wake, so it is usually seconds — but on a box that is
   asleep or offline it is not, and the screen says so rather than pretending.
2. **"Sync now" and a queued directive always run, schedule or no schedule.** An explicit
   human action never waits for a window.
3. **The box still checks in hourly even outside every window.** "Queue full resync" is
   collected by the box ASKING, so a box that went twelve hours without asking could not be
   given an instruction for twelve hours. Raise `RMC_EDGE_SYNC_IDLE_CEILING_SECONDS` if a
   school genuinely wants nothing in between, and accept that operator instructions queue
   for that long.

If the panel shows a missed window, the box was not reachable when a scheduled moment
passed. It catches up ONCE on its next connection — not once per missed moment.

Full design and the DST rules: `docs/EDGE_SYNC_SCHEDULES.md`.

## Conflicts

When both sides changed the same record, it lands as a **`SyncConflict`** in the Sync
Center with a pending count. Resolve each **Keep server** / **Keep client** / **Discard**.
Money never reaches here — it is cloud-authoritative by policy.

---

## Gotchas

- **Box not on the latest build?** Render auto-deploy is off. If `edge_sync_cycle`, the
  Sync Center button, or the branding commands report "Unknown command"/missing, the box
  needs a **manual redeploy** to pick up current code.
- **Reaching the box:** use **`http://<host>:10000/`** — plain HTTP, no TLS. `https://…`
  fails ("no lock"). See `EDGE_LAN_HOSTNAME_DNS.md`.
- **`.school.lan` host 400s?** Set `MULTI_TENANT_BASE_DOMAIN=school.lan` on the box (the
  default ALLOWED_HOSTS covers `.local`, not `.lan`).

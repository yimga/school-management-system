# Edge ↔ Cloud sync + going live with real data (operator runbook)

How to load a school's real data (student records, specialties/trades, staff, finance)
and keep a self-hosted **edge box** and the **cloud** converged — in the correct order.

Companion docs: `EDGE_LAN_HOSTNAME_DNS.md` (reaching the box).

**Single source of truth for the ordered steps, `runs_on`, copy-paste commands, and
validators:** `apps/lifecycle/edge_onboarding.py` (`EDGE_ONBOARDING_STEPS`).
The operator console is `/super/edge-onboarding/` (`super:edge_onboarding_runbook`).
Box verify commands: `python manage.py verify_edge_link --http` (is the box talking to
the cloud, and if not, which link is broken?) and
`python manage.py edge_onboarding_verify --slug <slug> [--include-gate]` (is the whole
onboarding done?).
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

## Step 3 — Pair the box with its cloud tenant

This is the whole of "connect the box to the cloud". It is one command on the box and
one click in the cloud, and there is **nothing to type into a `.env` file**.

**On the box** (shell, or open `http://<box-host>:10000/edge/pair-this-box/` in a browser):

```bash
python manage.py pair_box --slug gilead-tech --wait
```

`--slug` is optional — the box resolves its school from its binding or
`RMC_EDGE_SCHOOL_SLUG` — but naming it lets a technician pair a box whose
environment names neither, and the cloud address is derived from it.

It prints a short code and holds:

```
    Pairing code:  K7RM-42XQ
    Expires:       2026-08-27T14:05:00Z
    Cloud:         https://gilead-tech.runmycampus.com
```

**On the cloud**, an administrator of that school signs in and goes to **Settings → Sync
Center → Pending boxes**, enters the code, and approves. The box collects its credential
on its next poll (a few seconds) and starts syncing.

**Why this shape.** The code alone grants nothing — approval happens inside an
authenticated session, and the credential is minted in the response to the box's own
poll, so it never travels through a person, a chat message, or a text file. The box
reaches the cloud over the *same* outbound path it will use to sync, so a pairing that
succeeds has already proved the network path. A pairing that fails tells you the cloud
is unreachable *before* any credential exists, instead of surfacing days later as a
credential error.

### What pairing sets up for you

| Thing | Where it lives now |
|---|---|
| Cloud base URL | The box's own database (`EdgeCloudBinding`) |
| Edge credential | Same row, encrypted at rest (Fernet) |
| "Is sync on?" | **Implied by the pairing** — see below |

A **paired box is an enabled box**. `RMC_EDGE_SYNC_ENABLED` is no longer something you
have to remember: a durable binding, written because a named administrator approved this
box, counts on its own. The flag still works and still turns sync on for a box that was
never paired, so nothing existing needs migrating.

Because the binding is in the box's database rather than in `deploy/selfhost/.env`, it
survives a container rebuild and is captured by any backup worth the name. A box updated
by rebuilding its image comes back paired.

### When nobody is available to approve

An installer at a scheduled visit cannot always get a school admin on a console.

- **Claim ticket (unattended).** On the cloud, ahead of the visit:
  `python manage.py mint_claim_ticket --slug gilead-tech`. On the box:
  `pair_box --claim <ticket>`. It pre-authorises exactly **one** adoption of that **one**
  school, and every reuse after the first is recorded as misuse — the legitimate box
  redeems once, so a second attempt means the ticket is in someone else's hands.
- **Deferred approval.** A request stays open for days. The installer can leave; the
  school approves later and the box picks it up on its next poll.
- **Platform staff backstop.** Staff can approve on the school's behalf. It is recorded
  in `approved_by`, so an operator-approved box is visibly operator-approved forever.

### Legacy path (still supported)

Mint on the cloud and set on the box — unchanged, nothing to migrate:

| Env var | Purpose |
|---|---|
| `RMC_EDGE_SYNC_ENABLED=1` | Master switch for a box that was never paired. |
| `RMC_EDGE_CREDENTIAL=<token>` | Mint with `python manage.py mint_edge_credential`. |
| `RMC_EDGE_OPERATOR_BASE=https://<cloud-url>` | Falls back to `RMC_HUB_BASE_URL`. |

A stored pairing **wins** over these. To go back to the environment, clear it
explicitly: `python manage.py pair_box --unpair --yes`.

---

## Step 4 — Prove the link, end to end

One command answers "is this box talking to the cloud?" — run it **on the box**:

```bash
python manage.py verify_edge_link --http
```

It walks the chain in the order data actually flows and names the **first** broken link
with the command that fixes it:

```
Box <-> cloud link

    [ok]  deployment           edge sync is live - this box is paired to a cloud tenant
    [ok]  cloud address        https://gilead-tech.runmycampus.com (source: pairing)
    [ok]  credential           held for gilead-tech, expires 2027-08-20T…
    [ok]  school               gilead-tech (Gilead Tech High)
    [ok]  scheduler            sync_engine.edge_sync_cycle is registered in this process
    [ok]  recent activity      last cycle 44s ago: ok=True pushed=0 pulled=3 deleted=0
    [ok]  cloud directives     nothing queued for this box
    [ok]  cloud pull           HTTP 200 - cloud responded
    [ok]  cloud push           HTTP 400 - cloud responded
```

Fix the first `[FAIL]` and re-run; the later ones are usually consequences of it. It
exits non-zero on failure, so it can gate a deploy step. `--json` for machine use.

`cloud push` reporting **HTTP 400** is correct — the probe posts an empty body that the
cloud rejects by design. What matters is that the cloud *answered*.

### The `scheduler` check is the one nothing else made

A box can hold a perfect address and a perfect credential and still never sync, because
nothing in the process is driving a cycle. From the cloud that is indistinguishable from
a box that is switched off. That line is the difference.

### Then prove convergence with real data

1. Make one small change to a synced entity (edit a student's classroom on the box, or
   add an attendance row on the cloud).
2. Wait one cycle, or run `python manage.py edge_autosync` on the box.
3. Confirm the change appears on the other side.

Testing with a **small edit after seeding** is the correct test — not watching the bulk
load travel over sync (it won't; see the exclusion table above).

---

## "Sync now": what each button actually does

The two buttons are not the same button, and the difference is physical, not a policy
choice. **A box sits on a private LAN behind NAT, so the cloud can never open a
connection to it.** Every transfer is box-initiated.

**From the BOX — Settings → Sync Center → Sync now.** Runs a real cycle immediately:
push local changes up, then pull cloud changes down and apply. Start in **dry mode** (a
no-write probe: counts pending changes, confirms the cloud is reachable and the
credential accepted), then run live. Each click records one `EdgeSyncRun`.

**From the CLOUD — Settings → Sync Center → Queue full resync.** *Records* an
instruction. It cannot reach into the box's LAN, and the honest mechanism is the reverse:
the cloud writes down what it wants and the box collects it the next time it calls out.
The panel shows **requested** → **delivered** so you can tell "the box has not called
home yet" (a connectivity problem) from "the box has it".

This is why an earlier cloud-side "sync the box now" button failed every single time it
was pressed: it was asking for something physically impossible.

**How fast is the cloud→box path?** Queueing a directive nudges the long-poll changes
feed, so a box holding that feed open returns within about a second rather than waiting
out its cadence. On collecting a full-resync the box rewinds its cursors and raises a
wake, so the replay starts on the next tick (seconds) instead of after a full interval.
A box that is offline collects it whenever it comes back — the directive is not lost.

### Continuous sync without a broker

The box auto-syncs simply by being up: the in-process scheduler runs a cycle at
`RMC_EDGE_SYNC_INTERVAL_SECONDS` (default 180s, floor 60s), driven off the `/health/`
tick and ordinary page loads — no Celery worker, no beat, no cron. The entrypoint also
fires one reconcile on every boot, so a power-loss recovery syncs immediately.

For near-instant cloud→box, run the long-poll watcher on the box:

```bash
python manage.py edge_sync_watch
```

Or, for a broker-less cron instead of the in-process scheduler:

```cron
*/5 * * * * cd /path/to/app && python manage.py edge_autosync >> /var/log/rmc-edge-sync.log 2>&1
```

`edge_autosync` takes no arguments — it resolves the box's own school itself.

---

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
- **Paired but not syncing?** Run `verify_edge_link` on the box. The usual answer is the
  `scheduler` line: nothing is driving cycles because `/health/` is never reached and no
  page is being loaded. Run `edge_autosync` from cron, or point a monitor at `/health/`.
- **The pairing screen is gone.** Correct — a box seals itself after its first pairing,
  so `/edge/pair-this-box/` stops serving anonymous callers on the LAN. Re-pairing needs an
  authenticated admin on the box or `pair_box --unpair --yes` at a shell, either of which
  proves more than merely being on the network does.
- **Approved the code but the box did not notice?** It polls every few seconds; give it
  one interval. If it still has not collected, the box cannot reach the cloud — the
  pairing poll uses the same path as sync, so `verify_edge_link --http` will say why.
- **Box reports a 502 on push and pull?** Almost certainly NOT the box. A 502 is the
  cloud's proxy answering because the application behind it did not. The cause seen in
  production is **schema drift on that one tenant**: `apps.academics` is a TENANT app,
  so a column like `academics_academicyear.is_soft_closed` arrives per schema via
  `migrate_schemas --tenant` and can land for some tenants and not others. Because
  `academic_year` is a synced entity and building a bundle selects every field, one
  missing column raises `ProgrammingError` on every bundle build → 500 → 502. On the
  cloud run `python manage.py check_edge_sync_deploy_readiness`; it names the schema,
  the table and the columns. Fix with `python manage.py migrate_schemas --tenant`.
  Do **not** start by changing `RMC_EDGE_OPERATOR_BASE` — from the box, a tenant one
  column behind is indistinguishable from a cloud that is down.
- **Box reports a 404 with a page of HTML in it?** The path is wrong, not the host.
  Every `sync-*` route lives in `apps.api.urls`, mounted at `/api/` — `/api/v1/` is a
  different module with no sync routes. `verify_edge_link --http` reports this as
  "reachable, but the sync endpoint is missing".
- **Queued a resync and nothing happened?** The panel distinguishes *requested* from
  *delivered*. Still on "requested" means the box has not called home: it is off,
  offline, or cannot reach the cloud. It is not lost — the directive waits.

# Getting a platform upgrade from the cloud onto a school's box

**Status:** design + the parts that are built. Written 2026-08-22 after an operator
reported four bugs, **two of which had already been fixed in `main` days earlier** and
had reached neither the cloud nor the box.

---

## Read this before designing anything

The pipeline below is worth building. It is not what is broken today.

```
GitHub Actions, every workflow on main, 2026-08-22T14:14Z:
  "The job was not started because an Actions budget is preventing further use."
```

Eight workflows. All red. **None of them ran.** No test executed, no image built, no
deploy fired. The last job of any kind ran on **2026-08-15**.

So:

| Symptom the operator reported | Fixed in `main` | Why they still saw it |
|---|---|---|
| PIN dialog says "Local access could not be enabled on this browser" | `8736903db`, 2026-08-20 | never deployed |
| `guided-onboarding/execute-launch/` 500 on the cloud | `400416541`, 2026-08-19 | never deployed |

Two of the four reports were **delivery** defects wearing the costume of product
defects, and the most expensive part was not the outage — it was that three engineers
went looking in the product. Nothing in the system could say "the code you are looking
at is not the code that is running."

**`python manage.py deployment_parity --against <cloud-url>` now can.** It is the
smallest useful piece of this whole document and it is built:

```
THIS DEPLOYMENT
  code    commit_sha      475624840…
  assets  service_worker  sms-v4.06.78-…-2026-08-21
  schema  applied_migrations   1277 across 59 apps (digest fd875dfd…)
```

Pay the Actions bill first. Then build the rest.

---

## What the shape of this system already decides for you

Three facts constrain the design more than any preference does.

**1. The box is a container, not a filesystem.** `deploy/selfhost/docker-compose.yml`
+ `Dockerfile`. The unit of update is an **image digest**, not a set of changed files.
This matters because the obvious design — ship file deltas, `collectstatic`, swap a
symlink, reload gunicorn — is the *wrong shape* for a container appliance and buys
nothing: a container that has had files swapped underneath it is no longer the thing
its digest says it is, and the next `docker compose pull` silently reverts your work.
Content-addressed layers already give you deduplication, atomicity and rollback; the
job is to *drive* them, not to reimplement them one file at a time.

**2. A transport already exists, and adding a second one will get you firewalled.**
The box already talks to the cloud over HTTPS on `/api/sync/…` with a bearer
credential and HMAC-signed bundles (`apps/sync_engine/cloud_endpoints.py`,
`pairing_client.py`). School networks are hostile to new ports and unknown hosts. The
update channel must be the sync channel.

**3. A box can be weeks behind, which breaks the textbook.** The standard answer to
coordinating code and schema is
[expand/contract](https://blogs.reliablepenguin.com/2025/11/16/database-migrations-without-drama-expand-contract-in-practice):
expand the schema so old and new code both work, migrate, then contract. It assumes
the window between the two is short — minutes, a deploy. A sovereign box on a metered
link in a school that closed for the holidays can be **months** behind. Expand/contract
alone cannot carry that; something has to refuse the sync rather than silently
converge two incompatible schemas.

---

## The design

### The compatibility floor is the load-bearing part

Everything else is plumbing. This is the idea that makes the rest safe.

The cloud declares the **oldest box version it will still exchange data with**. A box
below the floor is not synced — it is told to update, and its data is held, not
discarded. That single rule converts an unbounded compatibility matrix (any box
version × any cloud version) into a bounded one (anything from the floor forward), and
it is what lets expand/contract work across a months-long window: a migration may only
contract once the floor has moved past every version that still read the old column.

```
    cloud release N
        │
        ├── compat_floor = N-6        "I will still sync with anything from N-6"
        │
        ├── box @ N-2   → sync normally
        ├── box @ N-6   → sync normally, nudge to update
        └── box @ N-9   → SYNC REFUSED. Update first. Data held, nothing lost.
```

A refused sync is a **good outcome**. The alternative — accepting a bundle a box will
apply with logic that no longer matches the schema it is applying into — is the
split-brain the operator would spend a week untangling.

### The handshake

The box already sends its cursor. It gains one field:

```python
"system_environment": {
    "commit_sha": "...",           # deploy_meta.resolve_deploy_commit_sha()
    "schema_digest": "...",        # deployment_parity.schema_fingerprint()["digest"]
    "release": "2026.08",          # RMC_RELEASE_VERSION
    "image_digest": "sha256:...",  # what the container actually is
}
```

All four already exist locally; `apps/sync_engine/deployment_parity.py` computes
three of them today. The cloud compares against its own and answers with one of:

- `IN_PARITY` — proceed, nothing to do.
- `UPDATE_AVAILABLE` — proceed with the sync, and here is a manifest.
- `UPDATE_REQUIRED` — **do not sync**, you are below the floor.

### The rollout on the box

Adapted from the pattern [Mender and balena](https://mender.io/resources/reports-and-guides/ota-updates-best-practices)
use for A/B partitions, with the partition replaced by a container tag — because for a
container that is what an A/B partition *is*:

1. **Pull in the background.** `docker compose pull` on the new tag. The school keeps
   working on the running container the entire time. On a metered link this can take
   hours; that is fine, nothing is waiting on it.
2. **Verify before touching anything.** Image digest must equal the manifest's. A
   truncated download fails here, having changed nothing.
3. **Back up.** `pg_dump` (or the SQLite file) plus the current image tag recorded in
   `EdgeDeploymentHistory`. **You cannot roll a migration back; you can only restore.**
   Any design that claims rollback without a backup is claiming something false.
4. **Migrate.** `migrate` on the new image. Django wraps each migration in a
   transaction on Postgres, so a failure inside one is atomic — but a failure in
   migration 7 of 12 leaves 6 applied. That is what step 3 is for.
5. **Health check, then switch.** New container up, `/health/` must answer, then
   traffic moves. `deploy/selfhost/docker-compose.yml` currently healthchecks only
   `db` — the web service needs one before any of this is safe.
6. **Watchdog.** No healthy response within 60s → restore the previous tag and the
   backup, and report. A failed update must never leave a school with a dead terminal
   at 08:00 on a Monday.
7. **Report back.** New fingerprint to the cloud, which lifts the hold and lets the
   held journals replay against the schema they were meant for.

### Where the tenant sits in the cascade

The brief this design answers proposed operator → tenant → box, with each tenant
re-packaging for its own boxes. **Do not build that.** In this system a "tenant" is a
Postgres schema inside the cloud, not a deployment — it has no filesystem, runs no
container, and cannot host a staging bucket. The three-tier packaging cascade would be
inventing a middle tier that does not exist in order to have something to put in it.

The real cascade is **two tiers with per-tenant policy**:

```
Operator (cloud)  ──── builds ONE image, publishes ONE manifest
      │
      │  per-tenant CHANNEL + WINDOW  (data, not a rebuild)
      │     · channel: stable | beta | pinned
      │     · window:  "not during exams", "Sundays 02:00", "never automatically"
      ▼
  Box (school)    ──── pulls, verifies, migrates, switches, reports
```

The tenant tier is where **policy** lives, not packaging. A school in exam week and a
school on holiday need different timing for the *same* image — and a school that has
never bought a box needs nothing at all. That is a row in the database, not a build
pipeline.

---

## What the competition does here

Worth being precise, because it is the strategic point.

[PowerSchool](https://www.trustradius.com/compare-products/on-products-vs-powerschool-student-information-system),
[Blackbaud](https://www.trustradius.com/compare-products/on-products-vs-veracross) and
[Veracross](https://www.veracross.com/resources/veracross-vs-powerschool/) are
cloud-only SIS products. PowerSchool describes itself as "fully web-based … with
real-time updates on any operating system, browser or device." Their update story is
therefore the easy one: they update the only copy that exists, and every customer gets
it simultaneously.

**None of them publishes an offline/on-prem story at all.** That is not an oversight;
it is a segment they have declined. A school with four hours of grid power a day and a
3G dongle is not a customer they can serve.

So the advantage is not "we also have OTA." It is:

> **They cannot run without connectivity. We can — and we can still be upgraded.**

That second clause is the whole moat, and it is the clause this pipeline exists to
make true. A sovereign box that cannot be updated is not a feature; within two years
it is a liability with a school's data on it. The competitor comparison that matters is
not PowerSchool's release notes — it is
[Mender and balena](https://proteanos.com/doc/ota-updates-rauc-swupdate-mender-2026/),
who solved fleet updates for embedded Linux, and whose designs are worth copying
directly rather than re-deriving.

---

## Build order

Ordered by what is worthless without the thing above it.

| # | | Status |
|---|---|---|
| 0 | **Pay the GitHub Actions bill.** Nothing below ships while no job can start. | **blocked, external** |
| 1 | `deployment_parity` — say what each side is running | **built** |
| 2 | Web-service healthcheck in `docker-compose.yml` | not built |
| 3 | `EdgeDeploymentHistory` — what ran, when, what it replaced | not built |
| 4 | `system_environment` in the sync handshake + `compat_floor` | not built |
| 5 | Backup → migrate → healthcheck → switch → watchdog on the box | not built |
| 6 | Per-tenant channel + maintenance window | not built |
| 7 | Signed manifests (cosign; the release workflows already sign images) | partly built |

**2 and 3 before 5.** A rollout with no healthcheck cannot detect failure, and a
rollout with no history cannot name what to go back to — building the switchover first
would produce a mechanism that can break a school and not un-break it.

---

## Three rules that keep this from eating a school

**Never open a second channel.** No SSH, no rsync, no new port. School firewalls block
what they do not recognise, and the failure mode is a box that cannot be updated
*precisely* in the environments that most need it. Wrap the payload in the sync frame
that already works.

**Never let the box decide it is fine.** The box reports its fingerprint; the *cloud*
decides whether that is acceptable. A box that self-certifies will, on the day its
clock or its build stamp is wrong, cheerfully sync itself into corruption. This is
also why `deployment_parity` treats an unreachable remote as UNKNOWN and never as
agreement.

**Never promise rollback you cannot deliver.** Code rolls back — it is a tag. Schema
does not. `EdgeDeploymentHistory` must record the backup that a restore would use, and
if there is no backup the update must not start. The honest word for step 3 is
*restore*, and calling it *rollback* is how someone finds out at the worst moment.

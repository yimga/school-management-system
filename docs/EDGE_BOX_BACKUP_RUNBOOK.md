# Edge box backups: the school's own records

**Audience:** whoever looks after a sovereign box. **Length of the procedure you have
to remember: one line.** Everything else on this page is what the box already does.

---

## The failure this closes

A sovereign box replicates roughly seventeen entities to the cloud. Everything else a
school does on it — the fee ledger, the marks, the attendance, the discipline record,
the timetable, the uploaded documents — exists on **exactly one disk**, on hardware
chosen because it was affordable, in a school building. A dead SSD was total loss.

The box already knew how to protect something properly. Its TLS **certificate
authority** gets an encrypted backup, a passphrase deliberately kept apart from it, a
gate that fails the box when the backup is missing, a gate that fails when the backup
does not match the live CA, a gate that proves the encryption is real, and a gate that
fails when there is no verified read-back on record. That discipline was exactly right
and it was being applied to a certificate while the children's records got nothing.

This is the same discipline, applied to the records.

---

## What happens without anyone doing anything

`docker compose -f deploy/selfhost/docker-compose.yml up -d` starts a `backup`
service. It is **not** behind a profile: the terminator is opt-in because a school may
reasonably run plain HTTP on its own LAN, but no school reasonably chooses to hold the
only copy of its fee ledger.

| | |
|---|---|
| **Nightly** | `pg_dump --format=custom` of the whole database, streamed straight into `openssl enc -aes-256-cbc -pbkdf2 -iter 200000`. The plaintext never exists as a file. |
| **Then, every time** | The dump is **read back before it counts**: decrypted, checked for the `PGDMP` magic, its table of contents listed and checked against the migrations table and a floor on entry count, and then read **end to end** through `pg_restore -f /dev/null` — which decompresses every data block without touching any database. A dump truncated by a full disk decrypts fine, lists fine, and fails here. |
| **And** | A **wrong** passphrase is tried on purpose. It must not produce a Postgres archive. That is what proves the encryption is real rather than merely configured. |
| **Then** | A dump that will not read back is **deleted**, and the last verified one is left alone. It is not a backup, and keeping it would let retention count it as one. |
| **Then** | Retention prunes, and a hard byte cap prunes further. The newest verified dump is never pruned by either rule. |
| **Then** | The dump is copied to the off-box target, if one is configured. |
| **Weekly** | An encrypted `tar` of the media tree — if it fits (see *Media*, below). |
| **Monthly** | A **full restore drill**: the dump is restored into a scratch database and rows are counted, proving Postgres accepts it and not merely that the archive reads. Gated on measured free space; skipped, on the record, with the numbers, when it cannot afford to run. |
| **Always** | Everything above is written to a record at `/backups/backup-state.json`, which is what `box-audit.sh` gates on. |

It runs in its own container, on the same image `db` already runs, so it **adds no new
bytes to pull** on a box that is offline in a school building. It has no healthcheck
and nothing depends on it, so it cannot take the box down; every write is preceded by
a measured free-space check that skips the run rather than filling the disk.

---

## The three decisions that are actually yours

### 1. Where the off-box copy goes — the only one that matters

Everything above lives on the box's single disk. It protects against a bad migration,
a wrong delete and a lost `pgdata` volume. It does **not** protect against the disk
dying, which is the failure a school in a building actually suffers.

Put a USB disk or a NAS mount somewhere, then in `deploy/selfhost/.env`:

```env
RMC_BOX_BACKUP_OFFBOX_DIR=/mnt/usb/rmc-backups
```

Absolute path. That is the whole configuration; every run copies itself there, with
the same retention, and prunes there too so a USB stick cannot be filled either.

`box-audit.sh` compares filesystems and will tell you which of the two you have:

```
[ OK ] the off-box copy is on a DIFFERENT filesystem -- it survives this disk
[WARN] the off-box copy is on the SAME filesystem as the box itself: a dead disk
       takes both.
```

The default is a named docker volume — on the same disk, and named rather than
pretended about, precisely so that warning is honest.

### 2. Take a copy of the passphrase off the box

The box generates one on its first run and keeps it in a **volume of its own**, so
`docker compose cp backup:/backups .` carries the dumps off this machine without
carrying the key that opens them. That separation is the point, and it is the same one
`edge-bootstrap.sh` asks for between the CA bundle and its passphrase.

```bash
docker compose -f deploy/selfhost/docker-compose.yml exec backup \
  bash /usr/local/bin/box-backup.sh export-key
```

Store it where you store the CA passphrase. **Without it every dump on the box is
unreadable, and it cannot be regenerated from the database.** Never change it
afterwards: a second passphrase re-encrypts nothing and silently strands every copy
already carried off the box — which you would discover during a restore, the worst
moment to discover anything.

The audit warns while the key is still sitting beside the backups it opens.

### 3. Whether the media tree fits

See *Media*, below. If the audit says media is being skipped, that is a decision
waiting for you, not a fault.

Optionally, set `TZ` so the quiet window means what you think it means. A box in Buea
is UTC+1; leaving it alone shifts the backup by an hour, which is harmless.

---

## Retention, and the disk bound

Two bounds, applied in that order, and **whichever binds first wins** — a bigger
school keeps fewer dumps rather than filling the disk.

**By age (grandfather-father-son, overlapping).** Keep the newest dump of each of the
last 7 days, of each of the last 4 weeks, and of each of the last 3 months. Buckets
overlap: today's dump is today's daily *and* this week's weekly *and* this month's
monthly, and it is one file either way.

Measured against 400 synthetic daily dumps, that settles at **11 files** — the last
seven days, two weekly boundaries, two month-ends. The theoretical maximum is 12.

**By bytes.** `RMC_BOX_BACKUP_MAX_BYTES`, default 4 GiB, prunes oldest-first until the
total fits. The newest verified dump is kept even if it alone exceeds the cap: a
retention rule that can delete the only backup is worse than no retention rule.

### The arithmetic, with its assumptions stated

`pg_dump --format=custom` is already zlib-compressed, so these are compressed sizes.

| | |
|---|---|
| Assumed dump size, school of ~2,000 students | **150 MiB** (generous; documents live in media, not in the database) |
| Steady state, 11 dumps | **~1.6 GiB** |
| Transient during a run: + the new dump + one decrypted verify copy | **~1.9 GiB peak** |
| Database cap (`RMC_BOX_BACKUP_MAX_BYTES`) | 4 GiB → the age policy binds first until a dump exceeds ~370 MiB |
| Media archive, one copy (`RMC_BOX_BACKUP_MEDIA_MAX_BYTES`) | 2 GiB ceiling, ~4 GiB transient during the swap |
| Floor never touched (`RMC_BOX_BACKUP_MIN_FREE_BYTES`) | 1 GiB |
| **Worst case on disk** | **~8 GiB** |

**The estimate is not a constant.** Before each run the service uses the size of the
dump *this box* actually produced last time, and requires `2 × that + 1 GiB` free. A
school of 300 and a school of 3,000 are an order of magnitude apart and neither should
be told the other's number. Below the threshold, the run **skips itself**, records the
measured numbers, and tries again next poll:

```
[backup] SKIPPED: only 612368384 bytes free, need 1610612736 (2 x 268435456 estimate
         + 1073741824 floor)
[backup] This is deliberate. Filling the disk stops Postgres writing and takes the
         school offline, which is worse than the missed backup it would have bought.
```

Raise the caps only after checking the disk has the room. The box will not check it
for you and it will not stop you.

---

## Restoring

One command, on the host. It stops the writers, restores, and starts them again — on
**every** exit path, including a Ctrl-C, because a box left stopped is a school with
no system at all.

```bash
bash deploy/selfhost/box-restore.sh --list                       # what is available
bash deploy/selfhost/box-restore.sh --yes-destroy-current-data   # newest
bash deploy/selfhost/box-restore.sh --file rmc-box-db-20260830T020000Z.dump.enc \
     --yes-destroy-current-data
```

Why a script rather than a list of steps: the ordering *is* the procedure. Restoring
while gunicorn and celery are still writing gives you a database that is half
yesterday and half this morning, with no way to tell which rows are which. And this
gets run by somebody having the worst day of their term, usually in a corridor.

Three refusals are built in, and each is there because the alternative is worse:

- **without `--yes-destroy-current-data`** it refuses — there is no undo;
- it **reads the dump back before dropping anything** — no sense destroying a working
  database for a file we already know is broken;
- `pg_restore --single-transaction` means a failure **rolls back**, so a refusal
  leaves the database exactly as it was.

Migrations run on `web`'s boot, so a dump older than the running code is brought
forward simply by the app starting again. That is why the readiness check comes after
the restart, not before.

Two things a restore cannot do, and the banner says so: confirm the right dump was
chosen (a clean restore onto the wrong dump looks identical to a clean restore onto
the right one — have somebody who uses the system daily look), and tell you what was
entered between the backup and now.

---

## Verifying

`bash deploy/selfhost/box-audit.sh`, section **C2**. It is read-only: it asks the
backup container what it has **recorded**, exactly as section C asks the trust anchor
for its recorded export. It never takes a backup and never restores one.

Three of its findings are the gate — a FAIL there flips the whole audit's verdict:

| The audit says | What it means |
|---|---|
| `no verified read-back on record -- this box cannot show its backup was ever read back` | There is no evidence any dump here has ever been opened. It is a file, not a backup. |
| `the verified read-back is for X, not the newest dump Y` | The newest dump has never been opened. Something is failing after the dump and before the check. |
| `the dump was listed but never read END TO END` | A truncated archive lists perfectly and restores nothing. |
| `NO BACKUP RECORD on this box` | It has never run. Check `docker compose logs backup`. |
| `the backup service is 'absent'` | Nothing is copying this school's database at all. |
| `the dump OPENS with a wrong passphrase` | It is not actually encrypted. |
| `only N bytes free -- the next run will skip itself` | Free space, or lower the caps. |

On demand, without waiting for the schedule:

```bash
docker compose -f deploy/selfhost/docker-compose.yml exec backup \
  bash /usr/local/bin/box-backup.sh once     # back up now, verify, prune
  #                                  verify  # re-read the newest one back
  #                                  drill   # full restore into a scratch database
  #                                  status  # the record box-audit.sh reads
  #                                  list    # what is on disk, newest first
```

---

## Media: the decision, stated

**Media is backed up** — uploaded documents, photographs, evaluation evidence and
receipts are as irreplaceable as any row, and leaving them out would have left exactly
the hole this service was built to close.

**But not on the same terms as the database**, for two reasons that are about this
hardware rather than about principle:

- it is the bulkiest thing on the box by an order of magnitude, and eleven rolling
  copies of an image tree would fill a mini-PC's disk on its own;
- a photograph usually still exists on the phone that took it and a scanned document
  usually still exists on paper. A fee ledger exists nowhere else.

So: **weekly** rather than nightly, **one** copy rather than eleven, uncompressed
(photographs and PDFs are already compressed; gzip would buy a rounding error and cost
an hour of a mini-PC's CPU), encrypted the same way, read back the same way, and the
**first thing dropped when space is short**.

When it is skipped it is skipped *on the record*, with the measured size and the cap
in the message, so nobody discovers the omission during a restore:

```
[backup] media SKIPPED: media is 7516192768 bytes, over the 2147483648 cap
[backup] raise RMC_BOX_BACKUP_MEDIA_MAX_BYTES only if the disk can carry it, or copy
         /media-src off the box by another route. It is NOT being backed up today.
```

`RMC_BOX_BACKUP_MEDIA=on` forces it (still space-gated — nothing here may fill the
disk); `off` disables it.

---

## What it deliberately does not back up

**`deploy/selfhost/.env`.** The backup container is given the database and the media
tree and nothing else — it never sees `SECRET_KEY`, the cloud credential, or the CA
passphrase. That is on purpose: a backup service that holds every secret on the box is
a second copy of the blast radius.

So `.env` is the other half of your backup. **Keep a copy of it wherever you keep the
backup passphrase.** Without it a restore onto fresh hardware still needs the database
password and `SECRET_KEY` re-supplied.

Database **roles** are also not in the dump (`pg_dump`, not `pg_dumpall`). They are
recreated by the compose file from `POSTGRES_USER` / `POSTGRES_PASSWORD` in that same
`.env`, which is one more reason to keep it.

---

## Related

- [`docs/DR_BACKUP_RESTORE_RUNBOOK.md`](DR_BACKUP_RESTORE_RUNBOOK.md) — the cloud/
  multi-tenant side, and the independent-store tiers this box's off-box target maps on to.
- [`docs/EDGE_TLS_RUNBOOK.md`](EDGE_TLS_RUNBOOK.md) — the CA backup whose discipline
  this copies.
- `deploy/selfhost/box-backup.sh`, `deploy/selfhost/box-restore.sh`,
  `deploy/selfhost/box-audit.sh` section C2.

# DR self-host restore runbook — tenant immutable snapshots

**Audience:** a school operator (or RunMyCampus on-call) recovering a single
tenant's core configuration from an immutable daily snapshot — on the platform,
or onto a self-hosted / freshly provisioned RunMyCampus instance.

**Scope of this runbook:** the *application-level* immutable snapshot produced by
`apps/lifecycle/tenant_dr_snapshot.py`. This is distinct from, and complementary
to, the *cloud-backup* drill in `scripts/restore_drill.py` (which restores a full
Render Postgres backup into a side DB). Use the cloud backup for a total-loss
full-database recovery; use **this** snapshot to rebuild a single tenant's config
core onto a clean instance, or to verify recoverability without touching prod.

---

## 1. What the snapshot contains (honest scope)

Each snapshot is a gzip-compressed, **HMAC-SHA256-signed** JSON document. The
signing key is derived from the platform `SECRET_KEY` mixed with the school id,
so a blob is cryptographically bound to both the platform secret and the owning
tenant. Tamper, wrong key, or wrong tenant → the restore **fails closed before
any database write**.

Payload `schema_version` is `2.0`. It carries two things:

| Key | Meaning |
|---|---|
| `counts` | Aggregate row counts (memberships, students, teachers, invoices, payments). Kept for a cheap post-restore sanity check. |
| `tables` | **Real, restorable row data** for the self-contained tenant config core, serialized with Django's `json` serializer (preserves dates / decimals / JSON / FK-by-pk). |

### Restored automatically (the config core)

These tables are self-contained — no dependency on the auth `User` table / PII,
and no `PROTECT` foreign key to an out-of-scope parent — so they restore cleanly
into an empty target tenant:

| Table | Natural key (idempotency) | FK handling on restore |
|---|---|---|
| `schools.School` (the tenant row) | `slug` (upsert) | — |
| `academics.AcademicYear` | `school` + `name` | — |
| `academics.Department` | `school` + `code` | — |
| `academics.Term` | `school` + `academic_year` + `name` | `academic_year` remapped to restored parent |
| `academics.Classroom` | `school` + `code` | `academic_year`, `department` remapped |
| `people.StudentProfile` | `school` + `student_code` | `user` FK **cleared** (re-link out of scope) |

Intra-snapshot foreign keys are rewritten to the freshly restored parent pks, in
dependency order, so the restored graph is internally consistent. Restore is
**idempotent**: re-running it upserts by natural key rather than duplicating rows.

### Captured for counts, but NOT auto-restored (roadmap)

Honest about the gaps — these are visible in `counts` but are **not** in `tables`
and are **not** materialized by `restore_from_snapshot`:

- **`people.TeacherProfile`** — has a non-nullable `OneToOne` to the auth `User`.
  Restoring it requires restoring users first, which pulls in the auth/PII
  surface and a credential-recovery story. Deferred.
- **`finance.Invoice` / `finance.Payment`** — `Invoice` has `PROTECT` foreign
  keys to `ComplianceProfile` and `Counterparty`, which are out of the current
  self-contained scope. Restoring the financial ledger needs those parents and a
  reconciliation pass. Deferred.
- **Attendance, grades/evaluations, messaging, files/media** — not captured.

This snapshot is therefore a **config-core recovery**, not a full tenant clone.
Treat it as "rebuild the school's structural skeleton (years, terms, classes,
students) on a clean instance", then re-onboard staff + finance separately.

---

## 2. Where snapshots live

`capture_daily_snapshot` writes two copies plus an optional object-storage copy:

- **Primary:** `var/tenant_snapshots/primary/<slug>_<YYYY-MM-DD>.json.gz`
- **Secondary:** `var/tenant_snapshots/secondary/<slug>_<YYYY-MM-DD>.json.gz`
- **Object storage (optional):** when `TENANT_SNAPSHOT_S3_BUCKET` is set, also
  uploaded to `s3://<bucket>/tenant_snapshots/<slug>/<YYYY-MM-DD>.json.gz`.

Metadata for each snapshot (paths, `payload_sha256`, `signature_hex`,
`byte_size`) is recorded in the `TenantImmutableSnapshot` table. The
`signature_hex` from that row is the **expected signature** you pass to restore.

---

## 3. Download the master file

On the source/platform side, find the latest snapshot row and its signature:

```bash
python manage.py shell -c "
from apps.lifecycle.models_dr_snapshot import TenantImmutableSnapshot
row = (TenantImmutableSnapshot.objects
       .filter(school__slug='your-school-slug')
       .order_by('-snapshot_date','-created_at').first())
print('primary  :', row.primary_uri)
print('secondary:', row.secondary_uri)
print('sha256   :', row.payload_sha256)
print('signature:', row.signature_hex)
print('school_id:', row.school_id)
"
```

Copy the `.json.gz` file (primary, or pull the secondary from S3) to the target
machine. Record the `signature_hex` and `school_id` — you need both to restore.

If pulled from S3:

```bash
aws s3 cp "s3://$TENANT_SNAPSHOT_S3_BUCKET/tenant_snapshots/your-school-slug/2026-06-26.json.gz" ./snapshot.json.gz
```

---

## 4. Verify the signature (fail closed)

**Do this before any restore.** Verification is the same function the restore
path calls first; a mismatch means the file was tampered with, corrupted, or
signed under a different `SECRET_KEY` — do not proceed.

> Verification requires the **same `SECRET_KEY`** the snapshot was signed with.
> Self-hosting under a *new* secret means you cannot verify legacy blobs — keep
> the original platform `SECRET_KEY` available (sealed) for DR, or re-sign during
> a controlled migration. This is a deliberate security property, not a bug.

```bash
python manage.py shell -c "
from pathlib import Path
from apps.lifecycle.tenant_dr_snapshot import verify_signature
data = Path('snapshot.json.gz').read_bytes()
ok = verify_signature(data, 'PASTE_signature_hex', school_id='PASTE_school_id')
print('signature_ok =', ok)
assert ok, 'SIGNATURE MISMATCH — refusing to restore'
"
```

---

## 5. Restore into a working school

`restore_from_snapshot` verifies the signature again (belt-and-suspenders),
parses the payload, then materializes the config-core tables inside a single
transaction. Pass a `target_school` to restore onto a freshly provisioned tenant
(self-host), or omit it to upsert the original `School` row by slug on the same
platform.

### 5a. Self-host: restore onto a fresh, empty tenant

```bash
python manage.py shell -c "
from pathlib import Path
from apps.schools.models import School
from apps.lifecycle.tenant_dr_snapshot import restore_from_snapshot

# Create (or pick) the empty destination tenant on this instance.
target, _ = School.objects.get_or_create(
    slug='your-school-slug',
    defaults={'name': 'Your School', 'subdomain': 'your-school-slug'},
)

result = restore_from_snapshot(
    Path('snapshot.json.gz'),
    school_id='PASTE_source_school_id',   # the id the blob is signed for
    expected_sig='PASTE_signature_hex',
    target_school=target,
)
print('target_school_id =', result['restored']['target_school_id'])
for table, c in result['restored']['tables'].items():
    print(f'  {table}: +{c[\"created\"]} created, {c[\"updated\"]} updated')
print('source counts    =', result['counts'])
"
```

### 5b. Same-platform: upsert the original tenant row by slug

Omit `target_school`; the School config row in the snapshot is upserted by slug
and used as the destination:

```python
restore_from_snapshot(
    Path('snapshot.json.gz'),
    school_id='PASTE_source_school_id',
    expected_sig='PASTE_signature_hex',
)  # target_school defaults to None -> upsert School by slug from the snapshot
```

Because restore is idempotent, running it twice is safe — the second pass reports
`updated` instead of `created`.

---

## 6. Confirm a working school

After restore, sanity-check against the snapshot's `counts` and spot-check rows:

```bash
python manage.py shell -c "
from apps.academics.models import AcademicYear, Term, Classroom
from apps.people.models import StudentProfile
from apps.schools.models import School
s = School.objects.get(slug='your-school-slug')
print('years     :', AcademicYear.objects.filter(school=s).count())
print('terms     :', Term.objects.filter(school=s).count())
print('classrooms:', Classroom.objects.filter(school=s).count())
print('students  :', StudentProfile.objects.filter(school=s).count())
"
```

The student / academic-year / classroom counts should match the config-core
portion of the snapshot's `counts`. (TeacherProfile / finance counts will read 0
until those roadmap surfaces are recovered separately — see §1.)

Then log in to the tenant and verify the academic structure (years → terms →
classes) and the student roster render. Re-link staff users and re-import finance
out of band.

---

## 7. Verify recoverability WITHOUT touching prod (drill)

A Celery task performs a real (non-dry-run) restore of a tenant's latest
snapshot inside a transaction that is **always rolled back** — proving the
restore path works end-to-end without mutating production data:

```bash
python manage.py shell -c "
from apps.lifecycle.tasks_dr_snapshot import verify_tenant_snapshot_restore_integrity
from apps.schools.models import School
sid = str(School.objects.get(slug='your-school-slug').pk)
print(verify_tenant_snapshot_restore_integrity(sid))
"
```

`ok=True` with per-table created counts means the snapshot is genuinely
restorable. This is the application-snapshot analogue of `scripts/restore_drill.py`
(which drills the cloud-backup path); both should be exercised on the DR cadence
in `var/dr-drill-schedule.json`.

---

## 8. What this runbook does and does NOT prove

- ✅ The config core (school → years → terms → departments → classrooms →
  students) is captured as real rows and restores onto a clean instance.
- ✅ Restore is signature-verified (fail-closed), transactional, and idempotent.
- ✅ Recoverability can be drilled without mutating production.
- ❌ It does **not** restore staff users, finance ledger, attendance, grades,
  messaging, or media — those are roadmap (see §1).
- ❌ It does **not** stand up application runtime (web/worker processes, DNS,
  TLS, env config). "Working school" here means *the tenant's data skeleton is
  present and consistent on a running instance*, not a turnkey cloud bring-up.

# Disaster Recovery Runbook (P12)

**Audit date:** 2026-05-17
**Pillar:** P12 — 12-pillar platform audit (DR / restore slice)
**Schedule:** [var/dr-drill-schedule.json](../var/dr-drill-schedule.json) — 90-day cadence; next drill due **2026-08-15**.
**History:** [docs/generated/dr_drill_log.json](../docs/generated/dr_drill_log.json)
**Verifier:** [scripts/verify_dr_drill_schedule.py](../scripts/verify_dr_drill_schedule.py)
**Restore tool:** [scripts/restore_drill.py](../scripts/restore_drill.py)

**Companion:** [docs/DEPLOY_PIPELINE_RUNBOOK.md](DEPLOY_PIPELINE_RUNBOOK.md) — covers the forward deploy path; this runbook covers the reverse recovery path.

---

## 1. Recovery targets

| Metric | Target | Source |
|---|---|---|
| **RTO** (Recovery Time Objective) | ≤ 4 hours | `var/dr-drill-schedule.json::rto_max_hours` |
| **RPO** (Recovery Point Objective) | ≤ 1 hour | `var/dr-drill-schedule.json::rpo_max_hours` |
| **Drill cadence** | Every 90 days | `var/dr-drill-schedule.json::cadence_days` |

Render's managed Postgres provides:
- Continuous WAL streaming → PITR window typically 7 days (operator-configurable).
- Daily automated snapshots, retained per Render plan tier.

---

## 2. Failure scenarios + response

### 2.1 Application-tier outage (Render service crash / deploy gone wrong)

**Symptoms:** `manager.runmycampus.com` 500s; status page red; Sentry alert storm.
**RTO target:** ≤ 30 minutes.

1. Confirm Render service status: `gh api repos/anthropics/runmycampus/deployments` (or Render dashboard).
2. If the bad deploy is the most recent: **roll back** via Render dashboard → Deploys → "Rollback to previous".
3. If the rollback fails: re-deploy the last green commit explicitly via `git push origin <sha>:main`.
4. Run `bash scripts/release/render_predeploy.sh` against the rolled-back env to confirm clean (memory `deploy_safety_net_v3_15`).
5. Post-mortem: append a `PlatformIncident` row + fill `lessons_learned` within 14 days.

### 2.2 Database corruption (logical — bad migration / bad mass UPDATE)

**Symptoms:** Constraint errors at runtime; financial reports inconsistent; users report stale or wrong data.
**RTO target:** ≤ 2 hours.

1. **STOP traffic** to the affected tenant (or all tenants if platform-wide): set `school.is_frozen=True` + display maintenance page.
2. Take a logical dump of the current (corrupt) state for forensics: `pg_dump --schema-only && pg_dump --data-only --table=<affected>`.
3. Identify recovery target time (last-known-good point — likely just before the bad migration ran).
4. From Render dashboard → Backups → PITR — initiate restore to a side database.
5. Diff the restored side DB vs the affected tables. Cherry-pick rows or full-table replace.
6. Run `python manage.py verify_all_migrations_applied --strict` to confirm migration state matches code.
7. Resume traffic; monitor.

### 2.3 Database total loss (Render incident / region outage)

**Symptoms:** Render Postgres unreachable for > 15 minutes; status page incident.
**RTO target:** ≤ 4 hours (hard RTO).
**RPO target:** ≤ 1 hour (worst case — last WAL checkpoint).

1. Spin up replacement Postgres instance (Render → New Postgres → same plan tier as current).
2. Restore from latest snapshot: Render → Backups → "Restore to new database".
3. Apply WAL up to most recent available timestamp.
4. Run `python manage.py migrate --check` + `python manage.py verify_all_migrations_applied --strict`.
5. Run `python manage.py seed_platform_complete --skip-tenants --continue-on-error` (idempotent — covers ~17 seed steps).
6. Update Render service `DATABASE_URL` env var to point at new DB; redeploy.
7. Smoke test: `curl https://manager.runmycampus.com/-/version/` returns 200 + matching SHA.
8. Resume traffic.

### 2.4 Tenant data deletion (tenant-scoped — admin error / GDPR right-to-erasure)

**Symptoms:** Tenant reports their data is "gone"; or a GDPR erasure request needs reversal.
**RTO target:** ≤ 24 hours.

1. Identify the tenant's `school_id`.
2. From last snapshot, restore that tenant's schema (in `django-tenants` mode) or filter-by-school_id selective restore.
3. Cross-check with [apps/security/audit_log.py](../apps/security/audit_log.py) — confirm what was deleted and by whom.

---

## 3. Drill protocol

**Quarterly (every 90 days).**

```bash
# 1. Validate the runbook against current code
python scripts/restore_drill.py --dry-run

# 2. Actually run a restore to a side DB and verify integrity
python scripts/restore_drill.py --apply --target-db dr-drill-$(date +%Y%m%d)

# 3. Verify integrity
python manage.py verify_all_migrations_applied --strict --database=dr-drill-$(date +%Y%m%d)
python manage.py check --database=dr-drill-$(date +%Y%m%d)

# 4. Append drill outcome
# Edit docs/generated/dr_drill_log.json — add an entry with completed_at, target_db, integrity_checks_passed.

# 5. Update next-due date
# Edit var/dr-drill-schedule.json — bump next_drill_due_by by 90 days.
```

**CI gate:** `python scripts/verify_dr_drill_schedule.py` fails when `today > next_drill_due_by` AND no in-window drill is logged. PRE-DEADLINE = passes by default until the date arrives.

---

## 4. Backup attestation

| Layer | Attestation method |
|---|---|
| Render Postgres snapshots | Render dashboard → Backups page (operator screenshot + date in [docs/generated/dr_drill_log.json](../docs/generated/dr_drill_log.json)) |
| WAL retention | Operator confirms via `SELECT pg_last_wal_replay_lsn();` + Render config |
| Static assets | Render persistent disk + offsite via `aws s3 sync` (operator-configured) |
| `var/`, `media/`, `staticfiles/` | Git-tracked where small; offsite for large media |

**Encryption at rest:** Render Postgres encrypts disk volumes by default (AWS-managed KMS). Backup snapshots inherit the encryption.

**Tenant-export integrity:** every export emitted by [apps/schoolops/views_tenant_ops.py](../apps/schoolops/views_tenant_ops.py) carries SHA-256 hash in the response headers + a footer row; operator stores the hash alongside the file for tamper detection.

---

## 5. Honest carve-outs

- **First scheduled drill is 2026-08-15** — 90 days after the v3.22 12-pillar closeout. No dry-run has been blessed as "production-ready" yet; the first drill is the first time a real Render PITR restore will be exercised.
- **Cross-region failover** — not configured. Render Postgres runs in a single region; loss of that region = ~4 hours to spin up in another region from snapshot. Multi-region active/active is a Tier-2 Lane-2 program item, not a repo deliverable.
- **Operator skill** — RTO assumes the operator on-call has run a drill before. The first real outage by someone who has never restored will be slower. Drill cadence is the mitigation.
- **External audit of DR procedure** — not on file. SOC 2 Type II audit (PATH_TO_100_PERCENT Tier 2) will assess this when scheduled.

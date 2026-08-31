# DR: backups, tenant schemas, restore drills

**Purpose:** Operator runbook for **schema-per-tenant** and platform DB continuity. Align with [PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md](PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md).

## RPO / RTO targets (set per environment)

| Tier | RPO (max data loss) | RTO (time to usable) | Notes |
|------|---------------------|----------------------|--------|
| **Production** | ≤ 24 h (adjust per contract) | ≤ 4 h (adjust per contract) | Document actuals after each drill. |
| **Staging** | Best effort | Best effort | Same *procedure* as prod, smaller data. |

## Backup scope (non-negotiable)

1. **Platform / shared schema** (where `django-tenants` + `public` schema or single DB) — all tables that hold platform configuration.
2. **Every tenant schema** — schools must not be dropped from backup scope; a “restore” that only restores `public` is **invalid** for multi-tenant SaaS.
3. **Object storage** — media buckets tied to tenants (if used).

## Workers and cron

- Any job that writes to the DB must run with **explicit tenant/schema context** (or `public` only for platform). Wrong connection = silent cross-tenant corruption.
- Add new jobs to the same review checklist as HTTP routes.

## Restore drill (quarterly or each release train)

1. Take a **non-prod** snapshot label from the same backup tooling as prod.
2. Restore to an isolated DB instance.
3. Run `manage.py migrate` and smoke tests against **at least two** tenant schemas + platform.
4. Record: date, operator, RPO/RTO observed, gaps.

## Related

- Single execution source: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md)

---

## Independent Store Classification (#28 / #22)

### What "independent store" means

A DR backup is only meaningful if the backup destination survives the failure
of the primary. Three tiers of independence:

| Tier | Description | Repo-provable? |
|------|-------------|---------------|
| **Ephemeral dual_dir** | Local filesystem directory; `DR_BACKUP_DUAL_DIR` env var | YES (CI can write + read) |
| **Independent volume** | Network-attached volume or managed DB snapshot (Render) | NO — requires cloud infra |
| **Cross-region S3** | S3 bucket in a different AWS region / GCS multi-region | NO — requires cloud infra |

### Environment variables for independent-store configuration

```env
# Ephemeral (CI / local dev) — proves the write path works
DR_BACKUP_DUAL_DIR=/tmp/rmc-dr-drill/

# Independent volume (production)
DR_BACKUP_S3_BUCKET=rmc-dr-backups-us-east-2
DR_BACKUP_S3_REGION=us-east-2
DR_BACKUP_S3_PREFIX=tenant-snapshots/

# Render-managed (production alternative)
RENDER_API_KEY=rnd_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
RENDER_POSTGRES_SERVICE_ID=srv-xxxxxxxxxxxxxx
```

### Verification

```bash
# Repo-contained proof (apply-local queries the configured DB)
python scripts/restore_drill.py --apply-local --json

# Independent-store classification
python scripts/verify_dr_independent_store.py

# Full cloud drill (EXTERNAL — requires Render API key)
python scripts/restore_drill.py --backup-ts 2026-07-19T12:00:00Z --apply
```

### What remains EXTERNAL

- **S3/volume backup writes**: Require `DR_BACKUP_S3_BUCKET` + AWS credentials
- **Render point-in-time restore**: Requires `RENDER_API_KEY` + side DB binding
- **Cross-region failover**: Cloud infrastructure decision, documented in
  `var/dr-drill-schedule.json` field `cross_region_failover_allowed`
- **Production restore verification**: Real tenant data recovery into a side instance

---

## Sovereign / edge boxes (self-hosted appliances)

Everything above assumes a hosted database an operator can reach. A **sovereign box**
is the opposite case: one school, one mini-PC, one disk, in a school building, usually
offline. It replicates roughly seventeen entities to the cloud, so the cloud backup
above covers a small fraction of what that school does, and none of its media.

Its backup is therefore **on the box, automated, and gated by the box's own audit** —
not a procedure an operator runs. Canonical page:
[`EDGE_BOX_BACKUP_RUNBOOK.md`](EDGE_BOX_BACKUP_RUNBOOK.md).

| | Cloud (above) | Sovereign box |
|---|---|---|
| Scope | platform + every tenant schema + object storage | the whole box database + the media tree |
| Runs | operator tooling / managed snapshots | `backup` service in `deploy/selfhost/docker-compose.yml`, nightly |
| At rest | provider-managed | `openssl enc -aes-256-cbc -pbkdf2`, key in a volume of its own |
| Read back | quarterly drill (below) | **every run**, `pg_restore -f /dev/null` end to end; full into-a-database drill monthly |
| Restore | `scripts/restore_drill.py` | `bash deploy/selfhost/box-restore.sh --yes-destroy-current-data` |
| Gate | `verify_dr_drill_schedule.py` | `box-audit.sh` section C2, which fails the box |

### Independent-store classification, for a box

The tiers in the section above apply, with one change: on a box the tier is
**measured, not declared**. The backup service compares the filesystem of its backup
volume against the filesystem of its off-box target and records the answer, and
`box-audit.sh` reports it:

| Tier | On a box | Repo-provable? |
|---|---|---|
| Same disk (default) | a named docker volume — protects against a bad migration, a wrong delete, a lost `pgdata` volume; **not** against the disk dying | NO — needs a running box |
| Independent volume | `RMC_BOX_BACKUP_OFFBOX_DIR` pointed at a mounted USB disk or a NAS share | NO — needs the mount |

A box that has not been given an off-box target is not misconfigured; it is a box
whose backups all live on the disk they are protecting, and it says so out loud.

### RPO / RTO on a box

RPO is the backup interval, default 24h, with one deliberate exception: a box switched
off overnight would never be inside the quiet window, so a backup more than half an
interval overdue runs regardless of the hour. RTO is a `pg_restore` of one dump plus
the app restarting — minutes, not hours, because there is no infrastructure to
provision.

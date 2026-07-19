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

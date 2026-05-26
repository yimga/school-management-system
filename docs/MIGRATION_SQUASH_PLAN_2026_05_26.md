# Migration Squash Plan — 6 high-migration apps

Plan only. **No squash is executed in this batch.** This document captures the preconditions and procedure so the operator can pull the trigger after the next stable production cutover tag.

## Apps in scope

| App | Migration count | Latest leaf (2026-05-26) | Risk profile |
| --- | ---: | --- | --- |
| `siteconfig` | 188 | `0186_sitesettings_email_delivery` | Highest — held the 7-layer config cascade, frequent additive fields; squash here is the most valuable but also touches every tenant |
| `platform_runtime` | 75 | `0075_ensure_admin_operator_profile` | High — IAM identity 10x lives here; many recent batches |
| `finance` | 66 | `0064_webhooklog_uniq_provider_bucket` | High — money tables; ledger correctness is non-negotiable |
| `people` | 57 | `0053_ensure_teacherprofile_updated_at_column` | Medium — heavy `User`/`StudentProfile` history, search GIN indexes |
| `schools` | 56 | `0057_school_primary_language` | Medium — every tenant joins on `School` |
| `academics` | 52 | `0049_alter_certificationfeetemplate_currency_and_more` | Medium — Term / Grade / Curriculum lineage |

## Hard preconditions before any squash runs

A squash is irreversible in practice. All of these must be true:

1. **Production cutover tag exists.** A specific commit SHA is tagged (e.g. `prod-2026-Q2-cutover-<sha>`) and ALL live tenants are confirmed migrated to or past it via the deploy runbook.
2. **No active feature branches carry new migrations on the squash target app.** Run `git log --all -- apps/<app>/migrations/` and confirm the last commit is on the canonical branch.
3. **`makemigrations --check --dry-run` clean** on the target app at the chosen cutover tag.
4. **Backup of the live database snapshot taken** and restored to a staging clone with the *unsquashed* migration history applied. The squash will be tested against this clone first.
5. **`apps/<app>/migrations/__init__.py` last-modified by squash author** — confirm no parallel session is mid-write.
6. **`scan_migration_model_imports` baseline 0** so we know historical migrations don't import live models (which would break the squash's `apps.get_model("X", "Y")` historical-state contract).
7. **Test suite green at the cutover tag** with `--keepdb=False` (forces full migration rebuild). If the test DB can't be rebuilt cleanly, the squash will fail in CI.

## Procedure (per-app, in this order)

The order matters. Squash `academics` and `schools` first because they have the fewest cross-app dependents. Save `siteconfig` for last — it has the broadest blast radius.

### Recommended sequence

```
1. academics      (52 → ~5 squashed leaves)
2. schools        (56 → ~5)
3. people         (57 → ~6)
4. finance        (66 → ~7) — money tables; freeze writes during cutover
5. platform_runtime (75 → ~8)
6. siteconfig     (188 → ~12) — last, longest freeze window
```

### Per-app steps

For each app:

```bash
# 1. Confirm no in-flight makemigrations
python manage.py makemigrations <app> --check --dry-run

# 2. Squash with the squashmigrations command (Django built-in)
python manage.py squashmigrations <app> <first> <last> --no-input
#    where <first> = oldest non-squashed leaf, <last> = current leaf

# 3. Review the generated <last>_squashed_<first>_<last>.py
#    — confirm `replaces = [...]` lists every file it consumes
#    — confirm `dependencies = [...]` points at the correct cross-app deps
#    — confirm operations are only CreateModel / AddField / AlterField / etc.
#      (NO RunPython, NO RunSQL — those must be preserved as standalone migrations
#       or extracted to a separate data migration with `elidable=False`)

# 4. Test the squash against the staging clone
#    a. drop the clone's schema for <app>
#    b. apply ONLY the unsquashed history -> capture schema snapshot A
#    c. drop again, apply ONLY the squashed history -> capture schema snapshot B
#    d. diff A vs B -> MUST be empty (modulo column ordering on PostgreSQL)

# 5. Test the suite with the squashed history
python manage.py test apps.<app> --keepdb=False --noinput --settings=config.settings

# 6. ONLY then commit the squashed migration + delete the squashed-by files

# 7. After the live deploy succeeds and the migration applies cleanly,
#    wait ONE FULL RELEASE CYCLE (typically 14 days) before deleting the
#    consumed files. Until then, both old and new histories coexist.
```

## What must NEVER happen

* Do not squash any migration that contains `RunPython` with side effects (sending emails, calling external APIs, writing to non-DB state) unless the data migration is preserved as a separate non-squashed file with `elidable=False`.
* Do not squash across a `RenameModel` boundary without first verifying every `ForeignKey` / `OneToOneField` pointing at the renamed model is updated.
* Do not squash if the staging clone schema diff in step 4d is non-empty.
* Do not delete the consumed migration files in the same commit that introduces the squashed migration — that breaks any in-flight deploy that hadn't yet applied the squash.
* Do not squash during a multi-region cutover or while any tenant DB is unreachable.

## Rollback procedure

If the squash applies cleanly in CI but fails on production:

1. Revert the squash commit.
2. Re-deploy the prior tag.
3. Roll the DB forward via the *unsquashed* migration history (it was preserved through the deprecation window).
4. File an incident with the actual SQL error from the production logs.
5. Diagnose against the staging clone before retrying.

## Why this is deferred (not executed now)

* No production cutover tag exists yet (precondition 1 fails).
* Parallel sessions are actively writing to `siteconfig` and `platform_runtime` (precondition 2 fails — most recently the v3.91.1 marketplace-ops-admin-bridge and v3.91.0 ReBAC waves touched both).
* Test suite full-rebuild discipline (precondition 7) has not been re-baselined since the batch 1506 module additions.

When the production cutover tag lands, walk this document top-to-bottom. Do not improvise.

## Owner

`platform` for `siteconfig` / `platform_runtime` / `schools` / `people` / `academics`. `platform-finance` for `finance` (money tables require finance-team signoff on the staging-clone diff in step 4d).

## Related verifiers

| Verifier | Role |
| --- | --- |
| `scripts/check_real_migration_drift.py` | Distinguishes real drift from cosmetic; must exit 0 immediately before AND after each squash |
| `scripts/scan_migration_model_imports.py` | Baseline 0; confirms historical migrations are safe to squash |
| `scripts/verify_sot_pillar_evidence.py` | Re-run after each squash to confirm SOT references still resolve |

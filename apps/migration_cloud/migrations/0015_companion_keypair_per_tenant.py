"""v3.34.0 Agent 1 — Companion keypair per-tenant scoping.

Promote ``MigrationCloudCompanionKeypair`` from platform-global
(one-active-row constraint scoped only on ``is_active=True``) to
per-tenant (one-active-row PER TENANT). A single-tenant key leak no
longer blasts radius across the platform.

Operations (pure AddField + AlterField + RemoveConstraint + AddIndex +
AddConstraint + RunPython):

  1. Drop the global ``migrationcloud_companion_keypair_one_active``
     constraint AND the ``unique=True`` on ``key_version``.
  2. Add ``tenant`` FK to ``schools.School`` (nullable for the
     interim AddField step so the schema-rewrite doesn't reject
     existing rows; the RunPython backfill below assigns every row
     and the AlterField at the tail of the operations list flips
     ``null=False``).
  3. RunPython backfills ``tenant`` on every existing keypair row by
     copying to the first ``schools.School`` row. On a fresh DB with
     no keypairs (the common case) this is a no-op. On a deploy with
     0 schools yet, also a no-op; the keypair will lazy-create on
     first ``ensure_active_keypair(tenant)`` call.
  4. Add the (tenant, is_active=True) partial unique constraint plus
     (tenant, key_version) unique-together for per-tenant rotation
     versioning.

Forward + reverse operations are pure: ``apps.get_model(...)`` only,
no live model imports — ``scan_migration_model_imports`` clean.
``# tenant-isolation-allow:`` markers are 5-part-hyphenated.

NEVER logs: private key bytes, plaintext content, encryption keys,
tenant schema name.
"""
from __future__ import annotations

import logging

from django.db import migrations, models

logger = logging.getLogger(__name__)


def backfill_keypair_tenant_forward(apps, schema_editor):
    """Assign every existing keypair to the first ``schools.School`` row.

    Idempotent:

    * On a fresh DB with no keypairs: no-op.
    * On a DB with keypairs but no schools yet: log + skip; the
      keypair is unreachable until a tenant is created, and the next
      ``ensure_active_keypair(tenant)`` call will mint a fresh one.
    * On a DB with keypairs and at least one school: assign every
      keypair row to ``School.objects.order_by('pk').first()`` so the
      historical key remains usable by that tenant. Operators with
      multiple existing tenants should manually rotate per-tenant
      after the migration (the staff-only rotate endpoint mints a
      fresh keypair scoped to ``request.tenant``).

    NEVER logs private bytes or fingerprint material; emits counts +
    tenant_pk only.
    """
    Keypair = apps.get_model("migration_cloud", "MigrationCloudCompanionKeypair")
    School = apps.get_model("schools", "School")

    # tenant-isolation-allow: data-migration-backfill-server-keypair-per-tenant
    raw_pks = list(Keypair.objects.values_list("pk", flat=True))
    if not raw_pks:
        logger.info(
            "migration_cloud_companion_keypair_per_tenant_backfill_forward",
            extra={"keypair_count": 0, "result": "noop_empty"},
        )
        return

    # tenant-isolation-allow: data-migration-backfill-server-keypair-per-tenant
    first_school = School.objects.order_by("pk").first()
    if first_school is None:
        logger.info(
            "migration_cloud_companion_keypair_per_tenant_backfill_forward",
            extra={
                "keypair_count": len(raw_pks),
                "result": "skipped_no_schools",
            },
        )
        return

    assigned = 0
    skipped = 0
    for pk in raw_pks:
        try:
            # tenant-isolation-allow: data-migration-backfill-server-keypair-per-tenant
            row = Keypair.objects.get(pk=pk)
        except Keypair.DoesNotExist:
            skipped += 1
            continue
        if row.tenant_id is not None:
            skipped += 1
            continue
        row.tenant = first_school
        row.save(update_fields=["tenant"])
        assigned += 1

    logger.info(
        "migration_cloud_companion_keypair_per_tenant_backfill_forward",
        extra={
            "keypair_count": len(raw_pks),
            "assigned": assigned,
            "skipped": skipped,
            "tenant_pk": str(first_school.pk),
            "result": "ok",
        },
    )


def backfill_keypair_tenant_reverse(apps, schema_editor):
    """Reverse: clear tenant FKs so the column can drop.

    Symmetric to the forward op; defensive against re-running. NEVER
    logs the bytes themselves.
    """
    Keypair = apps.get_model("migration_cloud", "MigrationCloudCompanionKeypair")
    # tenant-isolation-allow: data-migration-backfill-server-keypair-per-tenant
    cleared = Keypair.objects.update(tenant=None)
    logger.info(
        "migration_cloud_companion_keypair_per_tenant_backfill_reverse",
        extra={"cleared": cleared, "result": "ok"},
    )


class Migration(migrations.Migration):

    dependencies = [
        # v3.34.0 — chain after 0012 (which itself chains 0014) to keep
        # the leaf single. This preserves "applies cleanly on top of
        # 0014_merge_0011_0013" because 0012 only adds the
        # webhook_subscription.event_classes JSON column, which is
        # disjoint from this migration's keypair operations.
        ("migration_cloud", "0012_webhook_event_classes"),
        # Depend on the latest schools migration so the FK target's
        # PK column is settled at the point this migration applies.
        ("schools", "0051_add_default_language"),
    ]

    operations = [
        # 1. Drop the global one-active constraint and key_version
        #    global-uniqueness so we can re-scope both per-tenant.
        migrations.RemoveConstraint(
            model_name="migrationcloudcompanionkeypair",
            name="migrationcloud_companion_keypair_one_active",
        ),
        migrations.AlterField(
            model_name="migrationcloudcompanionkeypair",
            name="key_version",
            field=models.CharField(
                db_index=True,
                help_text=(
                    "Monotonic version tag scoped per-tenant, e.g. 'v1', 'v2'. "
                    "Unique within (tenant, key_version)."
                ),
                max_length=16,
            ),
        ),
        # 2. Add tenant FK (nullable for the AddField step so existing
        #    rows accept the column rewrite; backfill assigns + final
        #    AlterField below flips null=False).
        migrations.AddField(
            model_name="migrationcloudcompanionkeypair",
            name="tenant",
            field=models.ForeignKey(
                db_index=True,
                help_text=(
                    "Tenant that owns this keypair. v3.34.0 promotes the "
                    "Companion server keypair from platform-global to per-tenant "
                    "so a single-tenant key leak does not blast-radius the rest."
                ),
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="companion_keypairs",
                to="schools.school",
            ),
        ),
        # 3. Backfill existing rows.
        migrations.RunPython(
            backfill_keypair_tenant_forward,
            reverse_code=backfill_keypair_tenant_reverse,
        ),
        # 4. Flip tenant FK to NOT NULL now that the backfill landed.
        migrations.AlterField(
            model_name="migrationcloudcompanionkeypair",
            name="tenant",
            field=models.ForeignKey(
                db_index=True,
                help_text=(
                    "Tenant that owns this keypair. v3.34.0 promotes the "
                    "Companion server keypair from platform-global to per-tenant "
                    "so a single-tenant key leak does not blast-radius the rest."
                ),
                on_delete=models.deletion.CASCADE,
                related_name="companion_keypairs",
                to="schools.school",
            ),
        ),
        # 5. Re-add the partial unique constraint scoped per-tenant +
        #    the (tenant, key_version) unique-together + the composite
        #    index.
        migrations.AddIndex(
            model_name="migrationcloudcompanionkeypair",
            index=models.Index(
                fields=["tenant", "is_active"],
                name="migration_c_tenant__c71355_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="migrationcloudcompanionkeypair",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True)),
                fields=("tenant", "is_active"),
                name="uniq_active_keypair_per_tenant",
            ),
        ),
        migrations.AddConstraint(
            model_name="migrationcloudcompanionkeypair",
            constraint=models.UniqueConstraint(
                fields=("tenant", "key_version"),
                name="uniq_keypair_version_per_tenant",
            ),
        ),
    ]

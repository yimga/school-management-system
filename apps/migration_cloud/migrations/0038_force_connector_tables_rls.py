# FORCE ROW LEVEL SECURITY on the connector tables 0037 enabled.
#
# Without FORCE, the Postgres table OWNER (the role Django runs as in CI/managed
# prod/most local setups) bypasses every RLS policy — so 0037's ENABLE + policy is
# inert for the app. schools.0048_force_rls_on_all_enabled_tables did a one-shot
# gap-walk FORCE, but it ran BEFORE these tables existed and, being a completed
# RunPython, never re-runs on already-migrated databases — so the 0037 tables
# stay ENABLED-but-unFORCED and their policies never bind. This migration FORCEs
# exactly those 7 school_id connector tables so the default-deny policy actually
# takes effect for the app role (the bundle/asset/idmapping tables were already
# FORCEd by 0048, which is why only these need it).
#
# Safe to FORCE: the connector wizard writes/reads in request context with
# app.current_school_id set; no Celery task (retention/audit/alerts) touches these
# 7 tables cross-tenant (verified) so none hits default-deny. No-op on SQLite and
# when USE_DJANGO_TENANTS=True (schema mode).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = [
    "migration_cloud_migrationsourceconnection",
    "migration_cloud_migrationdiscoveryrun",
    "migration_cloud_migrationstagingbatch",
    "migration_cloud_migrationfieldmapping",
    "migration_cloud_migrationquarantineitem",
    "migration_cloud_migrationimportrun",
    "migration_cloud_migrationauditevent",
]


def force_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")


def unforce_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("migration_cloud", "0037_connector_tables_rls"),
    ]

    operations = [
        migrations.RunPython(force_rls, unforce_rls),
    ]

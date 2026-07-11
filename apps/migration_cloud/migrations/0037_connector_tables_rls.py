# RLS enable + default-deny for the school-scoped connector workflow tables
# (source connections, discovery/staging/mapping/quarantine/import runs, and the
# school-scoped connector audit trail). These carry per-tenant source-platform
# state and staged rows (PII in transit) but were never brought under RLS when
# 0030/0031 sealed the bundle/asset/idmapping tables.
#
# Same shape as 0031 and schoolops.0033_inventory_movement_rls: every table below
# has a ``school_id`` column (verified against apps/migration_cloud/models_connectors.py),
# so the tenant policy binds on ``school_id::text = current_setting('app.current_school_id')``.
# The platform-wide ``MigrationConnectorProfile`` (no school_id) and the
# tamper-evident ``MigrationCloudAuditEvent`` (pseudonymized ``tenant_id_hash``,
# no school_id) are deliberately excluded — the school_id policy cannot apply to them.
#
# No FORCE here, matching the per-table convention (0030/0031, schoolops.0033):
# retention/audit sweeps that touch these tables cross-tenant stay safe, and the
# global FORCE mechanism governs binding uniformly with the already-sealed tables.
# No-op on SQLite and when USE_DJANGO_TENANTS=True (schema mode).

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

USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def _policy_name(table):
    short = table.replace("migration_cloud_", "", 1)
    return f"migration_cloud_tenant_{short}"


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            policy_name = _policy_name(table)
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {USING_CLAUSE}
                WITH CHECK {USING_CLAUSE};
                """
            )


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            policy_name = _policy_name(table)
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("migration_cloud", "0036_artifact_assigned_domain"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]

# RLS enable + default-deny for the school-scoped CutoverRunbook table.
#
# CutoverRunbook (0041) is the rehearsal -> real -> sign-off cutover record, bound
# to a district via a ``school`` FK (school_id column), but it was never brought
# under RLS when 0030/0031 sealed the bundle/asset tables or when 0037 sealed the
# connector-workflow tables. It carries per-tenant cutover state, so it needs the
# same tenant policy.
#
# Same shape as 0037_connector_tables_rls (and 0031 / schoolops.0033): the table
# has a ``school_id`` column, so the tenant policy binds on
# ``school_id::text = current_setting('app.current_school_id')`` with the standard
# rls_bypass escape. No FORCE here, matching the per-table convention. No-op on
# SQLite and when USE_DJANGO_TENANTS=True (schema mode).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = [
    "migration_cloud_cutoverrunbook",
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
        ("migration_cloud", "0042_intake_bundle_fk"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]

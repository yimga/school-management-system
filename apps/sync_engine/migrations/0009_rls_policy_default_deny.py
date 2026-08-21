# RLS default-deny for tenant-scoped sync_engine tables.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = [
    "sync_engine_syncapplyledger",
    "sync_engine_edgesyncrun",
    "sync_engine_edgesynccursor",
    "sync_engine_edgesyncdirective",
    "sync_engine_synctombstone",
    "sync_engine_syncbundlereceipt",
    "sync_engine_syncfiletransfer",
]
USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def apply_default_deny(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            short = table.replace("sync_engine_", "", 1)
            policy_name = f"sync_engine_tenant_{short}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {USING_CLAUSE}
                WITH CHECK {USING_CLAUSE};
                """
            )


def reverse_default_deny(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            short = table.replace("sync_engine_", "", 1)
            policy_name = f"sync_engine_tenant_{short}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")


class Migration(migrations.Migration):
    dependencies = [
        ("sync_engine", "0008_enable_rls_postgresql"),
    ]

    operations = [
        migrations.RunPython(apply_default_deny, reverse_default_deny),
    ]

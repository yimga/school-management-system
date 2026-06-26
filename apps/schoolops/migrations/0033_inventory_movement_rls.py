# RLS for schoolops_inventorymovement (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLE = "schoolops_inventorymovement"
POLICY_PREFIX = "schoolops_tenant"
USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY;")
        cursor.execute(
            f"""
            CREATE POLICY {POLICY_PREFIX}_inventorymovement ON {TABLE}
            FOR ALL
            USING {USING_CLAUSE}
            WITH CHECK {USING_CLAUSE};
            """
        )


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(
            f"DROP POLICY IF EXISTS {POLICY_PREFIX}_inventorymovement ON {TABLE};"
        )
        cursor.execute(f"ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("schoolops", "0032_inventory_movement"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]

# Enable RLS on the tenant tables this app OWNS under the schoolops_ prefix.
# PostgreSQL single-schema mode only (should_apply_rls); no-op under
# schema-per-tenant and SQLite.
#
# Only schoolops_busboardingevent / schoolops_bookableresource /
# schoolops_resourcebooking are handled here. The other tenant models in this app
# were moved from the `schools` app and keep their legacy `schools_*` db_table
# (Campus->schools_campus, InventoryItem->schools_inventoryitem, ...). Those are
# RLS-enabled by schools/0081_rls_backfill_unenumerated_tenant_tables and must NOT
# be touched here. The pre-fix version listed all of them under a WRONG
# `schoolops_*` prefix (schoolops_campus etc.) that does not exist, which aborted
# `migrate` on a fresh single-schema Postgres database with
# `relation "schoolops_campus" does not exist` -- so RLS was in fact never enabled
# on the three schoolops-owned tables either. (SQLite hid it: the migration is a
# no-op there; and the tenants-rls Postgres CI that would have caught it has been
# unable to run.)
#
# Tables without a `school_id` column (HostelRoom, BiometricAttendanceLog) are
# FK-scoped, not school_id-scoped, and are intentionally not covered by a
# school_id policy here.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

# Real db_table names OWNED by this app (schoolops_ prefix + school_id column) and
# NOT covered by the schools/0081 backfill.
SCHOOLOPS_OWNED_TABLES = [
    "schoolops_busboardingevent",
    "schoolops_bookableresource",
    "schoolops_resourcebooking",
]
USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def _existing_with_school_id(cursor, tables):
    """Only touch tables that exist in the current schema AND carry school_id.

    Mirrors schools/0081: CREATE POLICY references school_id, so a table present
    without the column would abort migrate. Guarding is safe -- the coverage gate
    still requires each table name to appear in an *rls* migration literal.
    """
    cursor.execute(
        """
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid
        WHERE c.relkind = 'r'
          AND n.nspname = current_schema()
          AND c.relname = ANY(%s)
          AND a.attname = 'school_id'
          AND a.attnum > 0
          AND NOT a.attisdropped
        """,
        [list(tables)],
    )
    return [row[0] for row in cursor.fetchall()]


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in _existing_with_school_id(cursor, SCHOOLOPS_OWNED_TABLES):
            policy = f"rls_tenant_{table}"
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
            cursor.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;')
            cursor.execute(f'DROP POLICY IF EXISTS {policy} ON "{table}";')
            cursor.execute(
                f"""
                CREATE POLICY {policy} ON "{table}"
                FOR ALL
                USING {USING_CLAUSE}
                WITH CHECK {USING_CLAUSE};
                """
            )


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in _existing_with_school_id(cursor, SCHOOLOPS_OWNED_TABLES):
            policy = f"rls_tenant_{table}"
            cursor.execute(f'DROP POLICY IF EXISTS {policy} ON "{table}";')
            cursor.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [
        ("schoolops", "0029_resource_booking_exclude_constraint"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]

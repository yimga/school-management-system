"""RLS for the three tables items 2.3/2.4 made tenant-scoped (PostgreSQL only).

``schools/0081_rls_backfill_unenumerated_tenant_tables`` enumerates these three
tables, but it cannot be the migration that enables them:

  * ``academics_curriculumallocation`` does not exist yet when 0081 runs on a
    fresh database (0081 is a dependency of ``academics/0070``, which creates
    the table), so 0081's ``_existing`` filter skips it;
  * ``academics_room`` and ``academics_timeslot`` DO exist by then but have no
    ``school_id`` column until ``academics/0070`` adds it, and 0081's policy
    predicate is written against ``school_id``.

So this migration -- ordered after both the column and the table exist -- is
what actually turns RLS on for them. Idempotent (``DROP POLICY IF EXISTS``), and
a no-op under schema-per-tenant, where ``should_apply_rls`` returns False
because isolation comes from the schema instead.
"""

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = [
    "academics_curriculumallocation",
    "academics_room",
    "academics_timeslot",
]
POLICY_PREFIX = "academics_tenant"
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
        for table in TABLES:
            policy_name = f"{POLICY_PREFIX}_{table.replace('academics_', '')}"
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
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
            policy_name = f"{POLICY_PREFIX}_{table.replace('academics_', '')}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0071_backfill_room_timeslot_school"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]

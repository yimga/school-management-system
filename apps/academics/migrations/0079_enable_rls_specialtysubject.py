"""RLS for academics_specialtysubject (PostgreSQL single-schema only).

``SpecialtySubject`` (added in 0078) carries a ``school`` FK but was created after
the last academics RLS migration and is absent from the static backfill list in
``schools/0081_rls_backfill_unenumerated_tenant_tables``. Under single-schema
deployment RLS *is* the tenant isolation, so without this the table would have no
row-level policy — inconsistent with every sibling academics table. This turns it
on. Idempotent (``DROP POLICY IF EXISTS``); a no-op under schema-per-tenant, where
``should_apply_rls`` returns False because isolation comes from the schema.
"""

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLES = [
    "academics_specialtysubject",
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
        ("academics", "0078_specialtysubject"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]

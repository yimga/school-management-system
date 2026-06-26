# RLS for discipline ledger tables + Incident (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

DISCIPLINE_TABLES = [
    "academics_incident",
    "academics_behaviorpointledger",
    "academics_restorativeaction",
]
POLICY_PREFIX = "academics_tenant"
USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def _apply_policies(cursor, *, default_deny: bool):
    for table in DISCIPLINE_TABLES:
        short = table.replace("academics_", "")
        policy_name = f"{POLICY_PREFIX}_{short}"
        cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
        if default_deny:
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {USING_CLAUSE}
                WITH CHECK {USING_CLAUSE};
                """
            )
        else:
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING (
                    current_setting('app.current_school_id', true) IS NULL
                    OR school_id::text = current_setting('app.current_school_id', true)
                )
                WITH CHECK (
                    current_setting('app.current_school_id', true) IS NULL
                    OR school_id::text = current_setting('app.current_school_id', true)
                );
                """
            )


def enable_discipline_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        _apply_policies(cursor, default_deny=False)


def apply_discipline_default_deny(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        _apply_policies(cursor, default_deny=True)


def reverse_discipline_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in DISCIPLINE_TABLES:
            short = table.replace("academics_", "")
            policy_name = f"{POLICY_PREFIX}_{short}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0060_discipline_ledger"),
    ]

    operations = [
        migrations.RunPython(enable_discipline_rls, reverse_discipline_rls),
        migrations.RunPython(apply_discipline_default_deny, enable_discipline_rls),
    ]

# RLS enable + default-deny for athletics club tables (PostgreSQL only).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

CLUB_TABLES = [
    "athletics_club",
    "athletics_clubadvisorassignment",
    "athletics_clubmembership",
]

USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def enable_rls_and_policy(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in CLUB_TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            short = table.replace("athletics_", "")
            policy_name = f"athletics_tenant_{short}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {USING_CLAUSE}
                WITH CHECK {USING_CLAUSE};
                """
            )


def reverse_rls_and_policy(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in CLUB_TABLES:
            short = table.replace("athletics_", "")
            policy_name = f"athletics_tenant_{short}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("athletics", "0004_clubs"),
    ]

    operations = [
        migrations.RunPython(enable_rls_and_policy, reverse_rls_and_policy),
    ]

# RLS default-deny for tenant-scoped athletics tables.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

ATHLETICS_TABLES = [
    "athletics_sport",
    "athletics_season",
    "athletics_teamkitfee",
    "athletics_team",
    "athletics_coachassignment",
    "athletics_teammembership",
    "athletics_medicalclearance",
    "athletics_participationconsent",
    "athletics_eligibilityrecord",
    "athletics_fixture",
    "athletics_fixturevenuebooking",
    "athletics_fixtureresult",
    "athletics_fixturetravel",
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
        for table in ATHLETICS_TABLES:
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


def reverse_default_deny(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in ATHLETICS_TABLES:
            short = table.replace("athletics_", "")
            policy_name = f"athletics_tenant_{short}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")


class Migration(migrations.Migration):
    dependencies = [
        ("athletics", "0002_enable_rls_postgresql"),
    ]

    operations = [
        migrations.RunPython(apply_default_deny, reverse_default_deny),
    ]

# RLS enable for tenant-scoped athletics tables (PostgreSQL only).

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


def enable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in ATHLETICS_TABLES:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")


def disable_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in ATHLETICS_TABLES:
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("athletics", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]

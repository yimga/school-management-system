# RLS enable + default-deny for the tenant-scoped ExperienceRegionApproval table
# (PostgreSQL only; SQLite/other backends skip and rely on the always-school=-scoped
# service-layer queryset). Mirrors apps/athletics/migrations/0002+0003.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLE = "studio_os_experienceregionapproval"
POLICY = "studio_os_tenant_experienceregionapproval"
USING_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""


def apply_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY;")
        cursor.execute(f"DROP POLICY IF EXISTS {POLICY} ON {TABLE};")
        cursor.execute(
            f"""
            CREATE POLICY {POLICY} ON {TABLE}
            FOR ALL
            USING {USING_CLAUSE}
            WITH CHECK {USING_CLAUSE};
            """
        )


def reverse_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(f"DROP POLICY IF EXISTS {POLICY} ON {TABLE};")
        cursor.execute(f"ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("studio_os", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(apply_rls, reverse_rls),
    ]

# RLS default-deny policy for the tenant-scoped ExperienceRegionApproval table.
#
# Idempotently re-asserts the tenant isolation policy that 0002 created, under the
# convention filename (*_rls_policy_default_deny) that scan_rls_force_coverage keys on.
# Together with 0003_enable_rls_postgresql this makes studio_os RLS-covered by the same
# convention every other tenant app follows, so the table can be removed from the
# rls-force-coverage baseline (the finding is genuinely resolved, not masked).
#
# Policy semantics match 0002 exactly: allow only when the RLS bypass GUC is on OR the
# row's school_id equals the current-school GUC; deny (no rows) otherwise.

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


def apply_default_deny(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(f"DROP POLICY IF EXISTS {POLICY} ON {TABLE};")
        cursor.execute(
            f"""
            CREATE POLICY {POLICY} ON {TABLE}
            FOR ALL
            USING {USING_CLAUSE}
            WITH CHECK {USING_CLAUSE};
            """
        )


def reverse_default_deny(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(f"DROP POLICY IF EXISTS {POLICY} ON {TABLE};")


class Migration(migrations.Migration):
    dependencies = [
        ("studio_os", "0003_enable_rls_postgresql"),
    ]

    operations = [
        migrations.RunPython(apply_default_deny, reverse_default_deny),
    ]

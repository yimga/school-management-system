# RLS ENABLE + FORCE for the tenant-scoped ExperienceRegionApproval table
# (PostgreSQL only; SQLite/other backends skip via should_apply_rls and rely on the
# always-school=-scoped service-layer queryset).
#
# 0002 already ENABLEd RLS + created the tenant policy, but under a non-convention
# filename — so (a) scan_rls_force_coverage could not recognize studio_os as covered
# (it looks for *_enable_rls_postgresql + *_rls_policy_default_deny) and baselined the
# table, and (b) the catch-all schools.0048_force_rls_on_all_enabled_tables — which
# FORCEs every enabled table but depends only on each app's *_rls_policy_default_deny
# migration — never listed studio_os.0002, so 0048 could run BEFORE this table was
# enabled and leave it un-FORCEd. Without FORCE the table owner (the role Django runs
# as) bypasses the policy entirely.
#
# This convention-named migration re-asserts ENABLE and adds FORCE ROW LEVEL SECURITY
# EXPLICITLY on studio_os's own migration graph, so the guarantee does not depend on
# 0048's ordering. Idempotent (ENABLE/FORCE are safe to re-run).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

TABLE = "studio_os_experienceregionapproval"


def enable_and_force_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY;")
        cursor.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY;")


def unforce_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("studio_os", "0002_experience_region_approval_rls"),
    ]

    operations = [
        migrations.RunPython(enable_and_force_rls, unforce_rls),
    ]

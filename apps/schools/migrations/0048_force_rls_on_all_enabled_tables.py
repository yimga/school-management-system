# Without FORCE, the Postgres table owner (the role Django runs as in CI, in
# managed prod, and in most local setups) bypasses every RLS policy. The policies
# in `*_enable_rls_postgresql` + `*_rls_policy_default_deny` exist for everyone
# except the owner — i.e. for nobody, in practice. This migration flips every
# already-RLS-enabled table to FORCE so the policies actually bind.
#
# Post-deploy, any code that runs without setting app.current_school_id or
# app.rls_bypass = 'on' will hit default-deny on every tenant-scoped table.
# Mgmt commands, signal handlers, and background jobs that legitimately need
# cross-tenant access MUST wrap their work in apps.schools.rls_context.rls_bypass.
#
# No-op on SQLite and when USE_DJANGO_TENANTS=True (schema mode).

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls


def _rls_tables(cursor, *, forced: bool):
    cursor.execute(
        """
        SELECT n.nspname, c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND c.relrowsecurity = TRUE
          AND c.relforcerowsecurity = %s
          AND n.nspname = current_schema()
        ORDER BY n.nspname, c.relname
        """,
        [forced],
    )
    return cursor.fetchall()


def force_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for schema, table in _rls_tables(cursor, forced=False):
            cursor.execute(f'ALTER TABLE "{schema}"."{table}" FORCE ROW LEVEL SECURITY;')


def unforce_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for schema, table in _rls_tables(cursor, forced=True):
            cursor.execute(
                f'ALTER TABLE "{schema}"."{table}" NO FORCE ROW LEVEL SECURITY;'
            )


class Migration(migrations.Migration):
    # Depend on every per-app default-deny migration so we never FORCE a table
    # whose policies are still in the old "NULL OR match" permissive shape.
    dependencies = [
        ("schools", "0047_alter_marketingfunnelevent_event_type_lifecycle"),
        ("academics", "0038_rls_policy_default_deny"),
        ("communication", "0014_rls_policy_default_deny"),
        ("evals", "0027_rls_policy_default_deny"),
        ("finance", "0047_rls_policy_default_deny"),
        ("people", "0038_rls_policy_default_deny"),
        ("reports", "0012_rls_policy_default_deny"),
        ("siteconfig", "0129_rls_policy_default_deny"),
    ]
    operations = [migrations.RunPython(force_rls, unforce_rls)]

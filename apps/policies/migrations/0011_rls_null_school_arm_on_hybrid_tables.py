# RLS default-deny, corrected for the three HYBRID platform-or-tenant tables.
#
# 0009 applied ONE clause to all six policies tables. Three of them are hybrid
# global+tenant -- policyrule ("Null => platform-wide rule applied to every tenant"),
# policybundle ("Null = platform/country-level bundle") and policydecisionlog
# (school is null=True, SET_NULL). For a row with school_id NULL,
# `NULL::text = '42'` evaluates to NULL, so USING is false and the row is invisible.
#
# In RLS mode that hides the platform baseline allow-rules seeded by 0010, and
# pdp._applicable_rules is built entirely on Q(school__isnull=True) | Q(school=school)
# -- so every pdp_enforce surface would fall to implicit_deny -- while every
# decide(school=None) log INSERT would violate the WITH CHECK with 42501.
#
# The peer migrations for the same situation get this right and are the pattern
# followed here: siteconfig/0129 defines a separate USING_FT for its one hybrid
# table, and metadata/0012 leads with `school_id IS NULL OR ...`.

from django.db import connection, migrations

from apps.schools.rls import should_apply_rls

STRICT_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""

# Same clause plus the platform-scope arm. Additive: bypass and the tenant match
# behave exactly as before; only school_id IS NULL rows change visibility.
HYBRID_CLAUSE = """(
    current_setting('app.rls_bypass', true) = 'on'
    OR school_id IS NULL
    OR (
        current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true)
    )
)"""

# Explicit per-table mapping so the clause shape is readable next to the table it
# guards -- and so the regression test can assert it against the models' own
# school-FK nullability instead of a second hand-maintained list.
POLICY_CLAUSES = {
    "policies_policybundle": HYBRID_CLAUSE,
    "policies_policydecisionlog": HYBRID_CLAUSE,
    "policies_policyrule": HYBRID_CLAUSE,
    "policies_scheduledpolicyoverride": STRICT_CLAUSE,
    "policies_tenantblueprint": STRICT_CLAUSE,
    "policies_tenantpolicyoverride": STRICT_CLAUSE,
}


def apply_clauses(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table, clause in POLICY_CLAUSES.items():
            short = table.replace("policies_", "", 1)
            policy_name = f"policies_tenant_{short}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {clause}
                WITH CHECK {clause};
                """
            )


def reverse_clauses(apps, schema_editor):
    """Restore 0009's uniform strict clause (its own reverse only DROPs)."""
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for table in POLICY_CLAUSES:
            short = table.replace("policies_", "", 1)
            policy_name = f"policies_tenant_{short}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table};")
            cursor.execute(
                f"""
                CREATE POLICY {policy_name} ON {table}
                FOR ALL
                USING {STRICT_CLAUSE}
                WITH CHECK {STRICT_CLAUSE};
                """
            )


class Migration(migrations.Migration):
    dependencies = [
        ("policies", "0010_seed_iam_baseline_pdp_rules"),
    ]

    operations = [
        migrations.RunPython(apply_clauses, reverse_clauses),
    ]

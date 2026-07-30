# Second global RLS FORCE sweep -- the sequel to 0048_force_rls_on_all_enabled_tables.
#
# 0048 flipped every RLS-enabled table to FORCE so its default-deny policy would
# bind even for the Postgres table owner (the role Django runs as in CI, managed
# prod, and most local setups). But 0048 ran ONCE, early: it depended only on the
# per-app default-deny leaves that existed at the time. Every app that added RLS
# afterward (athletics, billing, analytics, automation, apicenter, communication's
# extend-list, schoolops inventory movement, registries, school_events, late
# accounts/academics tables, ...) enabled + policied its tables but was never
# FORCE'd -- so on a fresh single-schema Postgres those ~75+ tenant tables carried
# a policy that binds "for everyone except the owner -- i.e. for nobody" (0048's
# own words). An owner connection saw every school's rows. SQLite hid it (RLS is a
# no-op there) and the tenants-rls Postgres CI that would have caught it has been
# unable to run.
#
# This migration re-runs the exact force sweep at the current migration tip. It
# depends on every first-party app leaf so it lands dead last, after all RLS
# enable/policy work. A companion must-fire test
# (apps/schools/tests/test_rls_force_coverage.py) asserts no RLS-enabled + policied
# table is left un-FORCE'd, so a future app that adds RLS without FORCE turns CI red.
#
# SAFETY: unlike 0048, this only forces tables that already carry at least one
# policy. Forcing an enabled-but-policy-less table would flip it to deny-all
# (nobody, not even a correctly-scoped tenant, could read it). Guarding on policy
# presence makes the sweep safe to run blindly across the whole schema.
#
# No-op on SQLite and when USE_DJANGO_TENANTS=True (schema-per-tenant mode).

from django.apps import apps as django_apps
from django.db import connection, migrations

from apps.schools.rls import should_apply_rls


def _enabled_unforced_with_policy(cursor):
    cursor.execute(
        """
        SELECT n.nspname, c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND c.relrowsecurity = TRUE
          AND c.relforcerowsecurity = FALSE
          AND n.nspname = current_schema()
          AND EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid)
        ORDER BY n.nspname, c.relname
        """
    )
    return cursor.fetchall()


def force_rls(apps, schema_editor):
    if not should_apply_rls(connection):
        return
    with connection.cursor() as cursor:
        for schema, table in _enabled_unforced_with_policy(cursor):
            cursor.execute(
                f'ALTER TABLE "{schema}"."{table}" FORCE ROW LEVEL SECURITY;'
            )


# Depend on every first-party app leaf so this sweep runs after all RLS
# enable/policy migrations, landing dead last.
#
# A few first-party apps (payment, plans_entitlements) live ONLY in the base
# INSTALLED_APPS and are deliberately excluded from SHARED_APPS/TENANT_APPS, so
# under schema-per-tenant mode (USE_DJANGO_TENANTS=1) their migrations are never
# loaded into the graph. A static dependency on such a leaf dangles with
# NodeNotFoundError and aborts `migrate_schemas` on a fresh Postgres. We filter
# the leaf list to the apps actually installed in the current mode:
#   * RLS mode (USE_DJANGO_TENANTS=0): every app is installed, so all leaves are
#     kept and the "runs after every RLS enable/policy" ordering is preserved --
#     test_rls_force_coverage stays honest.
#   * schema mode: the force sweep is a no-op anyway (should_apply_rls is False),
#     so dropping the excluded (and unloadable) leaves changes nothing except
#     letting the graph resolve.
_ALL_LEAF_DEPENDENCIES = [
    ("academics", "0072_enable_rls_curriculum_room_timeslot"),
    ("accounts", "0055_loginmagiclink"),
    ("analytics", "0030_rls_policy_default_deny"),
    ("api", "0002_offline_global_ops"),
    ("apicenter", "0011_rls_policy_default_deny"),
    ("assist_dock", "0004_impersonationgrant_impersonationsession_and_more"),
    ("athletics", "0005_clubs_rls"),
    ("automation", "0021_rls_policy_default_deny"),
    ("billing", "0020_processorrevenueshareaccrual"),
    ("brand_experience", "0004_template_assignment_and_audit_event"),
    ("communication", "0032_ensure_school_fk_columns"),
    ("compliance", "0023_auditlog_impersonation_context"),
    ("customers", "0004_world_engine"),
    ("customersuccess", "0006_rls_policy_default_deny"),
    ("emis", "0002_emis_export_tenant_upload_to"),
    ("evals", "0038_ensure_school_fk_columns"),
    ("events", "0008_rls_policy_default_deny"),
    ("feedback", "0009_rls_policy_default_deny"),
    ("finance", "0079_fractionalpaymentledger_tax_component"),
    ("global_registries", "0001_proxy_owner_models"),
    ("governance", "0006_rls_policy_default_deny"),
    ("integrations_marketplace", "0006_tenantretentionoverride"),
    ("lifecycle", "0005_rls_policy_default_deny"),
    ("marketplace", "0015_rls_policy_default_deny"),
    ("metadata", "0016_dynamicfielddefinition_validation_json"),
    ("migration_cloud", "0043_cutoverrunbook_rls"),
    ("observability", "0006_incident_update_timeline"),
    ("orchestration", "0004_rls_policy_default_deny"),
    ("packages", "0008_rls_policy_default_deny"),
    ("payment", "0001_regional_payment_rail_catalog"),
    ("payroll", "0008_ensure_offline_capture_table"),
    ("people", "0071_backfill_enrollment_from_student_row"),
    ("plans_entitlements", "0002_entitlement_proxy"),
    ("platform_runtime", "0100_heavy_work_outbox_kind_choices"),
    ("policies", "0010_seed_iam_baseline_pdp_rules"),
    ("portal", "0043_ensure_school_fk_columns"),
    ("registries", "0011_seed_currency_country_registries"),
    ("reports", "0025_enrollment_first_class"),
    ("requests", "0005_rls_policy_default_deny"),
    ("runtime_blueprints", "0001_proxy_owner_models"),
    ("sales", "0003_lead_decision_maker_and_owner"),
    ("school_events", "0003_rls_policy_default_deny"),
    ("schoolops", "0036_substitute_market_shift"),
    ("schools", "0082_ensure_advancement_offline_id"),
    ("setup_studio", "0004_rls_policy_default_deny"),
    ("siteconfig", "0207_seed_country_grading_profiles"),
    ("social_media", "0003_rls_policy_default_deny"),
    ("student360", "0001_immutable_transcript"),
    ("studio_os", "0004_rls_policy_default_deny"),
]

# Evaluated at graph-build time, after django.setup() has populated the app
# registry (the migration loader imports this module well after apps are ready).
_INSTALLED_APP_LABELS = {config.label for config in django_apps.get_app_configs()}


class Migration(migrations.Migration):
    dependencies = [
        dep for dep in _ALL_LEAF_DEPENDENCIES if dep[0] in _INSTALLED_APP_LABELS
    ]

    operations = [
        migrations.RunPython(force_rls, migrations.RunPython.noop),
    ]

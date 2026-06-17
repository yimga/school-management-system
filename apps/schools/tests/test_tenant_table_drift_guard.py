from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings

from apps.schools.tenant_schema_guard import (
    _entry_to_app_name,
    ensure_models_tables,
    missing_tenant_tables,
    tenant_app_labels,
)


class _StubSchemaEditor:
    """Minimal stand-in for the no-op (table-exists) path of ensure_models_tables.

    Constructing a real SQLite schema editor inside a TestCase transaction raises
    (FK checks enabled). The no-op path never issues DDL, so a stub with .connection
    + .deferred_sql is enough to exercise it.
    """

    def __init__(self, conn):
        self.connection = conn
        self.deferred_sql = []


class TenantAppLabelsTests(TestCase):
    def test_entry_to_app_name_normalises_appconfig_paths(self):
        self.assertEqual(
            _entry_to_app_name("apps.feedback.apps.FeedbackConfig"), "apps.feedback"
        )
        self.assertEqual(_entry_to_app_name("apps.people"), "apps.people")

    # TENANT_APPS / SHARED_APPS only exist under USE_DJANGO_TENANTS=1 (Postgres);
    # the SQLite test env runs shared-mode, so pin them deterministically here.
    @override_settings(
        TENANT_APPS=[
            "apps.people",
            "apps.schoolops",
            "apps.finance",
            "apps.payroll",
            "apps.feedback.apps.FeedbackConfig",
            "apps.schools",
        ],
        SHARED_APPS=["apps.schools", "apps.customers", "apps.siteconfig"],
    )
    def test_resolves_tenant_only_labels(self):
        labels = tenant_app_labels()
        for expected in {"people", "schoolops", "finance", "payroll", "feedback"}:
            self.assertIn(expected, labels)
        # In both TENANT_APPS and SHARED_APPS → public schema → excluded.
        self.assertNotIn("schools", labels)


class MissingTenantTablesTests(TestCase):
    def test_no_missing_tables_on_fully_migrated_schema(self):
        # The test DB is migrated to HEAD → every tenant-app table exists.
        self.assertEqual(missing_tenant_tables(), [])


class EnsureModelsTablesTests(TestCase):
    def test_noop_when_table_exists(self):
        from apps.schoolops.models import VisitorCheckIn

        created = ensure_models_tables(
            _StubSchemaEditor(connection), [VisitorCheckIn]
        )
        self.assertEqual(created, [])


class DetectTenantTableDriftCommandTests(TestCase):
    def test_command_reports_clean_on_healthy_db(self):
        out = StringIO()
        # Healthy DB → no drift → exit 0 (no SystemExit raised). In shared-mode
        # SQLite there are no tenant Client rows, so "no tenant schemas" is also a
        # valid clean outcome; either way the command must not flag drift / exit 1.
        call_command("detect_tenant_table_drift", stdout=out)
        val = out.getvalue().lower()
        self.assertTrue(
            "no table drift" in val or "no tenant schemas" in val,
            msg=f"unexpected detector output: {val!r}",
        )

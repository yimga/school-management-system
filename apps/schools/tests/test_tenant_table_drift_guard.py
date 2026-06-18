from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings

from apps.schools.tasks import detect_tenant_table_drift_scan
from apps.schools.tenant_schema_guard import (
    _entry_to_app_name,
    ensure_models_tables,
    missing_tenant_tables,
    scan_all_tenant_schemas,
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


class ScanAllTenantSchemasTests(TestCase):
    def test_returns_dict_with_no_drift_on_healthy_db(self):
        report = scan_all_tenant_schemas()
        self.assertIsInstance(report, dict)
        # Every schema reports an empty missing-table list on a HEAD-migrated DB.
        for rows in report.values():
            self.assertEqual(rows, [])


class DetectTenantTableDriftScanTests(TestCase):
    def test_scan_reports_ok_no_drift_on_healthy_db(self):
        result = detect_tenant_table_drift_scan()
        self.assertTrue(result["ok"])
        self.assertEqual(result["drifted_schemas"], 0)
        self.assertEqual(result["drift"], {})


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


class RunTenantColumnRepairsTests(TestCase):
    """The consolidated COLUMN-drift heal that the provision seed step runs so a
    requeue actually REPAIRS `column ... does not exist` instead of looping."""

    def test_runs_every_registered_repair_and_returns_bool_map(self):
        from apps.schools import tenant_schema_guard

        result = tenant_schema_guard.run_tenant_column_repairs()
        # On the HEAD-migrated test DB every column already exists → each repair
        # runs to completion and reports no change.
        expected_labels = {label for label, _, _ in tenant_schema_guard._COLUMN_REPAIRS}
        self.assertEqual(set(result), expected_labels)
        for label, changed in result.items():
            self.assertIsInstance(changed, bool, msg=label)
            self.assertFalse(changed, msg=f"{label} reported a change on a healthy DB")

    def test_idempotent_second_pass_changes_nothing(self):
        from apps.schools.tenant_schema_guard import run_tenant_column_repairs

        run_tenant_column_repairs()
        second = run_tenant_column_repairs()
        self.assertTrue(all(v is False for v in second.values()), msg=str(second))

    def test_one_repair_failing_never_blocks_the_others(self):
        from unittest import mock

        from apps.schools import tenant_schema_guard

        # Force the FIRST repair to raise an import failure; the remaining repairs
        # must still run (failure isolation — provisioning never aborts on a heal).
        bad = ("academics_school_id", "apps.academics.schema_repair", "does_not_exist")
        good = tenant_schema_guard._COLUMN_REPAIRS[1:]
        with mock.patch.object(
            tenant_schema_guard, "_COLUMN_REPAIRS", (bad,) + good
        ):
            result = tenant_schema_guard.run_tenant_column_repairs()
        # The broken one is skipped (absent from results), the good ones complete.
        self.assertNotIn("academics_school_id", result)
        self.assertEqual(set(result), {label for label, _, _ in good})

    def test_academics_school_id_heal_is_reachable_and_idempotent(self):
        # Direct proof the academics heal (the screenshot's failing column) is wired
        # and idempotent — a second pass on a healed schema is a no-op.
        from apps.academics.schema_repair import ensure_academics_school_id_columns

        ensure_academics_school_id_columns()
        self.assertFalse(ensure_academics_school_id_columns())

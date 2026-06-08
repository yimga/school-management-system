from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.tenancy.checks import database_pooling_checks
from apps.tenancy.pool_readiness import assess_database_pool_readiness


POSTGRES_DB = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "CONN_MAX_AGE": 600,
    }
}


class DatabasePoolingContractTests(SimpleTestCase):
    @override_settings(DB_POOL_MODE="direct", DATABASES=POSTGRES_DB)
    def test_direct_postgres_endpoint_is_supported(self):
        report = assess_database_pool_readiness()
        self.assertTrue(report.supported)
        self.assertEqual(database_pooling_checks(None), [])

    @override_settings(DB_POOL_MODE="session", DATABASES=POSTGRES_DB)
    def test_session_pooling_is_supported(self):
        report = assess_database_pool_readiness()
        self.assertTrue(report.supported)
        self.assertIn("server sessions remain pinned", report.reason)

    @override_settings(
        DB_POOL_MODE="transaction",
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "CONN_MAX_AGE": 0,
                "DISABLE_SERVER_SIDE_CURSORS": True,
            }
        },
    )
    def test_transaction_pooling_is_rejected_even_with_defensive_tuning(self):
        report = assess_database_pool_readiness()
        errors = database_pooling_checks(None)
        self.assertFalse(report.supported)
        self.assertTrue(report.live_interleaving_test_required)
        self.assertIn("tenancy.E009", {error.id for error in errors})
        self.assertNotIn("tenancy.E010", {error.id for error in errors})
        self.assertNotIn("tenancy.E011", {error.id for error in errors})

    @override_settings(
        DB_POOL_MODE="transaction",
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "CONN_MAX_AGE": 600,
                "DISABLE_SERVER_SIDE_CURSORS": False,
            }
        },
    )
    def test_transaction_pooling_reports_unsafe_django_tuning(self):
        error_ids = {error.id for error in database_pooling_checks(None)}
        self.assertEqual(
            error_ids,
            {"tenancy.E009", "tenancy.E010", "tenancy.E011"},
        )

    @override_settings(DB_POOL_MODE="mystery", DATABASES=POSTGRES_DB)
    def test_unknown_pool_mode_is_rejected(self):
        errors = database_pooling_checks(None)
        self.assertEqual([error.id for error in errors], ["tenancy.E008"])

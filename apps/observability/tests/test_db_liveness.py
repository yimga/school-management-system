"""
§2.4 Tests for db_liveness. Isolated from test_monitoring to avoid merge conflicts.
"""

from unittest.mock import patch

from django.test import TestCase
from django.db.utils import OperationalError

from apps.observability.db_liveness import check_db_liveness


class DbLivenessTests(TestCase):
    """Test check_db_liveness used by monitoring.check_database_health."""

    def test_returns_dict_with_status(self):
        result = check_db_liveness()
        self.assertIsInstance(result, dict)
        self.assertIn("status", result)
        self.assertIn(result["status"], ("healthy", "unhealthy"))

    def test_healthy_includes_response_time_ms(self):
        result = check_db_liveness()
        self.assertIn("response_time_ms", result)
        if result["status"] == "healthy":
            self.assertIsInstance(result["response_time_ms"], (int, float))
            self.assertGreaterEqual(result["response_time_ms"], 0)

    def test_monitoring_uses_it(self):
        from apps.observability.monitoring import SystemHealthMonitor

        db_health = SystemHealthMonitor.check_database_health()
        self.assertIn("status", db_health)
        self.assertIn(db_health["status"], ("healthy", "unhealthy"))

    def test_unhealthy_when_ensure_connection_fails(self):
        with patch(
            "apps.observability.db_liveness.connection.ensure_connection",
            side_effect=OperationalError("DB unavailable"),
        ):
            result = check_db_liveness()

        self.assertEqual(result["status"], "unhealthy")
        self.assertIn("DB unavailable", result["error"])

    def test_unhealthy_when_connection_not_usable(self):
        with patch(
            "apps.observability.db_liveness.connection.ensure_connection"
        ), patch(
            "apps.observability.db_liveness.connection.is_usable",
            return_value=False,
        ):
            result = check_db_liveness()

        self.assertEqual(result["status"], "unhealthy")
        self.assertIn("not usable", result["error"])

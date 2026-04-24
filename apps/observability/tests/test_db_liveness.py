"""
§2.4 Tests for db_liveness. Isolated from test_monitoring to avoid merge conflicts.
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase
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


class DbLivenessErrorShapeTests(SimpleTestCase):
    """Bucket C: stable operator-facing error payloads without requiring a live DB."""

    def test_unhealthy_truncates_error_at_200_chars(self):
        long_msg = "e" * 400
        with patch(
            "apps.observability.db_liveness.connection.ensure_connection",
            side_effect=OperationalError(long_msg),
        ):
            result = check_db_liveness()

        self.assertEqual(result["status"], "unhealthy")
        self.assertEqual(len(result["error"]), 200)
        self.assertTrue(result["error"].startswith("e"))


class DbLivenessHealthyShapeTests(SimpleTestCase):
    """Bucket C: stable healthy payload keys when connection APIs succeed (no live DB required)."""

    def test_healthy_includes_response_time_and_query_count(self):
        mock_conn = MagicMock()
        mock_conn.is_usable.return_value = True
        mock_conn.queries = [object(), object()]

        with patch("apps.observability.db_liveness.connection", mock_conn):
            result = check_db_liveness()

        self.assertEqual(result["status"], "healthy")
        self.assertIn("response_time_ms", result)
        self.assertIsInstance(result["response_time_ms"], (int, float))
        self.assertGreaterEqual(result["response_time_ms"], 0)
        self.assertEqual(result["connections"], 2)

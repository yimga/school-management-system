"""
§2.4 Tests for db_liveness (raw SQL wrap). Isolated from test_monitoring to avoid merge conflicts.
"""

from django.test import TestCase

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

"""#18 Observability — tests for the /healthz Celery queue-depth (backlog) probe.

Isolated from test_db_liveness / test_monitoring to avoid merge conflicts.

The queue-depth probe is fail-SOFT: /healthz must keep its normal 200 success
contract whether the broker reports a count, is unconfigured, or the probe
raises. These tests prove (a) the field is present + structured on success and
(b) a probe that raises NEVER turns /healthz into a 500.
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.urls import reverse

from apps.observability.views import _check_celery_queue_depth

# A DB-healthy result so /healthz reaches the best-effort sub-probes without a
# live database (healthz returns 500 only on DB failure — see views.healthz).
_DB_HEALTHY = {"status": "healthy", "response_time_ms": 1.0, "connections": 0}


class HealthzQueueDepthHelperTests(SimpleTestCase):
    """Direct unit tests of the helper's fail-soft contract."""

    def test_no_broker_reports_unavailable_not_degraded(self):
        # Eager mode (no CELERY_BROKER_URL): no queue exists, so the probe must
        # report a benign 'unavailable', never raise, never claim 'degraded'.
        with patch("apps.observability.views.settings.CELERY_BROKER_URL", "", create=True):
            result = _check_celery_queue_depth()
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("detail", result)

    def test_returns_ok_with_depth_when_broker_reports_count(self):
        declared = MagicMock()
        declared.message_count = 7
        conn = MagicMock()
        conn.default_channel.queue_declare.return_value = declared
        celery_app = MagicMock()
        celery_app.connection.return_value = conn
        celery_app.conf.task_default_queue = "celery"

        with patch("apps.observability.views.settings.CELERY_BROKER_URL", "redis://x:6379/0", create=True), \
                patch.dict("sys.modules", {"config.celery": MagicMock(app=celery_app)}):
            result = _check_celery_queue_depth()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["depth"], 7)
        self.assertEqual(result["queue"], "celery")

    def test_degraded_when_depth_exceeds_threshold(self):
        declared = MagicMock()
        declared.message_count = 5000
        conn = MagicMock()
        conn.default_channel.queue_declare.return_value = declared
        celery_app = MagicMock()
        celery_app.connection.return_value = conn
        celery_app.conf.task_default_queue = "celery"

        with patch("apps.observability.views.settings.CELERY_BROKER_URL", "redis://x:6379/0", create=True), \
                patch("apps.observability.views._queue_depth_warn_threshold", return_value=1000), \
                patch.dict("sys.modules", {"config.celery": MagicMock(app=celery_app)}):
            result = _check_celery_queue_depth()

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["depth"], 5000)

    def test_probe_failure_is_swallowed_to_unavailable(self):
        # Broker configured but the connection raises: must NOT propagate.
        celery_app = MagicMock()
        celery_app.connection.side_effect = RuntimeError("broker down")

        with patch("apps.observability.views.settings.CELERY_BROKER_URL", "redis://x:6379/0", create=True), \
                patch.dict("sys.modules", {"config.celery": MagicMock(app=celery_app)}):
            result = _check_celery_queue_depth()

        self.assertEqual(result["status"], "unavailable")
        self.assertIn("error", result)
        self.assertIn("broker down", result["error"])


class HealthzEndpointQueueDepthTests(SimpleTestCase):
    """End-to-end /healthz contract: the new field is present and fail-soft."""

    def test_healthz_includes_queue_depth_field_on_success(self):
        with patch("apps.observability.views.check_db_liveness", return_value=_DB_HEALTHY), \
                patch("apps.observability.views._check_cache_liveness", return_value={"status": "ok"}), \
                patch("apps.observability.views._check_celery_broker_liveness", return_value={"status": "ok"}), \
                patch(
                    "apps.observability.views._check_celery_queue_depth",
                    return_value={"status": "ok", "depth": 3, "queue": "celery"},
                ):
            response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        # Pre-existing keys preserved (no payload restructure).
        self.assertEqual(payload["database"], "ok")
        self.assertIn("cache", payload)
        self.assertIn("celery_broker", payload)
        # New structured field present.
        self.assertIn("celery_queue_depth", payload)
        self.assertEqual(payload["celery_queue_depth"]["status"], "ok")
        self.assertEqual(payload["celery_queue_depth"]["depth"], 3)

    def test_healthz_stays_200_when_broker_raises_inside_real_probe(self):
        # The load-bearing guarantee: the REAL helper swallows any broker
        # exception, so /healthz keeps its 200 success contract end-to-end even
        # when the broker raises mid-probe. (The view trusts the helper to be
        # fail-soft; this drives that exact path with the real helper, not a
        # mock that returns a pre-baked dict.)
        celery_app = MagicMock()
        celery_app.connection.side_effect = RuntimeError("kombu blew up mid-declare")

        with patch("apps.observability.views.check_db_liveness", return_value=_DB_HEALTHY), \
                patch("apps.observability.views._check_cache_liveness", return_value={"status": "ok"}), \
                patch("apps.observability.views._check_celery_broker_liveness", return_value={"status": "ok"}), \
                patch("apps.observability.views.settings.CELERY_BROKER_URL", "redis://x:6379/0", create=True), \
                patch.dict("sys.modules", {"config.celery": MagicMock(app=celery_app)}):
            response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["celery_queue_depth"]["status"], "unavailable")
        self.assertIn("error", payload["celery_queue_depth"])

    def test_healthz_200_when_passive_queue_declare_raises(self):
        # Different failure path: broker reachable, but the passive queue_declare
        # raises (e.g. queue not yet created on a fresh broker). Still fail-soft,
        # still 200, field degrades to 'unavailable'.
        conn = MagicMock()
        conn.default_channel.queue_declare.side_effect = RuntimeError("NOT_FOUND - no queue")
        celery_app = MagicMock()
        celery_app.connection.return_value = conn
        celery_app.conf.task_default_queue = "celery"

        with patch("apps.observability.views.check_db_liveness", return_value=_DB_HEALTHY), \
                patch("apps.observability.views._check_cache_liveness", return_value={"status": "ok"}), \
                patch("apps.observability.views._check_celery_broker_liveness", return_value={"status": "ok"}), \
                patch("apps.observability.views.settings.CELERY_BROKER_URL", "redis://x:6379/0", create=True), \
                patch.dict("sys.modules", {"config.celery": MagicMock(app=celery_app)}):
            response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["celery_queue_depth"]["status"], "unavailable")

"""#18 Observability — Wave 16 strict configured-deps for /healthz.

When Redis or CELERY_BROKER_URL are configured, cache/broker ``degraded``
must return HTTP 503. LocMem / eager stay soft-OK (CI-safe).
Queue-depth alone never flips the top-level status.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

_DB_HEALTHY = {"status": "healthy", "response_time_ms": 1.0, "connections": 0}


class HealthzStrictDepsTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _call_healthz(self):
        from apps.observability.views import healthz

        return healthz(self.factory.get("/healthz/"))

    def test_healthz_503_when_cache_degraded_and_redis_configured(self):
        with (
            patch("apps.observability.views.check_db_liveness", return_value=_DB_HEALTHY),
            patch(
                "apps.observability.views._check_cache_liveness",
                return_value={"status": "degraded", "error": "redis down"},
            ),
            patch(
                "apps.observability.views._check_celery_broker_liveness",
                return_value={"status": "ok"},
            ),
            patch(
                "apps.observability.views._check_celery_queue_depth",
                return_value={"status": "ok", "depth": 0, "queue": "celery"},
            ),
            patch("apps.observability.views._redis_cache_configured", return_value=True),
            patch("apps.observability.views.settings.CELERY_BROKER_URL", "", create=True),
        ):
            response = self._call_healthz()

        self.assertEqual(response.status_code, 503)
        payload = json.loads(response.content)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["cache"], "degraded")

    def test_healthz_503_when_broker_degraded_and_broker_url_set(self):
        with (
            patch("apps.observability.views.check_db_liveness", return_value=_DB_HEALTHY),
            patch(
                "apps.observability.views._check_cache_liveness",
                return_value={"status": "ok"},
            ),
            patch(
                "apps.observability.views._check_celery_broker_liveness",
                return_value={"status": "degraded", "error": "broker down"},
            ),
            patch(
                "apps.observability.views._check_celery_queue_depth",
                return_value={"status": "unavailable"},
            ),
            patch("apps.observability.views._redis_cache_configured", return_value=False),
            patch(
                "apps.observability.views.settings.CELERY_BROKER_URL",
                "redis://x:6379/0",
                create=True,
            ),
        ):
            response = self._call_healthz()

        self.assertEqual(response.status_code, 503)
        payload = json.loads(response.content)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["celery_broker"], "degraded")

    def test_healthz_200_when_cache_degraded_without_redis(self):
        with (
            patch("apps.observability.views.check_db_liveness", return_value=_DB_HEALTHY),
            patch(
                "apps.observability.views._check_cache_liveness",
                return_value={"status": "degraded"},
            ),
            patch(
                "apps.observability.views._check_celery_broker_liveness",
                return_value={"status": "unavailable"},
            ),
            patch(
                "apps.observability.views._check_celery_queue_depth",
                return_value={"status": "unavailable"},
            ),
            patch("apps.observability.views._redis_cache_configured", return_value=False),
            patch("apps.observability.views.settings.CELERY_BROKER_URL", "", create=True),
        ):
            response = self._call_healthz()

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["status"], "ok")

    def test_healthz_200_when_broker_degraded_without_broker_url(self):
        """Eager mode: broker helper returns unavailable; even a mock degraded stays soft."""
        with (
            patch("apps.observability.views.check_db_liveness", return_value=_DB_HEALTHY),
            patch(
                "apps.observability.views._check_cache_liveness",
                return_value={"status": "ok"},
            ),
            patch(
                "apps.observability.views._check_celery_broker_liveness",
                return_value={"status": "degraded"},
            ),
            patch(
                "apps.observability.views._check_celery_queue_depth",
                return_value={"status": "unavailable"},
            ),
            patch("apps.observability.views._redis_cache_configured", return_value=False),
            patch("apps.observability.views.settings.CELERY_BROKER_URL", "", create=True),
        ):
            response = self._call_healthz()

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["status"], "ok")

    def test_healthz_200_when_queue_depth_unavailable_but_broker_ok(self):
        with (
            patch("apps.observability.views.check_db_liveness", return_value=_DB_HEALTHY),
            patch(
                "apps.observability.views._check_cache_liveness",
                return_value={"status": "ok"},
            ),
            patch(
                "apps.observability.views._check_celery_broker_liveness",
                return_value={"status": "ok"},
            ),
            patch(
                "apps.observability.views._check_celery_queue_depth",
                return_value={"status": "unavailable", "error": "no queue"},
            ),
            patch("apps.observability.views._redis_cache_configured", return_value=False),
            patch(
                "apps.observability.views.settings.CELERY_BROKER_URL",
                "redis://x:6379/0",
                create=True,
            ),
        ):
            response = self._call_healthz()

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["celery_queue_depth"]["status"], "unavailable")


class BrokerLivenessUnavailableTests(SimpleTestCase):
    def test_empty_broker_url_reports_unavailable(self):
        from apps.observability.views import _check_celery_broker_liveness

        with patch("apps.observability.views.settings.CELERY_BROKER_URL", "", create=True):
            result = _check_celery_broker_liveness()
        self.assertEqual(result["status"], "unavailable")

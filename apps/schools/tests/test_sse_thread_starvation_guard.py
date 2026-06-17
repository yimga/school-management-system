"""Regression seal: dashboard SSE streams must not starve worker threads.

Incident (2026-06-17): the web service crash-looped — p90 ~2min, /health/ probe
timed out (5s) and Render killed the instance repeatedly, while CPU/RAM stayed
low (threads BLOCKED, not computing). Two amplifiers on the streaming side:
the globe / fleet-live / tenant-health SSE endpoints each held a gthread worker
thread for up to ONE HOUR (cap 3600s) with NO per-worker SSE slot guard, so a
few open operator/tenant tabs pinned every thread and /health/ got none.

Fix: route all three through ``guarded_sse_response`` (acquires an SSE slot or
returns a cheap busy frame) and cut the default hold from 3600s -> 30s.

This test proves the guard short-circuits when no slot is free: the view returns
immediately with a busy frame instead of entering the long-lived stream loop.
Hermetic — patches the slot acquirer, no DB, no real streaming.
"""
from unittest import mock

from django.test import SimpleTestCase


def _busy_body(response):
    return b"".join(
        chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
        for chunk in response.streaming_content
    )


class SseThreadStarvationGuardTests(SimpleTestCase):
    def _assert_busy_frame_when_no_slot(self, response):
        # The guard emits a single "event: busy" frame and ends, freeing the
        # thread at once — it never enters the underlying stream loop.
        self.assertTrue(response.streaming)
        body = _busy_body(response)
        self.assertIn(b"event: busy", body)
        self.assertIn(b"retry:", body)

    def test_default_caps_are_short_not_one_hour(self):
        from apps.schools import views_fleet_live as fleet
        from apps.schools import views_tenant_health_api as health
        from apps.siteconfig import views_globe_api as globe

        # A 1-hour hold is what pinned the threads; the defaults must be short.
        self.assertLessEqual(globe._SSE_MAX_SECONDS, 60)
        self.assertLessEqual(fleet._FLEET_SSE_MAX_SECONDS, 60)
        self.assertLessEqual(health._TENANT_HEALTH_SSE_MAX_SECONDS, 60)

    def test_globe_stream_returns_busy_when_no_slot(self):
        from apps.siteconfig.views_globe_api import GlobeStreamView

        with mock.patch(
            "services.sse_response.try_acquire_sse_slot", return_value=False
        ):
            response = GlobeStreamView().get(mock.Mock())
        self._assert_busy_frame_when_no_slot(response)

    def test_fleet_stream_returns_busy_when_no_slot(self):
        from apps.schools.views_fleet_live import FleetStreamView

        with mock.patch(
            "services.sse_response.try_acquire_sse_slot", return_value=False
        ):
            response = FleetStreamView().get(mock.Mock())
        self._assert_busy_frame_when_no_slot(response)

    def test_tenant_health_stream_returns_busy_when_no_slot(self):
        from apps.schools.views_tenant_health_api import TenantHealthStreamView

        with mock.patch(
            "services.sse_response.try_acquire_sse_slot", return_value=False
        ):
            response = TenantHealthStreamView().get(mock.Mock())
        self._assert_busy_frame_when_no_slot(response)

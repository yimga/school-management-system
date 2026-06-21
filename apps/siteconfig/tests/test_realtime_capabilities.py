"""Realtime transport capability flags."""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.siteconfig.realtime_capabilities import (
    is_asgi_web_tier,
    resolve_realtime_client_config,
    resolve_web_server_mode,
    sse_streams_client_enabled,
    wal_stream_client_enabled,
)


class RealtimeCapabilitiesTests(SimpleTestCase):
    @mock.patch.dict("os.environ", {"WEB_SERVER_MODE": "wsgi"}, clear=False)
    def test_default_web_tier_is_wsgi(self):
        self.assertEqual(resolve_web_server_mode(), "wsgi")
        self.assertFalse(is_asgi_web_tier())

    @mock.patch.dict("os.environ", {"WEB_SERVER_MODE": "asgi"}, clear=False)
    def test_asgi_mode_detected(self):
        self.assertEqual(resolve_web_server_mode(), "asgi")
        self.assertTrue(is_asgi_web_tier())

    @mock.patch.dict(
        "os.environ",
        {"WEB_SERVER_MODE": "wsgi", "RMC_WAL_STREAM_ENABLED": "1"},
        clear=False,
    )
    def test_wal_disabled_on_wsgi_even_when_env_set(self):
        self.assertFalse(wal_stream_client_enabled())

    @mock.patch.dict(
        "os.environ",
        {"WEB_SERVER_MODE": "asgi", "RMC_WAL_STREAM_ENABLED": "1"},
        clear=False,
    )
    def test_wal_enabled_on_asgi_when_opted_in(self):
        self.assertTrue(wal_stream_client_enabled())

    @mock.patch.dict("os.environ", {"RMC_SSE_STREAMS_ENABLED": "0"}, clear=False)
    def test_sse_can_be_disabled(self):
        self.assertFalse(sse_streams_client_enabled())

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_sse_enabled_by_default(self):
        self.assertTrue(sse_streams_client_enabled())

    @mock.patch.dict(
        "os.environ",
        {"WEB_SERVER_MODE": "wsgi", "RMC_WAL_STREAM_ENABLED": "1"},
        clear=False,
    )
    def test_client_config_payload(self):
        payload = resolve_realtime_client_config()
        self.assertEqual(payload["webServerMode"], "wsgi")
        self.assertFalse(payload["walStreamEnabled"])
        self.assertTrue(payload["sseStreamsEnabled"])

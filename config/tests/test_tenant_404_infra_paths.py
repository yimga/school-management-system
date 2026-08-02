"""The tenant 404 handler must not render the ~1.2 MB branded shell for WebSocket
handshakes that fall through to the WSGI HTTP layer.

On Render the tenant + manager web services are WSGI-only (no Channels/ASGI), so a
browser WebSocket handshake to ``/ws/notifications/`` reaches the HTTP 404 handler.
Rendering the full-shell branded "Campus Not Found" page (~1.2 MB) for it is pure
waste — the WS client discards the body and re-downloads it on every reconnect.
A ``/ws/*`` miss must short-circuit to a tiny plain 404, exactly like the existing
``/static/`` and ``/media/`` asset-miss guard.
"""

from __future__ import annotations

from unittest.mock import patch

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.test import SimpleTestCase

from config.tenant_urls import page_not_found


def _req(path: str) -> HttpRequest:
    request = HttpRequest()
    request.path = path
    return request


class TenantNotFoundInfraPathShortCircuitTests(SimpleTestCase):
    def test_ws_handshake_returns_plain_tiny_404(self):
        # Before the fix this delegated to the branded full-shell handler
        # (schools/404_tenant.html, ~1.2 MB) re-downloaded on every WS reconnect.
        with patch("apps.schools.error_views.school_not_found") as branded:
            response = page_not_found(_req("/ws/notifications/"), Exception())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content, b"Not found")
        branded.assert_not_called()

    def test_other_ws_paths_also_short_circuit(self):
        for path in ("/ws/wal/", "/ws/substitute-market/", "/ws/support/chat/"):
            with self.subTest(path=path):
                with patch("apps.schools.error_views.school_not_found") as branded:
                    response = page_not_found(_req(path), Exception())
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.content, b"Not found")
                branded.assert_not_called()

    def test_static_miss_still_plain_404(self):
        path = (settings.STATIC_URL or "/static/") + "app.css.map"
        with patch("apps.schools.error_views.school_not_found") as branded:
            response = page_not_found(_req(path), Exception())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content, b"Not found")
        branded.assert_not_called()

    def test_real_page_miss_still_uses_branded_handler(self):
        # A genuine page 404 on a live campus must still get the brand page — the
        # /ws/ guard must not swallow real navigational misses.
        sentinel = HttpResponse("branded", status=404)
        with patch(
            "apps.schools.error_views.school_not_found", return_value=sentinel
        ) as branded:
            response = page_not_found(_req("/academics/"), Exception())
        branded.assert_called_once()
        self.assertIs(response, sentinel)

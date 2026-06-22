"""Regression gate: error + offline pages must NEVER escalate to 500.

Root cause closed here (2026-06-21): tenant subdomains returned 500 for unknown
paths (e.g. ``/sw-manifest.json``) and for ``/offline/`` because the 404/offline
renders ran the full context-processor stack, and a tenant-scoped processor that
performs DB work for an anonymous hit raised — so the 404 handler itself threw and
Django escalated it to ``handler500``. The 500 handler was already bulletproof; the
404/403/503 handlers and the offline view were not. These tests lock the symmetry
so a future context-processor regression can degrade gracefully but can never again
take down a safety-net page (which is exactly what the service worker precaches and
what users hit when the network/DB is unreachable).

SimpleTestCase: no DB required — the failing-render path is simulated by patching
``render`` to raise, which is the whole point.
"""

from __future__ import annotations

from unittest import mock

from django.test import RequestFactory, SimpleTestCase

import config.error_handlers as eh
import config.urls as cu


class ErrorHandlerBulletproofTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_404_falls_back_to_static_when_render_raises(self):
        req = self.rf.get("/sw-manifest.json")
        with mock.patch.object(eh, "render", side_effect=RuntimeError("ctx boom")):
            resp = eh.page_not_found(req, Exception("nf"))
        self.assertEqual(resp.status_code, 404)
        self.assertIn(b"404", resp.content)

    def test_403_falls_back_to_static_when_render_raises(self):
        req = self.rf.get("/admin/")
        with mock.patch.object(eh, "render", side_effect=RuntimeError("ctx boom")):
            resp = eh.permission_denied(req, Exception("denied"))
        self.assertEqual(resp.status_code, 403)

    def test_503_falls_back_to_static_when_render_raises(self):
        req = self.rf.get("/")
        with mock.patch.object(eh, "render", side_effect=RuntimeError("ctx boom")):
            resp = eh.service_unavailable(req, Exception("down"))
        self.assertEqual(resp.status_code, 503)

    def test_500_handler_still_robust(self):
        req = self.rf.get("/")
        with mock.patch.object(eh, "render", side_effect=RuntimeError("boom")):
            resp = eh.server_error(req)
        self.assertEqual(resp.status_code, 500)


class OfflinePageBulletproofTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_offline_renders_without_context_processors_when_full_render_fails(self):
        # Simulates a tenant context-processor crash: the full render fails, but the
        # context-free render of the branded shell must still succeed (status 200).
        req = self.rf.get("/offline/")
        with mock.patch.object(cu, "render", side_effect=RuntimeError("ctx boom")):
            resp = cu.offline_page(req)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content)

    def test_offline_static_fallback_when_everything_fails(self):
        from django.template import loader

        req = self.rf.get("/offline/")
        with mock.patch.object(cu, "render", side_effect=RuntimeError("boom")), \
                mock.patch.object(loader, "render_to_string", side_effect=RuntimeError("boom2")):
            resp = cu.offline_page(req)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"offline", resp.content.lower())


class TenantNotFoundBulletproofTests(SimpleTestCase):
    """The tenant urlconf's handler404 -> school_not_found must also degrade to a
    clean 404, not a 500, when the branded render's context-processor stack raises.
    This is what made /sw-manifest.json and /offline/ (unmatched on the tenant) 500.
    """

    def setUp(self):
        self.rf = RequestFactory()

    def test_school_not_found_falls_back_to_static_when_render_raises(self):
        from apps.schools import error_views

        req = self.rf.get("/sw-manifest.json")
        with mock.patch.object(error_views, "render", side_effect=RuntimeError("ctx boom")):
            resp = error_views.school_not_found(req)
        self.assertEqual(resp.status_code, 404)
        self.assertIn(b"404", resp.content)

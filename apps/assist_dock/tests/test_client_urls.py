"""Assist dock client URL SOT."""

from __future__ import annotations

from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.assist_dock.client_urls import resolve_assist_dock_client_urls


class AssistDockClientUrlsTests(SimpleTestCase):
    def test_resolves_named_endpoints(self):
        request = RequestFactory().get("/portal/dashboard/")
        def _fake_reverse(name, kwargs=None):
            if kwargs and "action_id" in kwargs:
                return f"/mock/{name}/{kwargs['action_id']}/"
            return f"/mock/{name}/"

        with mock.patch("apps.assist_dock.client_urls.reverse", side_effect=_fake_reverse):
            urls = resolve_assist_dock_client_urls(request)
        self.assertTrue(urls["context"].startswith("/mock/"))
        self.assertIn("{action_id}", urls["ai_invoke"])

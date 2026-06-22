"""The stale-service-worker escape hatch (/sw-reset/) must resolve on EVERY host.

Root cause closed here: ``service_worker_reset`` was registered only in
``config.urls``. A tenant subdomain resolves through ``config.tenant_urls``,
marketing/public hosts through ``config.public_urls``, and the control plane
through ``config.manager_urls`` — none of which routed ``/sw-reset/``. So the
one-click "unregister the stuck worker + clear caches" page 404'd on exactly the
hosts where a stale cache-first service worker keeps serving days-old HTML after
a deploy (the "my changes never show up on the tenant" report).

Pure ``resolve`` against each urlconf — no DB, no middleware, no request.
"""

from __future__ import annotations

from importlib import import_module

from django.test import SimpleTestCase
from django.urls import resolve

from apps.siteconfig.views_service_worker import service_worker_reset


class SwResetRoutedOnAllHostsTests(SimpleTestCase):
    def _assert_routed(self, urlconf_module: str):
        match = resolve("/sw-reset/", urlconf=import_module(urlconf_module))
        self.assertIs(
            match.func,
            service_worker_reset,
            f"/sw-reset/ does not route to service_worker_reset under {urlconf_module}",
        )
        self.assertEqual(match.url_name, "service_worker_reset")

    def test_tenant_host_routes_sw_reset(self):
        self._assert_routed("config.tenant_urls")

    def test_public_host_routes_sw_reset(self):
        self._assert_routed("config.public_urls")

    def test_manager_host_routes_sw_reset(self):
        self._assert_routed("config.manager_urls")

    def test_default_urlconf_still_routes_sw_reset(self):
        self._assert_routed("config.urls")

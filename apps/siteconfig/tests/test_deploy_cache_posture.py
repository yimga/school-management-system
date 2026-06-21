from __future__ import annotations

from django.test import Client, SimpleTestCase, TestCase, override_settings

from apps.siteconfig.deploy_meta import read_service_worker_cache_version


class DeployMetaTests(SimpleTestCase):
    def test_read_service_worker_cache_version_matches_file(self):
        version = read_service_worker_cache_version()
        self.assertTrue(version.startswith("sms-v"))


class ServiceWorkerRootViewTests(TestCase):
    def test_sw_js_served_with_full_site_scope_header(self):
        response = Client().get("/sw.js")
        self.assertEqual(response.status_code, 200, msg=response.content[:200])
        self.assertIn("application/javascript", response["Content-Type"])
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn(b"CACHE_VERSION", response.content)

    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_sw_js_resolves_on_manager_urlconf(self):
        response = Client(HTTP_HOST="manager.runmycampus.com").get("/sw.js")
        self.assertEqual(response.status_code, 200, msg=response.content[:200])
        self.assertEqual(response["Service-Worker-Allowed"], "/")

    @override_settings(ROOT_URLCONF="config.public_urls")
    def test_sw_js_resolves_on_public_urlconf(self):
        response = Client(HTTP_HOST="runmycampus.com").get("/sw.js")
        self.assertEqual(response.status_code, 200, msg=response.content[:200])
        self.assertEqual(response["Service-Worker-Allowed"], "/")

    def test_scanner_middleware_does_not_block_sw_js(self):
        response = Client().get("/sw.js")
        self.assertNotEqual(response.status_code, 404)

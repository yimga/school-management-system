"""Tests for config (e.g. BlockScannerPathsMiddleware)."""
from django.http import HttpRequest
from django.test import SimpleTestCase

from config.middleware import BlockScannerPathsMiddleware


class BlockScannerPathsMiddlewareTests(SimpleTestCase):
    def test_root_path_passes_through(self):
        m = BlockScannerPathsMiddleware(lambda r: "ok")
        req = HttpRequest()
        req.path = "/"
        self.assertEqual(m(req), "ok")

    def test_normal_path_passes_through(self):
        m = BlockScannerPathsMiddleware(lambda r: "ok")
        req = HttpRequest()
        req.path = "/health/"
        self.assertEqual(m(req), "ok")

    def test_git_returns_404(self):
        m = BlockScannerPathsMiddleware(lambda r: "ok")
        req = HttpRequest()
        req.path = "/.git/config"
        resp = m(req)
        self.assertEqual(resp.status_code, 404)

    def test_terraform_returns_404(self):
        m = BlockScannerPathsMiddleware(lambda r: "ok")
        req = HttpRequest()
        req.path = "/terraform.tfstate"
        resp = m(req)
        self.assertEqual(resp.status_code, 404)

    def test_wp_config_returns_404(self):
        m = BlockScannerPathsMiddleware(lambda r: "ok")
        req = HttpRequest()
        req.path = "/wp-config.php.bak"
        resp = m(req)
        self.assertEqual(resp.status_code, 404)

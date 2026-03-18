"""Tests for config (e.g. BlockScannerPathsMiddleware, Part F 16.6 testing matrix)."""

from django.conf import settings
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


class TestingMatrixRegionsTests(SimpleTestCase):
    """Part F 16.6: Global testing matrix (USA, Brazil, Germany, Japan, Nigeria, UAE, Canada, UK)."""

    def test_testing_matrix_regions_defined(self):
        regions = getattr(settings, "TESTING_MATRIX_REGIONS", None)
        self.assertIsNotNone(regions)
        self.assertIsInstance(regions, list)

    def test_testing_matrix_covers_eight_regions(self):
        regions = getattr(settings, "TESTING_MATRIX_REGIONS", [])
        expected = {"US", "BR", "DE", "JP", "NG", "AE", "CA", "GB"}
        self.assertEqual(
            set(regions),
            expected,
            "TESTING_MATRIX_REGIONS must cover USA, BR, DE, JP, NG, AE, CA, UK (Part F 16.6)",
        )

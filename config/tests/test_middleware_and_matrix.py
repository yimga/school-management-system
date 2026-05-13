"""Tests for config middleware and the global testing matrix."""

from django.conf import settings
from django.http import HttpRequest
from django.test import SimpleTestCase

from config.middleware import BlockScannerPathsMiddleware


class BlockScannerPathsMiddlewareTests(SimpleTestCase):
    def test_root_path_passes_through(self):
        middleware = BlockScannerPathsMiddleware(lambda request: "ok")
        request = HttpRequest()
        request.path = "/"
        self.assertEqual(middleware(request), "ok")

    def test_normal_path_passes_through(self):
        middleware = BlockScannerPathsMiddleware(lambda request: "ok")
        request = HttpRequest()
        request.path = "/health/"
        self.assertEqual(middleware(request), "ok")

    def test_git_returns_404(self):
        middleware = BlockScannerPathsMiddleware(lambda request: "ok")
        request = HttpRequest()
        request.path = "/.git/config"
        response = middleware(request)
        self.assertEqual(response.status_code, 404)

    def test_terraform_returns_404(self):
        middleware = BlockScannerPathsMiddleware(lambda request: "ok")
        request = HttpRequest()
        request.path = "/terraform.tfstate"
        response = middleware(request)
        self.assertEqual(response.status_code, 404)

    def test_wp_config_returns_404(self):
        middleware = BlockScannerPathsMiddleware(lambda request: "ok")
        request = HttpRequest()
        request.path = "/wp-config.php.bak"
        response = middleware(request)
        self.assertEqual(response.status_code, 404)


class TestingMatrixRegionsTests(SimpleTestCase):
    """Part F 16.6: Global testing matrix."""

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

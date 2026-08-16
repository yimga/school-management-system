import unittest

from scripts.verify_approved_ui_deploy_artifacts import parse_cache_version


class ApprovedUiDeployArtifactTests(unittest.TestCase):
    def test_accepts_future_monotonic_cache_release(self):
        source = 'const CACHE_VERSION = "sms-v4.06.99-future-ui-2026-08-16";'
        self.assertEqual(parse_cache_version(source), (4, 6, 99))

    def test_rejects_missing_or_malformed_cache_declaration(self):
        self.assertIsNone(parse_cache_version("const CACHE_VERSION = 'sms-v4.06.44';"))
        self.assertIsNone(parse_cache_version("// no service worker version"))


if __name__ == "__main__":
    unittest.main()

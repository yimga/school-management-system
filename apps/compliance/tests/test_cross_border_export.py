"""Cross-border export gate (strict mode only)."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from apps.compliance.cross_border_export import cross_border_export_blocked


class CrossBorderExportTests(TestCase):
    def test_soft_mode_allows_mismatch(self):
        school = SimpleNamespace(data_region="eu-central-1")
        blocked, _ = cross_border_export_blocked(
            school,
            destination_region="us-east-1",
        )
        self.assertFalse(blocked)

    @patch.dict("os.environ", {"DATA_RESIDENCY_ENFORCE": "1"}, clear=False)
    def test_strict_mode_blocks_mismatch(self):
        school = SimpleNamespace(data_region="eu-central-1")
        blocked, msg = cross_border_export_blocked(
            school,
            destination_region="us-east-1",
        )
        self.assertTrue(blocked)
        self.assertIn("blocked", msg.lower())

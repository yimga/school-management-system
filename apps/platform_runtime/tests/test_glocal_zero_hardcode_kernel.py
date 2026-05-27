"""Contract pins for Glocal Zero-Hardcode kernel (batch 1529)."""

from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.schools.data_residency import GLOBAL_DATA_REGION


class GlocalZeroHardcodeKernelTests(SimpleTestCase):
    def test_manifest_rejects_crdt_edge_iam_admin(self):
        text = (
            Path(__file__).resolve().parents[2]
            / "accounts"
            / "permission_manifest.py"
        ).read_text(encoding="utf-8")
        self.assertIn("crdt_edge_iam_admin", text)
        self.assertIn('"REJECTED"', text)

    @patch("apps.platform_runtime.models.RuntimeDefaults")
    def test_derive_default_region_germany(self, mock_rd):
        mock_rd.objects.order_by.return_value.first.return_value = None
        from apps.schools.data_residency import derive_default_region

        self.assertEqual(derive_default_region("DE"), "eu_central")

    @patch("apps.platform_runtime.models.RuntimeDefaults")
    def test_derive_default_region_empty_is_global(self, mock_rd):
        mock_rd.objects.order_by.return_value.first.return_value = None
        from apps.schools.data_residency import derive_default_region

        self.assertEqual(derive_default_region(""), GLOBAL_DATA_REGION)

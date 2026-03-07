from unittest.mock import patch

from django.test import SimpleTestCase

from apps.finance.ocr_runtime import get_ocr_runtime_status
from apps.finance.receipt_verification import ReceiptVerificationService


class OcrRuntimeStatusTests(SimpleTestCase):
    def test_pattern_mode_is_always_ready(self):
        status = get_ocr_runtime_status("pattern")
        self.assertTrue(status["ready"])
        self.assertEqual(status["provider"], "pattern")

    @patch.dict("os.environ", {}, clear=True)
    def test_google_cloud_mode_reports_missing_credentials(self):
        status = get_ocr_runtime_status("ocr_cloud_google")
        self.assertFalse(status["ready"])
        self.assertIn("GOOGLE_CLOUD_VISION_API_KEY", " ".join(status["missing"]))

    @patch.dict("os.environ", {"AWS_ACCESS_KEY_ID": "k", "AWS_SECRET_ACCESS_KEY": "s"}, clear=True)
    def test_aws_mode_requires_region(self):
        status = get_ocr_runtime_status("ocr_cloud_aws")
        self.assertFalse(status["ready"])
        self.assertIn("AWS_DEFAULT_REGION", " ".join(status["missing"]))

    def test_receipt_service_uses_custom_ocr_command_for_runtime(self):
        service = ReceiptVerificationService(
            verification_method="ocr_tesseract",
            marksheet_ocr_command="custom-tesseract-wrapper",
        )
        self.assertTrue(service.runtime_status["ready"])

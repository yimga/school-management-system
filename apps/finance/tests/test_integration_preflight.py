from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.platform_runtime.helpers import get_platform_site_settings_record


class IntegrationPreflightCommandTests(TestCase):
    def setUp(self):
        site = get_platform_site_settings_record(create=True)
        flags = {
            **dict(site.get_backend_feature_flags()),
            "enable_ocr_scan_teller": False,
            "enable_ministry_api_cartescolaire": False,
            "enable_ministry_api_dgi": False,
            "enable_ministry_live_sync": False,
        }
        site.apply_feature_control_state(
            backend_feature_flags=flags,
            field_updates={"finance_receipt_verification_method": "pattern"},
        )

    def test_preflight_json_outputs_runtime_status(self):
        out = StringIO()
        call_command("integration_preflight", "--json", stdout=out)
        payload = json.loads(out.getvalue())
        self.assertIn("ocr", payload)
        self.assertIn("ministry", payload)
        self.assertIn("status", payload["ocr"])
        self.assertIn("status", payload["ministry"])

    @patch.dict("os.environ", {}, clear=True)
    def test_preflight_fails_when_ocr_feature_enabled_but_runtime_missing(self):
        site = get_platform_site_settings_record(create=True)
        flags = {
            **dict(site.get_backend_feature_flags()),
            "enable_ocr_scan_teller": True,
        }
        site.apply_feature_control_state(
            backend_feature_flags=flags,
            field_updates={"finance_receipt_verification_method": "ocr_cloud_google"},
        )

        with self.assertRaises(SystemExit) as exc:
            call_command("integration_preflight")
        self.assertEqual(exc.exception.code, 2)

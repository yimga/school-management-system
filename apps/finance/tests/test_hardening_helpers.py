from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.finance.tasks import _get_finance_runtime_config, _get_marketplace_integration_settings
from apps.finance.views import _backend_flags


class FinanceHardeningHelperTests(SimpleTestCase):
    def test_backend_flags_returns_empty_dict_when_runtime_lookup_fails(self):
        request = RequestFactory().get("/finance/")

        with patch("apps.finance.views.get_effective_flags", side_effect=RuntimeError("runtime unavailable")):
            self.assertEqual(_backend_flags(request), {})

    def test_finance_runtime_config_prefers_owner_accessor(self):
        site = type(
            "SettingsStub",
            (),
            {
                "get_finance_runtime_config": lambda self: {
                    "reminder_max_retries": 7,
                    "invoice_auto_status_updates_enabled": False,
                }
            },
        )()

        config = _get_finance_runtime_config(site)

        self.assertEqual(config["reminder_max_retries"], 7)
        self.assertFalse(config["invoice_auto_status_updates_enabled"])

    def test_marketplace_integration_settings_prefers_owner_accessor(self):
        site = type(
            "SettingsStub",
            (),
            {
                "get_marketplace_integration_settings": lambda self: {
                    "marksheet_ocr_command": "/usr/bin/tesseract"
                }
            },
        )()

        config = _get_marketplace_integration_settings(site)

        self.assertEqual(config["marksheet_ocr_command"], "/usr/bin/tesseract")

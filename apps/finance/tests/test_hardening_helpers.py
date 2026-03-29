from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.finance.tasks import (
    FINANCE_TASK_RETRYABLE_FAILURES,
    _get_finance_runtime_config,
    auto_copy_fee_plans_task,
    auto_generate_fee_invoices_task,
    process_payment_receipt_upload_task,
    retry_bank_verification_task,
    update_invoice_statuses_task,
)
from apps.platform_runtime.helpers import get_effective_marketplace_integration_settings
from apps.finance.views_common import _backend_flags, _notification_delivery_settings


class FinanceHardeningHelperTests(SimpleTestCase):
    def test_backend_flags_returns_empty_dict_when_runtime_lookup_fails(self):
        request = RequestFactory().get("/finance/")

        with patch(
            "apps.finance.views_common.get_effective_flags",
            side_effect=RuntimeError("runtime unavailable"),
        ):
            self.assertEqual(_backend_flags(request), {})

    def test_finance_runtime_config_prefers_owner_accessor(self):
        site = type(
            "SettingsStub",
            (),
            {
                "get_finance_runtime_config": lambda self: {
                    "reminder_max_retries": 7,
                    "invoice_auto_status_updates_enabled": False,
                    "receipt_upload_enabled": False,
                    "receipt_allowed_extensions": "pdf,png",
                }
            },
        )()

        config = _get_finance_runtime_config(site)

        self.assertEqual(config["reminder_max_retries"], 7)
        self.assertFalse(config["invoice_auto_status_updates_enabled"])
        self.assertFalse(config["receipt_upload_enabled"])
        self.assertEqual(config["receipt_allowed_extensions"], "pdf,png")

    def test_effective_marketplace_integration_settings_uses_facade_method(self):
        site = type(
            "SettingsStub",
            (),
            {
                "get_marketplace_integration_settings": lambda self: {
                    "marksheet_ocr_command": "/usr/bin/tesseract"
                }
            },
        )()

        with patch(
            "apps.platform_runtime.helpers.get_effective_site_settings",
            return_value=site,
        ):
            config = get_effective_marketplace_integration_settings()

        self.assertEqual(config["marksheet_ocr_command"], "/usr/bin/tesseract")

    def test_effective_marketplace_integration_settings_defaults_when_no_site(self):
        with patch(
            "apps.platform_runtime.helpers.get_effective_site_settings",
            return_value=None,
        ):
            config = get_effective_marketplace_integration_settings()
        self.assertEqual(config["marksheet_ocr_command"], "")
        self.assertEqual(config["sms_provider"], "console")
        self.assertEqual(config["sms_sender_id"], "RUNMYCAMPUS")

    def test_notification_delivery_settings_prefers_owner_accessor(self):
        site = type(
            "SettingsStub",
            (),
            {
                "get_notification_delivery_settings": lambda self: {
                    "notification_channels": ["email", "sms"],
                    "email_from_address": "ops@runmycampus.test",
                }
            },
        )()

        channels, from_email = _notification_delivery_settings(site=site)

        self.assertEqual(channels, ["email", "sms"])
        self.assertEqual(from_email, "ops@runmycampus.test")

    def test_finance_task_autoretry_contract_is_limited_to_retryable_failures(self):
        for task in (
            auto_generate_fee_invoices_task,
            auto_copy_fee_plans_task,
            update_invoice_statuses_task,
            process_payment_receipt_upload_task,
            retry_bank_verification_task,
        ):
            self.assertEqual(
                task.autoretry_for,
                FINANCE_TASK_RETRYABLE_FAILURES,
            )

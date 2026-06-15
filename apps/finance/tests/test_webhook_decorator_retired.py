"""Address-the-backlog (2026-06-15) — dead webhook_security_required retired.

Plain ``unittest`` (no DB).

apps/finance/security.py once defined a ``webhook_security_required`` decorator
(Phase 0) that was applied to NO view, referenced a ``PaymentIntegration`` model
that was never built (so it would ImportError if ever applied), and was
superseded by the live, routed ``views_payments.py::payment_provider_webhook``
which performs the same HMAC / IP / rate-limit / WebhookLog checks inline using
``WebhookSecurityValidator``. The dead decorator was retired; the live security
classes remain.
"""

from __future__ import annotations

import os
import unittest

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()


class WebhookDecoratorRetiredTests(unittest.TestCase):

    def test_dead_decorator_gone(self) -> None:
        import apps.finance.security as s

        self.assertFalse(hasattr(s, "webhook_security_required"))

    def test_live_security_classes_kept(self) -> None:
        import apps.finance.security as s

        for keep in (
            "PaymentValidator",
            "WebhookSecurityValidator",
            "PaymentEncryption",
            "FraudDetector",
        ):
            self.assertTrue(hasattr(s, keep), f"{keep} must remain")

    def test_no_phantom_paymentintegration_import(self) -> None:
        import inspect

        import apps.finance.security as s

        src = inspect.getsource(s)
        # The phantom must not be imported or queried (a mention in the
        # retirement NOTE comment is fine).
        self.assertNotIn("import PaymentIntegration", src)
        self.assertNotIn("PaymentIntegration.objects", src)

    def test_live_webhook_handler_still_imports(self) -> None:
        # The routed handler must still import its security deps cleanly.
        from apps.finance.views_payments import payment_provider_webhook  # noqa: F401


if __name__ == "__main__":
    unittest.main()

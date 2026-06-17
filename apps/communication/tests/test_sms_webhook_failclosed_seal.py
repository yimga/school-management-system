"""Regression seal: inbound SMS webhook must fail closed in production.

Bug (2026-06-17 gap analysis): _signature_ok() returned True when NO auth mechanism was
configured, so in prod (no Twilio signature + no shared secret) anyone could POST and
forge SMS consent (STOP=withdraw / START=grant) for any phone number. Fix: accept the
no-auth case only under DEBUG (local dev); fail closed otherwise.
"""
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.communication.views_sms_inbound_webhook import _signature_ok


class SmsWebhookFailClosedSealTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _req(self, **extra):
        return self.factory.post(
            "/communication/sms/inbound/",
            data={"From": "+15550000000", "Body": "STOP"},
            **extra,
        )

    @override_settings(
        DEBUG=False,
        RMC_SMS_WEBHOOK_SHARED_SECRET="",
        RMC_SMS_WEBHOOK_REQUIRE_TWILIO_SIGNATURE=False,
    )
    def test_prod_no_auth_fails_closed(self):
        self.assertFalse(_signature_ok(self._req()))

    @override_settings(
        DEBUG=True,
        RMC_SMS_WEBHOOK_SHARED_SECRET="",
        RMC_SMS_WEBHOOK_REQUIRE_TWILIO_SIGNATURE=False,
    )
    def test_dev_no_auth_accepts(self):
        self.assertTrue(_signature_ok(self._req()))

    @override_settings(DEBUG=False, RMC_SMS_WEBHOOK_SHARED_SECRET="s3cret-value")
    def test_prod_valid_shared_secret_accepts(self):
        req = self.factory.post(
            "/communication/sms/inbound/",
            data={"From": "+15550000000"},
            HTTP_X_RMC_SMS_SECRET="s3cret-value",
        )
        self.assertTrue(_signature_ok(req))

    @override_settings(DEBUG=False, RMC_SMS_WEBHOOK_SHARED_SECRET="s3cret-value")
    def test_prod_wrong_shared_secret_rejected(self):
        req = self.factory.post(
            "/communication/sms/inbound/",
            data={"From": "+15550000000"},
            HTTP_X_RMC_SMS_SECRET="not-the-secret",
        )
        self.assertFalse(_signature_ok(req))

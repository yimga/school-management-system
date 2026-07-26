"""M7: write-time validation + operator command for webhook signature schemes.

The request path already fails CLOSED on an unknown scheme; this covers the
write-time twin — an operator can only STORE a recognised scheme, so a typo is
caught while configuring rather than as silent 403s after the PSP goes live.
"""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from apps.finance.webhooks.signature_dispatch import is_recognized_scheme
from apps.integrations_marketplace.models import Integration


class IsRecognizedSchemePureTests(SimpleTestCase):
    def test_absent_and_generic_are_accepted(self):
        for value in ("", None, "generic_hmac", "GENERIC_HMAC", "  generic_hmac  "):
            self.assertTrue(is_recognized_scheme(value), value)

    def test_provider_accurate_schemes_accepted_case_and_space_insensitive(self):
        for value in ("stripe", "STRIPE", " paystack ", "Flutterwave", "mpesa_daraja", "aggregator_hmac"):
            self.assertTrue(is_recognized_scheme(value), value)

    def test_typos_and_unknowns_rejected(self):
        for value in ("strpe", "paystackk", "unknown", "hmac", "sha256"):
            self.assertFalse(is_recognized_scheme(value), value)


class SetSignatureSchemeCommandTests(TestCase):
    def setUp(self):
        self.integration = Integration.objects.create(
            name="Stripe",
            slug="stripe",
            provider="payments",
            enabled=True,
            config={"provider_slug": "stripe", "webhook_secret": "whsec_x"},
        )

    def _run(self, **kwargs):
        out = StringIO()
        call_command("set_payment_webhook_signature_scheme", stdout=out, **kwargs)
        return out.getvalue()

    def test_sets_recognized_scheme(self):
        self._run(provider_slug="stripe", scheme="stripe")
        self.integration.refresh_from_db()
        self.assertEqual(self.integration.config["signature_scheme"], "stripe")

    def test_resolves_by_config_provider_slug(self):
        # Integration.slug differs from the provider slug in config.
        other = Integration.objects.create(
            name="MTN MoMo", slug="mtn-momo-cm", provider="payments", enabled=True,
            config={"provider_slug": "mtn_momo"},
        )
        self._run(provider_slug="mtn_momo", scheme="aggregator_hmac")
        other.refresh_from_db()
        self.assertEqual(other.config["signature_scheme"], "aggregator_hmac")

    def test_unknown_scheme_is_rejected_and_nothing_persisted(self):
        with self.assertRaises(CommandError):
            self._run(provider_slug="stripe", scheme="strpe")
        self.integration.refresh_from_db()
        self.assertNotIn("signature_scheme", self.integration.config)

    def test_unknown_provider_slug_raises(self):
        with self.assertRaises(CommandError):
            self._run(provider_slug="does-not-exist", scheme="stripe")

    def test_dry_run_does_not_persist(self):
        out = self._run(provider_slug="stripe", scheme="stripe", dry_run=True)
        self.assertIn("dry-run", out)
        self.integration.refresh_from_db()
        self.assertNotIn("signature_scheme", self.integration.config)

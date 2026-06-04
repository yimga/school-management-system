"""Pillar 3 — Verified Communications: DKIM email signing posture tests."""

from __future__ import annotations

import os
import unittest.mock as mock

from django.test import SimpleTestCase, override_settings

from apps.communication.email_signing import (
    DKIM_SIGNING_BACKENDS,
    EmailSigningMisconfigured,
    NON_SIGNING_BACKENDS,
    assert_dkim_configured,
    email_signing_status,
)


class EmailSigningStatusTests(SimpleTestCase):
    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        EMAIL_SIGNING_REQUIRED=False,
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_console_backend_reports_no_dkim(self):
        status = email_signing_status()
        self.assertEqual(
            status["backend"],
            "django.core.mail.backends.console.EmailBackend",
        )
        self.assertFalse(status["signs_dkim"])
        self.assertEqual(status["provider"], "Django console (dev)")
        self.assertFalse(status["required"])
        self.assertEqual(status["default_from"], "noreply@example.com")

    @override_settings(
        EMAIL_BACKEND="anymail.backends.mailgun.EmailBackend",
        EMAIL_SIGNING_REQUIRED=True,
    )
    def test_anymail_mailgun_backend_reports_dkim(self):
        status = email_signing_status()
        self.assertTrue(status["signs_dkim"])
        self.assertEqual(status["provider"], "Mailgun")
        self.assertTrue(status["required"])

    @override_settings(
        EMAIL_BACKEND="anymail.backends.sendgrid.EmailBackend",
    )
    def test_sendgrid_also_recognized(self):
        # Cross-check that the matrix isn't accidentally Mailgun-only.
        status = email_signing_status()
        self.assertTrue(status["signs_dkim"])
        self.assertEqual(status["provider"], "SendGrid")

    @override_settings(EMAIL_BACKEND="some.unknown.Backend")
    def test_unknown_backend_marked_unsigned(self):
        status = email_signing_status()
        self.assertFalse(status["signs_dkim"])
        self.assertEqual(status["provider"], "Unknown backend")


class AssertDkimConfiguredTests(SimpleTestCase):
    @override_settings(
        EMAIL_BACKEND="anymail.backends.postmark.EmailBackend",
        EMAIL_SIGNING_REQUIRED=True,
    )
    def test_signing_backend_passes(self):
        # Should not raise; returns the status dict.
        status = assert_dkim_configured()
        self.assertTrue(status["signs_dkim"])
        self.assertEqual(status["provider"], "Postmark")

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        EMAIL_SIGNING_REQUIRED=False,
    )
    def test_soft_warn_when_not_required(self):
        # In dev posture (REQUIRED=False), a non-signing backend must
        # only log a warning and never raise.
        with self.assertLogs("apps.communication.email_signing", level="WARNING") as cm:
            status = assert_dkim_configured()
        self.assertFalse(status["signs_dkim"])
        self.assertTrue(any("does NOT sign DKIM" in line for line in cm.output))

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        EMAIL_SIGNING_REQUIRED=False,
    )
    def test_render_hosted_console_downgrades_to_debug(self):
        with mock.patch.dict(os.environ, {"RENDER": "true"}, clear=False):
            with self.assertLogs(
                "apps.communication.email_signing", level="DEBUG"
            ) as cm:
                status = assert_dkim_configured()
        self.assertFalse(status["signs_dkim"])
        self.assertTrue(any("does NOT sign DKIM" in line for line in cm.output))

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_SIGNING_REQUIRED=True,
        # Pin EMAIL_HOST to a non-relay host so this asserts the genuine
        # misconfig path. Under audit H13 an SMTP backend pointing at a KNOWN
        # signing relay (Brevo/SendGrid/...) legitimately signs and must NOT
        # raise; without this override the test would be env-dependent on
        # whatever EMAIL_HOST the local .env happens to carry.
        EMAIL_HOST="mail.unknown-relay.example",
        EMAIL_DKIM_RELAY_TRUSTED="",
    )
    def test_required_setting_raises_on_misconfig(self):
        with self.assertRaises(EmailSigningMisconfigured) as ctx:
            assert_dkim_configured()
        self.assertIn("does NOT sign DKIM", str(ctx.exception))

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_SIGNING_REQUIRED=True,
        EMAIL_HOST="smtp-relay.brevo.com",
    )
    def test_smtp_pointing_at_known_relay_signs(self):
        # Audit H13: the plain SMTP backend aimed at a known DKIM-signing relay
        # IS signed at the relay edge — the gate must pass, not hard-block.
        status = assert_dkim_configured()
        self.assertTrue(status["signs_dkim"])
        self.assertIn("Brevo", status["provider"])


class ProviderMatrixSanityTests(SimpleTestCase):
    def test_matrices_are_disjoint(self):
        # Belt + braces: a backend cannot be both signing and non-signing.
        overlap = set(DKIM_SIGNING_BACKENDS) & set(NON_SIGNING_BACKENDS)
        self.assertEqual(overlap, set())

    def test_known_signing_providers_present(self):
        for required in (
            "anymail.backends.mailgun.EmailBackend",
            "anymail.backends.sendgrid.EmailBackend",
            "anymail.backends.postmark.EmailBackend",
            "anymail.backends.amazon_ses.EmailBackend",
        ):
            self.assertIn(required, DKIM_SIGNING_BACKENDS)

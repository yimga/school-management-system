"""The SendGrid bounce webhook must refuse an unverifiable signature.

``/email/webhook/sendgrid/`` is anonymous and CSRF-exempt by design, so the
ECDSA signature is the ONLY thing standing between the internet and
``suppress_recipient()``. Before this fix an unverifiable signature fell through
to accept-unverified whenever the operator had not opted in, which let anyone
blackhole any address the platform mails (password resets, invoices, activation
links) with one POST.

``test_unverified_post_is_accepted_when_the_operator_opts_in`` is the vacuity
guard: it fires the SAME forged POST with the legacy fallback explicitly enabled
and asserts the suppression row IS written. That proves the request reaches the
suppression path — so the 401 in the other tests is the signature gate, not a
routing miss, a parser reject, or a 404.
"""

from __future__ import annotations

import json
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.schoolops.models_email_suppression import SuppressedRecipient
from apps.schoolops.views_email_webhook import _hash_recipient

_VICTIM = "head@victim-school.example"
_FORGED_BODY = json.dumps(
    [{"event": "bounce", "type": "blocked", "email": _VICTIM}]
)
# Well-formed base64 that is not a usable P-256 key: verification cannot
# succeed, which is exactly the state a forged POST arrives in.
_OPERATOR_SECRET = "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="


class SendgridWebhookFailsClosedTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.url = reverse("email_provider_webhook", args=["sendgrid"])
        patcher = mock.patch(
            "apps.schoolops.views_email_webhook._load_webhook_secrets",
            return_value={"sendgrid": _OPERATOR_SECRET},
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    def _post(self):
        return self.client.post(
            self.url,
            data=_FORGED_BODY,
            content_type="application/json",
            HTTP_X_TWILIO_EMAIL_EVENT_WEBHOOK_SIGNATURE="AAAA",
            HTTP_X_TWILIO_EMAIL_EVENT_WEBHOOK_TIMESTAMP="1755900000",
        )

    def _suppressed(self):
        return SuppressedRecipient.objects.filter(
            to_hash=_hash_recipient(_VICTIM)
        ).exists()

    def test_forged_signature_is_rejected_and_suppresses_nobody(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(self._suppressed())

    @override_settings(SCHOOLOPS_SENDGRID_ALLOW_UNVERIFIED_WEBHOOK=True)
    def test_unverified_post_is_accepted_when_the_operator_opts_in(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self._suppressed())

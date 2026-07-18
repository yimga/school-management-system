"""transactional_email_configured: honest, no-network "can we deliver?" preflight.

The predicate exists so operator-facing paths (resend command, on-deploy dispatch)
can say "mail isn't configured" up front instead of reporting a bland "skipped"
when the Brevo secrets are empty. Hermetic — patches the config resolver so no DB
or SMTP is touched.
"""
from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.schoolops import email_delivery


class TransactionalEmailConfiguredTests(SimpleTestCase):
    def _cfg(self, **over):
        base = {"host": "smtp.example.com", "host_user": "u", "host_password": "p"}
        base.update(over)
        return base

    def test_true_when_host_and_credentials_present(self):
        with mock.patch.object(
            email_delivery, "get_resolved_smtp_config", return_value=self._cfg()
        ):
            self.assertTrue(email_delivery.transactional_email_configured())

    def test_false_when_password_empty(self):
        with mock.patch.object(
            email_delivery,
            "get_resolved_smtp_config",
            return_value=self._cfg(host_password=""),
        ):
            self.assertFalse(email_delivery.transactional_email_configured())

    def test_false_when_user_empty(self):
        with mock.patch.object(
            email_delivery,
            "get_resolved_smtp_config",
            return_value=self._cfg(host_user=""),
        ):
            self.assertFalse(email_delivery.transactional_email_configured())

    def test_false_when_host_empty(self):
        with mock.patch.object(
            email_delivery, "get_resolved_smtp_config", return_value=self._cfg(host="")
        ):
            self.assertFalse(email_delivery.transactional_email_configured())

    def test_false_when_resolver_raises(self):
        # A preflight predicate must never propagate — a broken resolver reads as
        # "not configured", not a 500.
        with mock.patch.object(
            email_delivery,
            "get_resolved_smtp_config",
            side_effect=RuntimeError("boom"),
        ):
            self.assertFalse(email_delivery.transactional_email_configured())

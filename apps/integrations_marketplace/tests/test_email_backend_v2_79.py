"""Tests for v2.79 additions to `apps.integrations_marketplace.email_backend`.

Specifically covers `_ANYMAIL_KEY_MAP`, `_anymail_settings_for(...)`,
`_tenant_anymail_settings(...)` context manager, and the thread-local
tenant binding API. DB-free where possible (uses SimpleTestCase + the
override_settings primitive directly).
"""

from __future__ import annotations

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from apps.integrations_marketplace import email_backend
from apps.integrations_marketplace.email_backend import (
    _ANYMAIL_KEY_MAP,
    _active_school,
    _anymail_settings_for,
    _tenant_anymail_settings,
    bind_tenant_for_email,
    clear_tenant_for_email,
)


class _FakeSchool:
    def __init__(self, name="acme"):
        self.name = name

    def __repr__(self):
        return f"<FakeSchool {self.name!r}>"


class AnymailKeyMapShapeTests(SimpleTestCase):
    """Lock the per-provider key translation so a silent rename breaks the test
    instead of silently misconfiguring Anymail for every tenant on that ESP."""

    def test_known_providers_present(self):
        for slug in (
            "mailgun", "sendgrid", "postmark", "amazon_ses",
            "sparkpost", "brevo", "mandrill", "mailersend",
            "mailjet", "resend",
        ):
            with self.subTest(slug=slug):
                self.assertIn(slug, _ANYMAIL_KEY_MAP)

    def test_mailgun_maps_to_anymail_canonical_keys(self):
        self.assertEqual(
            _ANYMAIL_KEY_MAP["mailgun"],
            {"api_key": "MAILGUN_API_KEY", "sender_domain": "MAILGUN_SENDER_DOMAIN"},
        )

    def test_mailjet_carries_both_key_and_secret(self):
        m = _ANYMAIL_KEY_MAP["mailjet"]
        self.assertIn("api_key", m)
        self.assertIn("secret_key", m)


class AnymailSettingsForTests(SimpleTestCase):
    def test_unknown_slug_returns_none(self):
        self.assertIsNone(_anymail_settings_for("never-heard-of-it", {"api_key": "x"}))

    def test_returns_none_when_config_is_empty(self):
        self.assertIsNone(_anymail_settings_for("sendgrid", {}))

    def test_returns_only_keys_present_in_config(self):
        result = _anymail_settings_for("mailgun", {"api_key": "abc"})
        self.assertEqual(result, {"MAILGUN_API_KEY": "abc"})

    def test_amazon_ses_nests_into_client_params(self):
        result = _anymail_settings_for("amazon_ses", {
            "access_key_id": "AKIA",
            "secret_access_key": "SECRET",
            "region": "us-east-1",
        })
        self.assertEqual(
            result,
            {"AMAZON_SES_CLIENT_PARAMS": {
                "aws_access_key_id": "AKIA",
                "aws_secret_access_key": "SECRET",
                "region_name": "us-east-1",
            }},
        )

    def test_amazon_ses_with_no_keys_returns_none(self):
        self.assertIsNone(_anymail_settings_for("amazon_ses", {}))

    def test_values_are_coerced_to_str(self):
        # Defensive: a Postmark server token coming back from JSON as int
        # shouldn't blow up when handed to Anymail.
        result = _anymail_settings_for("postmark", {"server_token": 42})
        self.assertEqual(result, {"POSTMARK_SERVER_TOKEN": "42"})


class TenantAnymailSettingsContextTests(SimpleTestCase):
    @override_settings(ANYMAIL={"BASE_KEY": "base_value"})
    def test_overrides_merge_with_existing_anymail(self):
        with _tenant_anymail_settings({"MAILGUN_API_KEY": "tenant-key"}):
            self.assertEqual(settings.ANYMAIL["BASE_KEY"], "base_value")
            self.assertEqual(settings.ANYMAIL["MAILGUN_API_KEY"], "tenant-key")
        # After the context exits the override is rolled back.
        self.assertNotIn("MAILGUN_API_KEY", settings.ANYMAIL)
        self.assertEqual(settings.ANYMAIL["BASE_KEY"], "base_value")

    @override_settings(ANYMAIL={"MAILGUN_API_KEY": "global-platform-key"})
    def test_tenant_override_wins_over_global(self):
        with _tenant_anymail_settings({"MAILGUN_API_KEY": "per-tenant-key"}):
            self.assertEqual(settings.ANYMAIL["MAILGUN_API_KEY"], "per-tenant-key")
        # Snapped back.
        self.assertEqual(settings.ANYMAIL["MAILGUN_API_KEY"], "global-platform-key")

    def test_none_overrides_is_a_noop(self):
        with _tenant_anymail_settings(None):
            pass  # Just must not raise.


class ThreadLocalTenantBindingTests(SimpleTestCase):
    def tearDown(self):
        clear_tenant_for_email()

    def test_explicit_kwarg_beats_thread_local(self):
        bind_tenant_for_email(_FakeSchool("from-thread-local"))
        explicit = _FakeSchool("from-kwarg")
        result = _active_school({"school": explicit})
        self.assertIs(result, explicit)

    def test_thread_local_used_when_no_explicit_kwarg(self):
        s = _FakeSchool("from-thread-local")
        bind_tenant_for_email(s)
        result = _active_school({})
        self.assertIs(result, s)

    def test_returns_none_when_nothing_bound(self):
        self.assertIsNone(_active_school({}))
        self.assertIsNone(_active_school({"school": None}))

    def test_clear_removes_thread_local(self):
        bind_tenant_for_email(_FakeSchool("temp"))
        clear_tenant_for_email()
        self.assertIsNone(_active_school({}))

    def test_clear_when_nothing_bound_is_safe(self):
        clear_tenant_for_email()  # Must not raise.

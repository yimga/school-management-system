"""Per-tenant email backend — picks the right Anymail/SMTP backend per tenant."""

from __future__ import annotations

from unittest import mock

from django.core.mail import EmailMessage
from django.test import TestCase, override_settings

from apps.integrations_marketplace.email_backend import (
    PerTenantEmailBackend,
    bind_tenant_for_email,
    clear_tenant_for_email,
)
from apps.schools.models import School
from apps.siteconfig.models_platform_catalog import ServiceIntegration


class _StubBackend:
    instances: list["_StubBackend"] = []

    def __init__(self, fail_silently=False, **kwargs):
        self.fail_silently = fail_silently
        self.kwargs = kwargs
        self.sent = 0
        _StubBackend.instances.append(self)

    def send_messages(self, messages):
        self.sent = len(messages)
        return self.sent


class PerTenantEmailBackendTests(TestCase):
    def setUp(self):
        _StubBackend.instances.clear()
        self.school = School.objects.create(name="Mail Tenant A")
        clear_tenant_for_email()

    def tearDown(self):
        clear_tenant_for_email()

    def _make_provider_row(self, *, slug, anymail_path, config=None):
        ServiceIntegration.objects.create(
            school=self.school,
            connector_slug=slug,
            service_name=slug,
            service_type=ServiceIntegration.ServiceType.OAUTH,
            config=config or {"connector_slug": slug, "api_key": "k"},
            is_active=True,
        )

    @override_settings(EMAIL_BACKEND_FALLBACK="apps.integrations_marketplace.tests.test_email_backend._StubBackend")
    def test_no_tenant_uses_global_fallback(self):
        backend = PerTenantEmailBackend()
        msg = EmailMessage(subject="x", body="y", from_email="a@b.c", to=["d@e.f"])
        backend.send_messages([msg])
        self.assertEqual(len(_StubBackend.instances), 1)
        self.assertEqual(_StubBackend.instances[0].sent, 1)

    @override_settings(EMAIL_BACKEND_FALLBACK="apps.integrations_marketplace.tests.test_email_backend._StubBackend")
    def test_tenant_without_provider_uses_fallback(self):
        bind_tenant_for_email(self.school)
        backend = PerTenantEmailBackend()
        msg = EmailMessage(subject="x", body="y", from_email="a@b.c", to=["d@e.f"])
        backend.send_messages([msg])
        self.assertEqual(len(_StubBackend.instances), 1)

    def test_tenant_with_sendgrid_picks_sendgrid_backend(self):
        self._make_provider_row(
            slug="sendgrid",
            anymail_path="anymail.backends.sendgrid.EmailBackend",
            config={"connector_slug": "sendgrid", "api_key": "SG.xxx"},
        )
        bind_tenant_for_email(self.school)

        # Stub the import to avoid importing the real anymail package in tests.
        with mock.patch(
            "apps.integrations_marketplace.email_backend.import_string",
            return_value=_StubBackend,
        ) as imp:
            backend = PerTenantEmailBackend()
            msg = EmailMessage(subject="x", body="y", from_email="a@b.c", to=["d@e.f"])
            backend.send_messages([msg])

        # First call should be the sendgrid backend dotted path.
        called_with = [c.args[0] for c in imp.call_args_list]
        self.assertIn("anymail.backends.sendgrid.EmailBackend", called_with)
        self.assertEqual(_StubBackend.instances[-1].sent, 1)

    def test_smtp_row_passes_typed_kwargs(self):
        self._make_provider_row(
            slug="smtp_generic",
            anymail_path="django.core.mail.backends.smtp.EmailBackend",
            config={
                "connector_slug": "smtp_generic",
                "host": "smtp.example.com",
                "port": 587,
                "username": "u",
                "password": "p",
                "use_tls": True,
            },
        )
        bind_tenant_for_email(self.school)
        with mock.patch(
            "apps.integrations_marketplace.email_backend.import_string",
            return_value=_StubBackend,
        ):
            backend = PerTenantEmailBackend()
            msg = EmailMessage(subject="x", body="y", from_email="a@b.c", to=["d@e.f"])
            backend.send_messages([msg])

        last = _StubBackend.instances[-1]
        self.assertEqual(last.kwargs.get("host"), "smtp.example.com")
        self.assertEqual(last.kwargs.get("port"), 587)
        self.assertEqual(last.kwargs.get("username"), "u")
        self.assertTrue(last.kwargs.get("use_tls"))

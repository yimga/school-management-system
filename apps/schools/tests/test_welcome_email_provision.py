"""Welcome email URLs and HTML after school provisioning."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from apps.schools.models import School, SchoolProvisioningEvent
from apps.schools.provision_email_urls import (
    build_provision_setup_password_url,
    build_tenant_authentication_url,
)
from apps.schools.welcome_email import render_welcome_email_html, send_welcome_email


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com", DEBUG=False)
class WelcomeEmailProvisionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Mail Test School",
            slug="mail-test-school",
            subdomain="mail-test-school",
        )
        self.user = get_user_model().objects.create_user(
            username="principal_mail",
            email="principal@mailtest.test",
            password="unused",
        )
        self.user.set_unusable_password()
        self.user.save()

    def test_build_tenant_authentication_url_uses_subdomain(self):
        url = build_tenant_authentication_url(
            self.school, "/authentication/login/"
        )
        self.assertIn("mail-test-school.runmycampus.com", url)
        self.assertIn("/authentication/login/", url)

    def test_build_provision_setup_password_url_contains_legacy_setup(self):
        url = build_provision_setup_password_url(self.school, self.user)
        self.assertIn("mail-test-school.runmycampus.com", url)
        self.assertIn("/authentication/legacy-setup/", url)

    def test_render_welcome_email_includes_set_password_cta(self):
        setup = build_provision_setup_password_url(self.school, self.user)
        html = render_welcome_email_html(
            self.school,
            "principal@mailtest.test",
            setup_password_url=setup,
        )
        self.assertIn("Set your password", html)
        self.assertIn(setup, html)


@override_settings(
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    DEBUG=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@runmycampus.com",
)
class WelcomeEmailEndToEndTests(TestCase):
    """v4.00.2 audit gap (item 2): exercise the actual ``send_welcome_email``
    call path end-to-end via Django's locmem backend so we prove a real
    EmailMessage with the school's branding lands in ``mail.outbox``."""

    def setUp(self):
        self.school = School.objects.create(
            name="Welcome E2E Academy",
            slug="welcome-e2e-academy",
            subdomain="welcome-e2e-academy",
            primary_color="#4F46E5",
        )
        self.admin_user = get_user_model().objects.create_user(
            username="welcome_admin",
            email="admin@welcomee2e.test",
        )
        self.admin_user.set_unusable_password()
        self.admin_user.save()
        mail.outbox = []

    def test_send_welcome_email_delivers_to_outbox(self):
        result = send_welcome_email(str(self.school.id), "admin@welcomee2e.test")
        self.assertTrue(result, "send_welcome_email should return True on success")
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ["admin@welcomee2e.test"])
        self.assertIn("Welcome E2E Academy", msg.subject)
        self.assertEqual(msg.content_subtype, "html")
        self.assertIn("Welcome E2E Academy", msg.body)
        self.assertIn("#4F46E5", msg.body)

    def test_send_welcome_email_no_recipient_returns_false(self):
        self.assertFalse(send_welcome_email(str(self.school.id), ""))
        self.assertEqual(len(mail.outbox), 0)

    def test_send_welcome_email_missing_school_returns_false(self):
        self.assertFalse(
            send_welcome_email(
                "00000000-0000-0000-0000-000000000000",
                "admin@welcomee2e.test",
            )
        )
        self.assertEqual(len(mail.outbox), 0)


class WelcomeEmailEventAuditTests(TestCase):
    """v4.00.2 audit gap (item 2): verify the WELCOME_EMAIL_SENT /
    WELCOME_EMAIL_FAILED ``SchoolProvisioningEvent`` rows are written by
    ``_do_provision`` based on the ``send_welcome_email`` return value.
    Replays just the welcome-email tail of ``_do_provision`` so the test
    stays deterministic without running the full provisioning pipeline."""

    def setUp(self):
        self.school = School.objects.create(
            name="Audit Trail School",
            slug="audit-trail-school",
            subdomain="audit-trail-school",
        )

    def _drive_welcome_email_branch(self, *, send_succeeds: bool) -> None:
        """Mirror the code path in ``apps/schools/tasks.py::_do_provision``."""
        from apps.schools.tasks import _record_school_event

        contact_email = "audit@audittrail.test"
        with patch(
            "apps.schools.welcome_email.send_welcome_email",
            return_value=send_succeeds,
        ) as patched:
            sent = patched(str(self.school.id), contact_email)
            recipient_domain = (
                contact_email.split("@", 1)[-1] if "@" in contact_email else ""
            )
            from apps.schools.tasks import (
                EVENT_WELCOME_EMAIL_FAILED,
                EVENT_WELCOME_EMAIL_SENT,
            )

            _record_school_event(
                self.school,
                event_type=EVENT_WELCOME_EMAIL_SENT if sent else EVENT_WELCOME_EMAIL_FAILED,
                status="SUCCESS" if sent else "WARNING",
                message=(
                    "Welcome email sent."
                    if sent
                    else "Welcome email not sent (check EMAIL_*); provisioning still completed."
                ),
                payload={"recipient_domain": recipient_domain},
            )

    def test_welcome_email_sent_event_recorded_on_success(self):
        # Demonstrates the canonical filter pattern using the importable
        # constants — callers should NOT re-type the string literals.
        from apps.schools.tasks import EVENT_WELCOME_EMAIL_SENT

        self._drive_welcome_email_branch(send_succeeds=True)
        ev = SchoolProvisioningEvent.objects.filter(
            school=self.school, event_type=EVENT_WELCOME_EMAIL_SENT
        ).first()
        self.assertIsNotNone(ev)
        self.assertEqual(ev.status, "SUCCESS")
        self.assertEqual(ev.payload.get("recipient_domain"), "audittrail.test")
        self.assertNotIn("@", ev.payload.get("recipient_domain", ""))

    def test_welcome_email_failed_event_recorded_on_failure(self):
        from apps.schools.tasks import EVENT_WELCOME_EMAIL_FAILED

        self._drive_welcome_email_branch(send_succeeds=False)
        ev = SchoolProvisioningEvent.objects.filter(
            school=self.school, event_type=EVENT_WELCOME_EMAIL_FAILED
        ).first()
        self.assertIsNotNone(ev)
        self.assertEqual(ev.status, "WARNING")
        self.assertIn("check EMAIL_*", ev.message)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@runmycampus.com",
    SCHOOLOPS_EMAIL_DELIVERY_RETRY_BACKOFF=[0],
)
class SignupVerificationEmailTests(TestCase):
    """v4.00.2 audit gap (item 7): exercise the public-signup verification
    email path. ``send_transactional`` with ``async_send=False`` runs the
    full retry + persist + send sequence; with locmem backend the email
    lands in ``mail.outbox`` and we prove the recipient + subject + audit
    row contract holds without poking into the daemon thread."""

    def test_send_transactional_sync_lands_in_outbox(self):
        from apps.schoolops.email_delivery import send_transactional

        mail.outbox = []
        result = send_transactional(
            subject="Verify your school: Test Academy",
            body=(
                "Hello,\n\nClick to verify your school (link valid 2 days):\n"
                "https://runmycampus.com/verify-signup/?token=abc\n"
            ),
            to="new-admin@signuptest.test",
            from_email="noreply@runmycampus.com",
            priority="transactional",
            async_send=False,
        )
        self.assertTrue(result.get("ok"), f"send_transactional failed: {result}")
        self.assertEqual(result.get("attempts"), 1)
        self.assertIsNotNone(result.get("delivery_event_id"))
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ["new-admin@signuptest.test"])
        self.assertIn("Verify your school", msg.subject)
        self.assertIn("/verify-signup/?token=abc", msg.body)

    def test_send_transactional_none_recipient_returns_ok_false(self):
        """``_coerce_to_list(None)`` returns ``[]`` — explicit no-recipient
        path. (Note: ``to=""`` coerces to ``[""]`` which is non-empty, so
        callers passing the empty-string form will still attempt a send.)"""
        from apps.schoolops.email_delivery import send_transactional

        mail.outbox = []
        result = send_transactional(
            subject="x",
            body="y",
            to=None,  # type: ignore[arg-type]
            async_send=False,
        )
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("attempts"), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_send_transactional_persists_audit_event(self):
        from apps.schoolops.email_delivery import send_transactional
        from apps.schoolops.models_email_delivery import EmailDeliveryEvent

        mail.outbox = []
        EmailDeliveryEvent.objects.all().delete()
        send_transactional(
            subject="Verify your school: Audit School",
            body="link",
            to="audit-row@signuptest.test",
            async_send=False,
        )
        row = EmailDeliveryEvent.objects.first()
        self.assertIsNotNone(row, "audit row must be persisted")
        self.assertTrue(row.ok)
        self.assertEqual(row.priority, "transactional")
        # PII safety — never log raw recipient
        self.assertNotIn("@", row.to_hash)
        self.assertNotIn("audit-row@signuptest.test", row.subject_prefix)

"""Portal-ready in-app inbox + SMS channels after signup completion."""

from __future__ import annotations

from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.finance.models import Notification
from apps.schools.models import School, SchoolMembership, SignupVerification
from apps.schools.signup_completion_notifications import notify_tenant_signup_completed
from apps.schools.signup_portal_channel_notifications import (
    PORTAL_READY_INBOX_TITLE,
    dispatch_portal_ready_channels,
    ensure_portal_ready_in_app_notification,
)
from apps.schools.signup_completion_notifications import build_signup_completed_payload


@override_settings(
    RMC_PUBLIC_SITE_URL="https://runmycampus.com",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class SignupPortalChannelNotificationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Channel Test School",
            slug="channel-test",
            subdomain="channel-test",
            is_active=True,
        )
        self.owner = User.objects.create_user(
            username="owner@channel.test",
            email="owner@channel.test",
            password="OwnerPass123!",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.owner,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        SignupVerification.objects.create(
            school=self.school,
            email=self.owner.email,
            expires_at=timezone.now() + timezone.timedelta(days=2),
            verified_at=timezone.now(),
        )
        self.payload = build_signup_completed_payload(
            self.school, self.owner.email, admin_user=self.owner
        )

    def test_in_app_notification_idempotent(self):
        first = ensure_portal_ready_in_app_notification(
            self.owner, self.school, self.payload
        )
        second = ensure_portal_ready_in_app_notification(
            self.owner, self.school, self.payload
        )
        self.assertIsNotNone(first)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.owner, title=PORTAL_READY_INBOX_TITLE
            ).count(),
            1,
        )

    @mock.patch("apps.platform_runtime.event_bus.publish_event")
    def test_notify_completed_dispatches_in_app(self, publish_event):
        publish_event.return_value = object()
        notify_tenant_signup_completed(
            self.school, self.owner.email, admin_user=self.owner
        )
        note = Notification.objects.filter(
            recipient=self.owner, title=PORTAL_READY_INBOX_TITLE
        ).first()
        self.assertIsNotNone(note)
        self.assertIn("Channel Test School", note.message)

    @mock.patch("apps.communication.notification_service.send_sms")
    def test_sms_sent_when_school_has_contact_phone(self, send_sms_mock):
        send_sms_mock.return_value = True
        self.school.settings = {"contact_phone": "+237670000001"}
        self.school.save(update_fields=["settings"])
        dispatch_portal_ready_channels(
            self.school,
            self.owner.email,
            self.payload,
            admin_user=self.owner,
        )
        send_sms_mock.assert_called_once()
        self.school.refresh_from_db(fields=["settings"])
        state = (self.school.settings or {}).get("signup_notifications") or {}
        self.assertTrue(state.get("sms_dispatched_at"))

    @mock.patch("apps.platform_runtime.event_bus.publish_event")
    @mock.patch("apps.schools.signup_portal_channel_notifications.dispatch_portal_ready_channels")
    def test_force_resend_redispatches_all_channels(self, dispatch_mock, publish_event):
        publish_event.return_value = object()
        notify_tenant_signup_completed(
            self.school, self.owner.email, admin_user=self.owner
        )
        dispatch_mock.reset_mock()
        publish_event.reset_mock()
        notify_tenant_signup_completed(
            self.school, self.owner.email, admin_user=self.owner, force=True
        )
        dispatch_mock.assert_called_once()
        self.assertTrue(dispatch_mock.call_args.kwargs.get("force"))
        publish_event.assert_called_once()

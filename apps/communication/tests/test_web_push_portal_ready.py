"""Web Push subscription + portal-ready push dispatch tests."""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.communication.models_web_push import WebPushSubscription
from apps.communication.web_push_service import upsert_web_push_subscription
from apps.schools.models import School, SchoolMembership
from apps.schools.signup_completion_notifications import build_signup_completed_payload
from apps.schools.signup_portal_channel_notifications import notify_portal_ready_web_push


@override_settings(
    WEB_PUSH_VAPID_PUBLIC_KEY="test-public-key",
    WEB_PUSH_VAPID_PRIVATE_KEY="test-private-key",
    WEB_PUSH_VAPID_CLAIMS_EMAIL="mailto:push@test.runmycampus.com",
)
class WebPushPortalReadyTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Push Test School",
            slug="push-test",
            subdomain="push-test",
            is_active=True,
        )
        self.owner = User.objects.create_user(
            username="owner@push.test",
            email="owner@push.test",
            password="OwnerPass123!",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.owner,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        self.payload = build_signup_completed_payload(
            self.school, self.owner.email, admin_user=self.owner
        )
        upsert_web_push_subscription(
            self.owner,
            {
                "endpoint": "https://push.example.test/sub/1",
                "keys": {"p256dh": "abc", "auth": "def"},
            },
        )

    @mock.patch("apps.communication.web_push_service.send_web_push")
    def test_portal_ready_web_push_marks_state(self, send_mock):
        send_mock.return_value = True
        sent = notify_portal_ready_web_push(
            self.owner, self.school, self.payload
        )
        self.assertEqual(sent, 1)
        self.school.refresh_from_db(fields=["settings"])
        state = (self.school.settings or {}).get("signup_notifications") or {}
        self.assertTrue(state.get("web_push_dispatched_at"))

    @mock.patch("apps.communication.web_push_service.send_web_push")
    def test_portal_ready_web_push_idempotent(self, send_mock):
        send_mock.return_value = True
        notify_portal_ready_web_push(self.owner, self.school, self.payload)
        send_mock.reset_mock()
        sent = notify_portal_ready_web_push(
            self.owner, self.school, self.payload
        )
        self.assertEqual(sent, 0)
        send_mock.assert_not_called()


@override_settings(
    WEB_PUSH_VAPID_PUBLIC_KEY="test-public-key",
    WEB_PUSH_VAPID_PRIVATE_KEY="test-private-key",
)
class WebPushSubscribeViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="pushview@test",
            email="pushview@test",
            password="Pass1234!",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_vapid_public_key_requires_auth(self):
        anon = Client()
        response = anon.get(reverse("accounts:web_push_vapid_public_key"))
        self.assertEqual(response.status_code, 302)

    def test_subscribe_persists_subscription(self):
        response = self.client.post(
            reverse("accounts:web_push_subscribe"),
            data={
                "endpoint": "https://push.example.test/sub/view",
                "keys": {"p256dh": "key1", "auth": "key2"},
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            WebPushSubscription.objects.filter(
                user=self.user, endpoint="https://push.example.test/sub/view"
            ).exists()
        )

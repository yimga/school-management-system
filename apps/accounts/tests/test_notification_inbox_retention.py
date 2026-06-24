"""Notification inbox retention — dismiss + expires_at visibility (GAP-4/5)."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.views import _notification_inbox_queryset
from apps.finance.models import Notification
from apps.schools.models import School
import uuid


class NotificationInboxRetentionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="inbox_retention", email="ret@example.com", password="pwd"
        )
        tag = uuid.uuid4().hex[:8]
        cls.school_a = School.objects.create(
            name="School A",
            slug=f"school-a-{tag}",
            subdomain=f"school-a-{tag}",
            is_active=False,
        )
        cls.school_b = School.objects.create(
            name="School B",
            slug=f"school-b-{tag}",
            subdomain=f"school-b-{tag}",
            is_active=False,
        )

    def setUp(self):
        self.client = Client()

    def test_dismiss_hides_from_inbox_but_keeps_row(self):
        note = Notification.objects.create(
            recipient=self.user,
            title="Dismiss me",
            message="payload",
            is_read=False,
        )
        self.client.force_login(self.user)
        url = reverse("accounts:notification_dismiss", args=[note.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        note.refresh_from_db()
        self.assertIsNotNone(note.dismissed_at)
        self.assertTrue(note.is_read)
        inbox = self.client.get(reverse("accounts:user_notifications"))
        self.assertNotContains(inbox, "Dismiss me")

    def test_expired_notification_hidden_from_inbox(self):
        Notification.objects.create(
            recipient=self.user,
            title="Expired row",
            message="payload",
            expires_at=timezone.now() - timedelta(hours=1),
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:user_notifications"))
        self.assertNotContains(response, "Expired row")

    def test_school_scoped_inbox_excludes_other_tenant_rows(self):
        Notification.objects.create(
            recipient=self.user,
            title="Tenant A only",
            message="payload",
            school=self.school_a,
        )
        Notification.objects.create(
            recipient=self.user,
            title="Tenant B leak",
            message="payload",
            school=self.school_b,
        )
        request = RequestFactory().get("/notifications/")
        request.user = self.user
        request.school = self.school_a
        titles = list(
            _notification_inbox_queryset(request).values_list("title", flat=True)
        )
        self.assertIn("Tenant A only", titles)
        self.assertNotIn("Tenant B leak", titles)

"""HTTP coverage for tenant event analytics surface."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Permission
from apps.events.models import DomainEvent, WebhookDelivery, WebhookSubscription
from apps.platform_runtime.models import PlatformEventLog
from apps.schools.models import School

User = get_user_model()


def _tenant_host(school: School) -> str:
    return f"{school.subdomain}.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["*"], ROOT_URLCONF="config.tenant_urls")
class EventAnalyticsConsoleTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.school = School.objects.create(
            name="Analytics School",
            slug="analytics-school",
            subdomain="analytics-school",
            is_active=True,
        )
        self.staff = User.objects.create_user(
            username="analytics_staff",
            password="pw",
            is_staff=True,
            role=User.Role.IT_ADMIN,
        )
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.staff.feature_permissions.add(manage_perm)

    def test_analytics_requires_staff(self):
        url = reverse("events:event_analytics_console")
        resp = self.client.get(url, HTTP_HOST=_tenant_host(self.school))
        self.assertEqual(resp.status_code, 302)

    def test_analytics_counts_by_type_and_replay_metric(self):
        DomainEvent.objects.create(
            event_type="payment_success",
            payload={"x": 1},
            school_id=self.school.pk,
            status=DomainEvent.Status.PROCESSED,
            processed_at=timezone.now(),
        )
        DomainEvent.objects.create(
            event_type="student_created",
            payload={"x": 2},
            school_id=self.school.pk,
            status=DomainEvent.Status.PENDING,
        )
        PlatformEventLog.objects.create(
            event_type="platform_event_replayed",
            payload={"school_id": str(self.school.pk)},
            school_id=str(self.school.pk),
        )
        PlatformEventLog.objects.create(
            event_type="report_generated",
            payload={"school_id": str(self.school.pk)},
            school_id=str(self.school.pk),
        )

        sub = WebhookSubscription.objects.create(
            school_id=self.school.pk,
            url="https://hook.example/out",
            event_types=["payment_success"],
            secret="x",
            is_active=True,
        )
        ev = DomainEvent.objects.filter(event_type="payment_success").first()
        WebhookDelivery.objects.create(
            subscription=sub,
            domain_event=ev,
            status=WebhookDelivery.Status.DELIVERED,
            http_status=200,
            delivered_at=timezone.now(),
        )

        self.client.force_login(self.staff)
        url = reverse("events:event_analytics_console")
        resp = self.client.get(url, HTTP_HOST=_tenant_host(self.school))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("payment_success", body)
        self.assertIn("student_created", body)
        self.assertIn("Replay audits", body)
        self.assertIn("1", body)

        filtered = self.client.get(
            f"{url}?event_type=payment_success&newest_limit=5",
            HTTP_HOST=_tenant_host(self.school),
        )
        self.assertEqual(filtered.status_code, 200)
        fb = filtered.content.decode()
        self.assertNotIn("student_created", fb)

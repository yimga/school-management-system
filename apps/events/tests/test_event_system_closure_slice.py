"""
Section 11.4 event_system closure slice: tenant-safe operator console + unified replay UX.

Workflow replay semantics for attendance_saved + webhook idempotency are fully exercised in
``apps.platform_runtime.tests.test_platform_loop_attendance_workflow_webhook``;
this module proves routing, tenancy guards, visibility, domain clone replay audit metadata,
and platform webhook replay dedupe at the HTTP/console surface.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.http import Http404

from apps.accounts.models import Permission
from apps.events.bus import clear_subscribers_for_tests, subscribe
from apps.events.models import DomainEvent, WebhookDelivery, WebhookSubscription
from apps.events.views_console import event_console, event_domain_detail
from apps.platform_runtime import event_bus
from apps.platform_runtime.events import EVENT_CATALOG
from apps.platform_runtime.models import (
    EventWebhookDelivery,
    EventWebhookSubscription,
    PlatformEventLog,
)
from apps.platform_runtime.tasks import deliver_event_webhook_task
from apps.schools.models import School

User = get_user_model()

_CRITICAL_TYPES = (
    "attendance_saved",
    "payment_success",
    "report_generated",
    "app_installed",
)


def _tenant_host(school: School) -> str:
    return f"{school.subdomain}.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["*"], ROOT_URLCONF="config.tenant_urls")
class EventSystemClosureSliceTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.school_a = School.objects.create(
            name="Event Slice A",
            slug="event-slice-a",
            subdomain="event-slice-a",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="Event Slice B",
            slug="event-slice-b",
            subdomain="event-slice-b",
            is_active=True,
        )
        self.staff = User.objects.create_user(
            username="event_console_staff",
            password="pw",
            is_staff=True,
            role=User.Role.IT_ADMIN,
        )
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.staff.feature_permissions.add(manage_perm)
        self.student = User.objects.create_user(
            username="event_console_student",
            password="pw",
            is_staff=False,
            role=User.Role.STUDENT,
        )

    def tearDown(self):
        clear_subscribers_for_tests()
        super().tearDown()

    def test_critical_slice_event_types_registered_in_catalog(self):
        for key in _CRITICAL_TYPES:
            self.assertIn(key, EVENT_CATALOG, msg=f"missing catalog entry for {key}")

    def test_event_console_staff_returns_200_on_tenant_host(self):
        sid = str(self.school_a.pk)
        for et in _CRITICAL_TYPES:
            event_bus.publish_event(
                et,
                {"school_id": sid, "slice": "closure"},
                school_id=self.school_a.pk,
                strict_catalog=True,
                idempotency_key=f"closure-{et}-1",
            )
        self.client.force_login(self.staff)
        url = reverse("events:event_console")
        resp = self.client.get(url, HTTP_HOST=_tenant_host(self.school_a))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        for et in _CRITICAL_TYPES:
            self.assertIn(et, body)

    def test_event_console_blocks_non_staff(self):
        self.client.force_login(self.student)
        url = reverse("events:event_console")
        resp = self.client.get(url, HTTP_HOST=_tenant_host(self.school_a))
        self.assertEqual(resp.status_code, 403)

    def test_event_console_requires_login(self):
        url = reverse("events:event_console")
        resp = self.client.get(url, HTTP_HOST=_tenant_host(self.school_a))
        self.assertEqual(resp.status_code, 302)

    def test_domain_detail_foreign_tenant_returns_404(self):
        ev_b = DomainEvent.objects.create(
            event_type="payment_success",
            payload={"note": "b-only"},
            school_id=self.school_b.pk,
            status=DomainEvent.Status.PROCESSED,
            processed_at=timezone.now(),
        )
        factory = RequestFactory()
        req = factory.get(
            reverse("events:event_domain_detail", kwargs={"event_id": ev_b.pk})
        )
        req.user = self.staff
        req.school = self.school_a
        with self.assertRaises(Http404):
            event_domain_detail(req, event_id=ev_b.pk)

    def test_domain_detail_shows_payload_summary_and_webhook_status(self):
        sub = WebhookSubscription.objects.create(
            school_id=self.school_a.pk,
            url="https://example.invalid/hook",
            event_types=["payment_success"],
            secret="x",
            is_active=True,
        )
        ev = DomainEvent.objects.create(
            event_type="payment_success",
            payload={"invoice_id": "inv-1", "school_id": str(self.school_a.pk)},
            school_id=self.school_a.pk,
            status=DomainEvent.Status.PROCESSED,
            processed_at=timezone.now(),
        )
        WebhookDelivery.objects.create(
            subscription=sub,
            domain_event=ev,
            status=WebhookDelivery.Status.FAILED,
            http_status=500,
            retry_count=2,
        )
        factory = RequestFactory()
        req = factory.get(
            reverse("events:event_domain_detail", kwargs={"event_id": ev.pk})
        )
        req.user = self.staff
        req.school = self.school_a
        resp = event_domain_detail(req, event_id=ev.pk)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("invoice_id", content)
        self.assertIn("https://example.invalid/hook", content)
        self.assertIn(WebhookDelivery.Status.FAILED, content)

    def test_domain_replay_via_http_clone_preserves_source_payload_and_invokes_subscriber(self):
        seen: list[str] = []

        def handler(domain_event):
            seen.append(str(domain_event.id))

        subscribe("payment_success", handler)

        ev = DomainEvent.objects.create(
            event_type="payment_success",
            payload={"amount": "10", "school_id": str(self.school_a.pk)},
            school_id=self.school_a.pk,
            status=DomainEvent.Status.PROCESSED,
            processed_at=timezone.now(),
        )
        src_payload = dict(ev.payload)

        self.client.force_login(self.staff)
        replay_url = reverse("events:event_replay")
        host = _tenant_host(self.school_a)
        resp = self.client.post(
            replay_url,
            {
                "source": "domain",
                "domain_event_id": str(ev.pk),
                "process_outbox": "1",
            },
            HTTP_HOST=host,
        )
        self.assertEqual(resp.status_code, 302)
        ev.refresh_from_db()
        self.assertEqual(ev.payload, src_payload)

        dup = DomainEvent.objects.exclude(pk=ev.pk).order_by("-created_at").first()
        self.assertIsNotNone(dup)
        self.assertEqual(dup.event_type, "payment_success")
        self.assertEqual(dup.status, DomainEvent.Status.PROCESSED)
        meta = (dup.payload or {}).get("_replay_meta") or {}
        self.assertEqual(meta.get("source_event_id"), str(ev.pk))
        self.assertEqual(meta.get("actor_id"), self.staff.pk)
        self.assertTrue(seen)
        self.assertIn(str(dup.pk), seen)

    def test_platform_detail_shows_webhook_delivery_row(self):
        sid = str(self.school_a.pk)
        EventWebhookSubscription.objects.create(
            target_url="https://example.invalid/platform-hook",
            event_types=["report_generated"],
            is_active=True,
            school_id=sid,
            secret="sec",
        )
        with patch.object(deliver_event_webhook_task, "delay", MagicMock()):
            row = event_bus.publish_event(
                "report_generated",
                {"school_id": sid},
                school_id=self.school_a.pk,
                strict_catalog=True,
                idempotency_key="closure-report-1",
            )
        self.assertIsNotNone(row)
        self.client.force_login(self.staff)
        detail_url = reverse(
            "events:event_platform_detail", kwargs={"event_pk": row.pk}
        )
        resp = self.client.get(detail_url, HTTP_HOST=_tenant_host(self.school_a))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("https://example.invalid/platform-hook", resp.content.decode())

    def test_platform_replay_via_http_is_webhook_idempotent_for_delivery_rows(self):
        sid = str(self.school_a.pk)
        EventWebhookSubscription.objects.create(
            target_url="https://example.invalid/pay-hook",
            event_types=["payment_success"],
            is_active=True,
            school_id=sid,
            secret="sec",
        )
        with patch.object(deliver_event_webhook_task, "delay", MagicMock()):
            row = event_bus.publish_event(
                "payment_success",
                {"school_id": sid},
                school_id=self.school_a.pk,
                strict_catalog=True,
                idempotency_key="closure-pay-hook-1",
            )
        self.assertIsNotNone(row)
        deliveries_before = EventWebhookDelivery.objects.filter(
            platform_event=row
        ).count()
        self.assertGreaterEqual(deliveries_before, 1)

        replay_url = reverse("events:event_replay")
        host = _tenant_host(self.school_a)
        self.client.force_login(self.staff)
        for _ in range(2):
            resp = self.client.post(
                replay_url,
                {
                    "source": "platform",
                    "platform_event_pk": str(row.pk),
                    "dispatch_webhooks": "1",
                },
                HTTP_HOST=host,
            )
            self.assertEqual(resp.status_code, 302)

        self.assertEqual(
            EventWebhookDelivery.objects.filter(platform_event=row).count(),
            deliveries_before,
        )
        audits = PlatformEventLog.objects.filter(event_type="platform_event_replayed")
        self.assertGreaterEqual(audits.count(), 2)

    def test_event_console_direct_call_requires_school_binding(self):
        factory = RequestFactory()
        req = factory.get(reverse("events:event_console"))
        req.user = self.staff
        resp = event_console(req)
        self.assertEqual(resp.status_code, 403)

"""DLQ ingress, bulk retry, disposition + audit trail."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Permission
from apps.events.models import (
    DomainEvent,
    EventSystemRemediationAudit,
    WebhookDelivery,
    WebhookSubscription,
)
from apps.platform_runtime.models import (
    EventWebhookDelivery,
    EventWebhookSubscription,
    PlatformEventLog,
)
from apps.schools.models import School, SchoolMembership

User = get_user_model()


def _tenant_host(school: School) -> str:
    return f"{school.subdomain}.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["*"], ROOT_URLCONF="config.tenant_urls")
class EventDlqBulkRemediationTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.school_a = School.objects.create(
            name="DLQ A",
            slug="dlq-a",
            subdomain="dlq-a",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="DLQ B",
            slug="dlq-b",
            subdomain="dlq-b",
            is_active=True,
        )
        self.staff = User.objects.create_user(
            username="dlq_staff",
            password="pw",
            is_staff=True,
            role=User.Role.IT_ADMIN,
        )
        # Staff must be a member of school_a: the tenant host confines a logged-in
        # non-member (redirect) before the DLQ console view runs its action.
        SchoolMembership.objects.create(
            user=self.staff, school=self.school_a, role=User.Role.IT_ADMIN, is_primary=True
        )
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.staff.feature_permissions.add(manage_perm)

    def _domain_dlq_delivery(self, school: School):
        sub = WebhookSubscription.objects.create(
            school_id=school.pk,
            url=f"https://{school.slug}.invalid/h",
            event_types=["payment_success"],
            secret="x",
            is_active=True,
        )
        ev = DomainEvent.objects.create(
            event_type="payment_success",
            payload={"school_id": str(school.pk)},
            school_id=school.pk,
            status=DomainEvent.Status.PROCESSED,
            processed_at=timezone.now(),
        )
        return WebhookDelivery.objects.create(
            subscription=sub,
            domain_event=ev,
            status=WebhookDelivery.Status.FAILED,
            retry_count=4,
            max_attempts=4,
            error_message="boom",
        )

    def test_failed_domain_delivery_is_dlq_until_disposition(self):
        d = self._domain_dlq_delivery(self.school_a)
        self.assertTrue(d.is_dead_letter)

    @patch("apps.events.remediation_ops.process_webhook_deliveries_batch", MagicMock())
    def test_bulk_retry_selected_resets_domain_delivery_and_audits(self):
        d = self._domain_dlq_delivery(self.school_a)
        self.client.force_login(self.staff)
        url = reverse("events:event_dlq_console")
        resp = self.client.post(
            url,
            {"action": "retry_selected", "domain_delivery_ids": [str(d.pk)]},
            HTTP_HOST=_tenant_host(self.school_a),
        )
        self.assertEqual(resp.status_code, 302)
        d.refresh_from_db()
        self.assertEqual(d.status, WebhookDelivery.Status.PENDING)
        self.assertEqual(d.retry_count, 0)
        audit = EventSystemRemediationAudit.objects.filter(
            school_id=self.school_a.pk,
            delivery_pk=d.pk,
            action=EventSystemRemediationAudit.Action.RETRY,
        ).first()
        self.assertIsNotNone(audit)

    def test_resolve_selected_writes_audit_and_sets_resolution(self):
        d = self._domain_dlq_delivery(self.school_a)
        self.client.force_login(self.staff)
        url = reverse("events:event_dlq_console")
        resp = self.client.post(
            url,
            {
                "action": "resolve_selected",
                "domain_delivery_ids": [str(d.pk)],
                "reason": "subscriber deprecated",
            },
            HTTP_HOST=_tenant_host(self.school_a),
        )
        self.assertEqual(resp.status_code, 302)
        d.refresh_from_db()
        self.assertEqual(d.operator_resolution, "resolved")
        self.assertIn("deprecated", d.operator_resolution_reason)
        audit = EventSystemRemediationAudit.objects.filter(
            action=EventSystemRemediationAudit.Action.RESOLVED,
            delivery_pk=d.pk,
        ).first()
        self.assertIsNotNone(audit)

    def test_cross_tenant_pk_does_not_remediate_foreign_delivery(self):
        d_b = self._domain_dlq_delivery(self.school_b)
        self.client.force_login(self.staff)
        url = reverse("events:event_dlq_console")
        self.client.post(
            url,
            {
                "action": "retry_selected",
                "domain_delivery_ids": [str(d_b.pk)],
            },
            HTTP_HOST=_tenant_host(self.school_a),
        )
        d_b.refresh_from_db()
        self.assertEqual(d_b.status, WebhookDelivery.Status.FAILED)

    @patch(
        "apps.platform_runtime.tasks.deliver_event_webhook_task.delay",
        MagicMock(),
    )
    def test_platform_dlq_retry_audits_and_resets_pending(self):
        sid = str(self.school_a.pk)
        sub = EventWebhookSubscription.objects.create(
            target_url="https://plat.invalid/w",
            event_types=["payment_success"],
            is_active=True,
            school_id=sid,
            secret="sec",
        )
        row = PlatformEventLog.objects.create(
            event_type="payment_success",
            payload={"school_id": sid},
            school_id=sid,
        )
        d = EventWebhookDelivery.objects.create(
            subscription=sub,
            platform_event=row,
            status=EventWebhookDelivery.Status.DEAD_LETTER,
            attempt_count=5,
            last_error="failed",
        )
        self.client.force_login(self.staff)
        url = reverse("events:event_dlq_console")
        resp = self.client.post(
            url,
            {"action": "retry_selected", "platform_delivery_ids": [str(d.pk)]},
            HTTP_HOST=_tenant_host(self.school_a),
        )
        self.assertEqual(resp.status_code, 302)
        d.refresh_from_db()
        self.assertEqual(d.status, EventWebhookDelivery.Status.PENDING)
        self.assertEqual(d.attempt_count, 0)
        audit = EventSystemRemediationAudit.objects.filter(
            delivery_source=EventSystemRemediationAudit.DeliverySource.PLATFORM_WEBHOOK,
            delivery_pk=d.pk,
            action=EventSystemRemediationAudit.Action.RETRY,
        ).first()
        self.assertIsNotNone(audit)

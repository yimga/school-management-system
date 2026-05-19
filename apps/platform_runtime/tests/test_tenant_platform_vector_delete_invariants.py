"""Append-only integration/audit rows must not be deletable via ORM or admin."""

from __future__ import annotations


from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.compliance.admin_audit import AuditLogAdmin
from apps.compliance.models_audit import AuditLog
from apps.migration_cloud.models import (
    MigrationCloudWebhookDelivery,
    MigrationCloudWebhookSubscription,
    WebhookDeliveryStatus,
)
from apps.schools.models import School
from apps.platform_runtime.append_only import AppendOnlyDeleteError
from apps.platform_runtime.admin import (
    PlatformEventLogAdmin,
    PlatformIntegrationWebhookEventAdmin,
)
from apps.platform_runtime.models import PlatformEventLog, PlatformIntegrationWebhookEvent


class AppendOnlyOrmDeleteTests(TestCase):
    def test_audit_log_delete_raises(self):
        row = AuditLog.objects.create(
            action=AuditLog.Action.CREATE,
            model_name="Test",
            object_id="1",
            object_repr="t",
        )
        with self.assertRaises(AppendOnlyDeleteError):
            row.delete()

    def test_platform_event_log_delete_raises(self):
        row = PlatformEventLog.objects.create(event_type="test.event", payload={})
        with self.assertRaises(AppendOnlyDeleteError):
            row.delete()

    def test_webhook_delivery_delete_raises(self):
        school = School.objects.create(
            name="Del School",
            slug="del-school",
            subdomain="delschool",
            is_active=True,
        )
        sub = MigrationCloudWebhookSubscription.objects.create(
            tenant=school,
            url="https://example.com/hook",
            secret_ciphertext=b"x",
        )
        row = MigrationCloudWebhookDelivery.objects.create(
            subscription=sub,
            event_type="migration.test",
            payload_json={},
            status=WebhookDeliveryStatus.PENDING,
        )
        with self.assertRaises(AppendOnlyDeleteError):
            row.delete()

    def test_integration_webhook_event_delete_raises(self):
        row = PlatformIntegrationWebhookEvent.objects.create(
            event_type="stripe.test",
            body_sha256="abc",
            verified=True,
        )
        with self.assertRaises(AppendOnlyDeleteError):
            row.delete()

    def test_audit_log_bulk_delete_raises(self):
        AuditLog.objects.create(
            action=AuditLog.Action.CREATE,
            model_name="Bulk",
            object_id="1",
            object_repr="b",
        )
        with self.assertRaises(AppendOnlyDeleteError):
            AuditLog.objects.filter(model_name="Bulk").delete()

    def test_webhook_delivery_bulk_delete_raises(self):
        school = School.objects.create(
            name="Bulk Del School",
            slug="bulk-del-school",
            subdomain="bulkdelschool",
            is_active=True,
        )
        sub = MigrationCloudWebhookSubscription.objects.create(
            tenant=school,
            url="https://example.com/hook-bulk",
            secret_ciphertext=b"x",
        )
        MigrationCloudWebhookDelivery.objects.create(
            subscription=sub,
            event_type="migration.test",
            payload_json={},
            status=WebhookDeliveryStatus.PENDING,
        )
        with self.assertRaises(AppendOnlyDeleteError):
            MigrationCloudWebhookDelivery.objects.filter(
                subscription=sub
            ).delete()


class AppendOnlyAdminDeletePermissionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="staff_del",
            password="Test1234",
            is_staff=True,
        )
        self.rf = RequestFactory()

    def test_audit_log_admin_cannot_delete(self):
        admin = AuditLogAdmin(AuditLog, None)
        self.assertFalse(admin.has_delete_permission(self.rf.get("/"), None))

    def test_platform_event_log_admin_cannot_delete(self):
        admin = PlatformEventLogAdmin(PlatformEventLog, None)
        self.assertFalse(admin.has_delete_permission(self.rf.get("/"), None))

    def test_integration_webhook_event_admin_cannot_delete(self):
        admin = PlatformIntegrationWebhookEventAdmin(
            PlatformIntegrationWebhookEvent, None
        )
        self.assertFalse(admin.has_delete_permission(self.rf.get("/"), None))

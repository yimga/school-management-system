"""Operator per-tenant subscription manager: actions, audit, RBAC."""

import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import TenantSubscription
from apps.compliance.models_audit import AuditLog
from apps.schools.models import School
from apps.schools.tests.manager_client import login_manager_control_plane
from apps.siteconfig.models import Plan

_HOST = "manager.runmycampus.com"
_PASSWORD = "testpass123"


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", _HOST],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SECURE_SSL_REDIRECT=False,
    ROOT_URLCONF="config.manager_urls",
    SESSION_PINNING_ENABLED=False,
    OPERATOR_MFA_REQUIRED_ON_MANAGER=False,
)
class OperatorSubscriptionManageTests(TestCase):
    def setUp(self):
        self.free = Plan.objects.create(
            name="Free", slug="free", base_price=Decimal("0.00"), is_active=True, is_default=True
        )
        self.pro = Plan.objects.create(
            name="Pro", slug="pro", base_price=Decimal("99.00"), is_active=True
        )
        self.school = School.objects.create(
            name="Op Sub School", slug="op-sub", subdomain="op-sub", is_active=True
        )
        self.op = User.objects.create_user(
            username=f"op_sub_{uuid.uuid4().hex[:8]}",
            email="op@test.local",
            password=_PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client(HTTP_HOST=_HOST)
        login_manager_control_plane(self.client, self.op, password=_PASSWORD, host=_HOST)
        self.url = reverse(
            "super:tenant_subscription_manage", kwargs={"school_id": str(self.school.pk)}
        )

    def test_get_renders(self):
        resp = self.client.get(self.url, HTTP_HOST=_HOST)
        self.assertEqual(resp.status_code, 200, msg=resp.get("Location", ""))

    def test_change_plan(self):
        self.client.post(
            self.url, {"action": "change_plan", "plan_id": str(self.pro.pk)}, HTTP_HOST=_HOST
        )
        self.school.refresh_from_db()
        self.assertEqual(self.school.plan, self.pro)
        # NB: evaluate the changed_fields membership in Python — SQLite's JSONField
        # has no __contains lookup (Postgres-only), so the prod-path assertion would
        # raise NotSupportedError under the local SQLite test runner.
        logs = AuditLog.objects.filter(object_id=str(self.school.pk))
        self.assertTrue(any("plan" in (log.changed_fields or []) for log in logs))

    def test_set_status_suspended(self):
        self.client.post(
            self.url, {"action": "set_status", "status": "SUSPENDED"}, HTTP_HOST=_HOST
        )
        sub = TenantSubscription.objects.filter(school=self.school).order_by("-updated_at").first()
        self.assertIsNotNone(sub)
        self.assertEqual(sub.status, TenantSubscription.Status.SUSPENDED)

    def test_extend_trial_by_days(self):
        self.client.post(
            self.url, {"action": "extend_trial", "extend_days": "30"}, HTTP_HOST=_HOST
        )
        self.school.refresh_from_db()
        self.assertIsNotNone(self.school.trial_end_date)
        self.assertGreaterEqual(
            self.school.trial_end_date, (timezone.now() + timedelta(days=29)).date()
        )

    def test_invalid_status_rejected(self):
        # Establish the subscription first (GET materializes it).
        self.client.get(self.url, HTTP_HOST=_HOST)
        sub = TenantSubscription.objects.filter(school=self.school).order_by("-updated_at").first()
        before = sub.status
        self.client.post(
            self.url, {"action": "set_status", "status": "BOGUS"}, HTTP_HOST=_HOST
        )
        sub.refresh_from_db()
        self.assertEqual(sub.status, before)

    def test_requires_operator_access(self):
        # A plain authenticated non-operator must not reach the manager surface.
        tenant_user = User.objects.create_user(
            username=f"plain_{uuid.uuid4().hex[:8]}", email="plain@test.local", password=_PASSWORD
        )
        c = Client(HTTP_HOST=_HOST)
        c.force_login(tenant_user)
        resp = c.get(self.url, HTTP_HOST=_HOST)
        self.assertNotEqual(resp.status_code, 200)

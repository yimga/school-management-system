from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.billing.models import BillingAccount, TenantSubscription
from apps.billing.services import ensure_subscription_for_school
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig

User = get_user_model()


class ControlPlaneLifecycleTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="cp_super",
            email="cp-super@example.com",
            password="testpass123",
        )
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            name="Lifecycle Test School",
            slug="lifecycle-test-school",
            subdomain="lifecycle-test-school",
            is_active=True,
            is_approved=False,
            default_region=self.region,
        )
        self.client.force_login(self.superuser)

    def test_lifecycle_api_can_deactivate_and_activate_school(self):
        url = reverse("super:api_school_lifecycle", args=[self.school.id])

        response = self.client.post(
            url,
            {
                "action": "deactivate",
                "next": reverse("super:tenant_360", args=[self.school.id]),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.school.refresh_from_db()
        self.assertFalse(self.school.is_active)

        response = self.client.post(
            url,
            {
                "action": "activate",
                "next": reverse("super:tenant_360", args=[self.school.id]),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.school.refresh_from_db()
        self.assertTrue(self.school.is_active)

    def test_lifecycle_api_blocks_billing_unfreeze_without_subscription_recovery(self):
        account, subscription, _ = ensure_subscription_for_school(self.school)
        self.school.is_frozen = True
        self.school.frozen_reason = "BILLING"
        self.school.save(update_fields=["is_frozen", "frozen_reason", "updated_at"])
        subscription.status = TenantSubscription.Status.SUSPENDED
        subscription.save(update_fields=["status", "updated_at"])
        account.status = BillingAccount.Status.SUSPENDED
        account.save(update_fields=["status", "updated_at"])

        url = reverse("super:api_school_lifecycle", args=[self.school.id])
        response = self.client.post(
            url,
            data='{"action":"unfreeze"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.school.refresh_from_db()
        self.assertTrue(self.school.is_frozen)

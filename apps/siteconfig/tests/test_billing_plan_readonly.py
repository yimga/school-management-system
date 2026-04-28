"""GTM: read-only tenant plan & entitlements page (no billing capture)."""

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission, User
from apps.people.models import StudentProfile, TeacherProfile
from apps.billing.models import PlatformBillingProcessorConfig, StripePlanPrice
from apps.siteconfig.models import Plan
from apps.schools.models import School

_T_HOST = "billingplan.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class BillingPlanReadonlyTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="Growth Demo",
            slug="growth-demo",
            included_features=["reports", "library"],
            max_students=500,
            max_staff=50,
            is_active=True,
        )
        cls.school = School.objects.create(
            name="Billing Plan School",
            slug="billingplan",
            subdomain="billingplan",
            is_active=True,
            plan=cls.plan,
        )
        cls.perm_settings, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def test_settings_manage_gets_200_with_plan_and_counts(self) -> None:
        code = f"S-{uuid.uuid4().hex[:8]}"
        StudentProfile.objects.create(
            school=self.school,
            first_name="A",
            last_name="Student",
            student_code=code,
            is_active=True,
        )
        tu = User.objects.create_user(
            username=f"t_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        TeacherProfile.objects.create(user=tu, school=self.school, staff_id="T1")
        u = User.objects.create_user(
            username="bp_op",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username="bp_op", password="x" * 8)
        path = reverse("siteconfig:billing_plan_readonly", urlconf="config.tenant_urls")
        self.assertIn("/siteconfig/billing/plan/", path)
        resp = c.get(path)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:500])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-shell-surface="billing-plan-readonly"', body)
        self.assertIn("Growth Demo", body)
        self.assertIn("reports", body)
        self.assertIn("500", body)
        self.assertIn("Commercial tier", body)
        self.assertIn("Resolved tier", body)

    def test_related_before_admin_for_superuser(self) -> None:
        u = User.objects.create_user(
            username="bp_su",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        u.feature_permissions.add(self.perm_settings)
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username="bp_su", password="x" * 8)
        path = reverse("siteconfig:billing_plan_readonly", urlconf="config.tenant_urls")
        body = c.get(path).content.decode("utf-8", errors="replace")
        p = body.find("Configuration Control Center")
        a = body.find("Advanced/Admin: plan catalog")
        self.assertNotEqual(p, -1)
        self.assertNotEqual(a, -1)
        self.assertLess(p, a)

    def test_checkout_button_visible_when_stripe_and_price_configured(self) -> None:
        PlatformBillingProcessorConfig.objects.create(
            code="stripe",
            display_name="Stripe",
            is_active=True,
            metadata={"secret_key": "sk_test_placeholder"},
        )
        StripePlanPrice.objects.create(
            plan_code=self.plan.slug,
            stripe_price_id="price_x",
            billing_cycle=StripePlanPrice.BillingCycle.MONTHLY,
            currency="USD",
            is_active=True,
        )
        u = User.objects.create_user(
            username="bp_checkout",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username="bp_checkout", password="x" * 8)
        path = reverse("siteconfig:billing_plan_readonly", urlconf="config.tenant_urls")
        body = c.get(path).content.decode("utf-8", errors="replace")
        self.assertIn("billing/checkout/start", body)
        self.assertIn("Checkout / renew", body)
        self.assertRegex(body, r"<a[^>]+btn-primary[^>]+href=[^>]+checkout/start")

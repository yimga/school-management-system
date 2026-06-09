"""GTM: read-only tenant plan & entitlements page (no billing capture)."""

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission, User
from apps.people.models import StudentProfile, TeacherProfile
from apps.billing.models import PlatformBillingProcessorConfig, StripePlanPrice
from apps.siteconfig.models import Plan
from apps.schools.models import School, SchoolMembership
from django_otp.plugins.otp_totp.models import TOTPDevice

_T_HOST = "billingplan.runmycampus.com"
_M_HOST = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST, _M_HOST],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
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

    def _login_past_mfa(self, client, user):
        TOTPDevice.objects.update_or_create(
            user=user, name="test-totp", defaults={"confirmed": True}
        )
        client.force_login(user)
        session = client.session
        session["mfa_verified"] = True
        session.save()

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
        SchoolMembership.objects.get_or_create(
            user=u, school=self.school, defaults={"role": User.Role.ADMIN, "is_primary": True}
        )
        c = Client(HTTP_HOST=_T_HOST)
        self._login_past_mfa(c, u)
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
        SchoolMembership.objects.get_or_create(
            user=u, school=self.school, defaults={"role": User.Role.ADMIN, "is_primary": True}
        )
        c = Client(HTTP_HOST=_T_HOST)
        self._login_past_mfa(c, u)
        path = reverse("siteconfig:billing_plan_readonly", urlconf="config.tenant_urls")
        resp = c.get(path, follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("manager", resp["Location"])
        resp = c.get(path, follow=True)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:500])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertTrue(
            "Plan & entitlements" in body or "Plan &amp; entitlements" in body,
            msg="expected plan page title in manager shell",
        )
        self.assertIn("Advanced/Admin: plan catalog", body)
        if "Configuration Control Center" in body:
            p = body.find("Configuration Control Center")
            a = body.find("Advanced/Admin: plan catalog")
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
        SchoolMembership.objects.get_or_create(
            user=u, school=self.school, defaults={"role": User.Role.ADMIN, "is_primary": True}
        )
        c = Client(HTTP_HOST=_T_HOST)
        self._login_past_mfa(c, u)
        path = reverse("siteconfig:billing_plan_readonly", urlconf="config.tenant_urls")
        body = c.get(path).content.decode("utf-8", errors="replace")
        self.assertIn("billing/checkout/start", body)
        self.assertIn("Checkout / renew", body)
        self.assertRegex(body, r"<a[^>]+btn-primary[^>]+href=[^>]+checkout/start")

"""1078: Term publish status — read-only CP evidence; superuser admin fallback only."""

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission, User
from apps.siteconfig.models import Plan
from apps.schools.models import School
from apps.test_utils.http_clients import login_tenant_admin_client

_T_HOST = "tpub.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class TermPublishStatusEvidenceTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="TpPlan",
            slug="tp-plan",
            included_features=["reports"],
            is_active=True,
        )
        cls.school = School.objects.create(
            name="Term Pub School",
            slug="tpub",
            subdomain="tpub",
            is_active=True,
            plan=cls.plan,
        )
        cls.perm_settings, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def test_settings_manage_gets_200_with_markers(self) -> None:
        u = User.objects.create_user(
            username="tpub_u",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)
        c = login_tenant_admin_client(
            u, password="x" * 8, host=_T_HOST, school=self.school
        )
        path = reverse(
            "siteconfig:term_publish_status_evidence", urlconf="config.tenant_urls"
        )
        self.assertIn("/siteconfig/reports/term-publish-status/", path)
        resp = c.get(path)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:500])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-shell-surface="term-publish-status-evidence"', body)
        self.assertIn("cp-evidence-page", body)
        self.assertIn('data-cp-evidence-surface="term-publish"', body)
        self.assertIn('data-rmc-operator-evidence-surface="1"', body)
        self.assertIn('data-rmc-operator-evidence-summary="1"', body)
        self.assertIn('data-admin-replacement-category="publish_staging_evidence"', body)
        self.assertIn("Term publish status", body)

    def test_superuser_sees_scheduled_hub_before_admin_fallback(self) -> None:
        u = User.objects.create_user(
            username="tpub_su",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        c = login_tenant_admin_client(
            u, password="x" * 8, host=_T_HOST, school=self.school
        )
        path = reverse(
            "siteconfig:term_publish_status_evidence", urlconf="config.tenant_urls"
        )
        body = c.get(path).content.decode("utf-8", errors="replace")
        pri = body.find("Scheduled report delivery")
        adv = body.find("Advanced: Admin term publish")
        self.assertNotEqual(pri, -1)
        self.assertNotEqual(adv, -1)
        self.assertLess(pri, adv)

    def test_non_superuser_hides_django_admin_row_link(self) -> None:
        u = User.objects.create_user(
            username="tpub_ns",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=False,
        )
        u.feature_permissions.add(self.perm_settings)
        c = login_tenant_admin_client(
            u, password="x" * 8, host=_T_HOST, school=self.school
        )
        path = reverse(
            "siteconfig:term_publish_status_evidence", urlconf="config.tenant_urls"
        )
        resp = c.get(path)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:300])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertNotIn("Advanced: Admin term publish", body)

    def test_anonymous_redirects(self) -> None:
        c = Client(HTTP_HOST=_T_HOST)
        path = reverse(
            "siteconfig:term_publish_status_evidence", urlconf="config.tenant_urls"
        )
        resp = c.get(path)
        self.assertIn(resp.status_code, (302, 403))

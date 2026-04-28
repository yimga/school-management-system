"""
Certification: ?install_app=<app_pk> deep link opens impact preview intent only for installable listings.
"""

from __future__ import annotations

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.marketplace.models import (
    MarketplaceApp,
    MarketplaceListing,
    PublisherOrganization,
)
from apps.people.models import TeacherProfile
from apps.schools.models import School, SchoolMembership

_T_HOST = "deeplink-mkt.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class TenantCatalogInstallAppDeepLinkTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Deep Link School",
            slug="deeplink-mkt",
            subdomain="deeplink-mkt",
            is_active=True,
        )
        cls.publisher = PublisherOrganization.objects.create(
            slug="dl-pub",
            name="DL Pub",
            verification_status=PublisherOrganization.VerificationStatus.VERIFIED,
        )

    def _admin_client(self):
        u = User.objects.create_user(
            username=f"dl_admin_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
        )
        TeacherProfile.objects.create(user=u, school=self.school, staff_id="DL1")
        SchoolMembership.objects.get_or_create(
            user=u,
            school=self.school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username=u.username, password="x" * 8)
        return c

    def test_install_app_sets_context_only_for_installable_app(self):
        good_app = MarketplaceApp.objects.create(
            slug="dl-good",
            name="Good App",
            version="1.0.0",
            manifest={"pricing_type": "free"},
            publisher=self.publisher,
        )
        bad_app = MarketplaceApp.objects.create(
            slug="dl-bad",
            name="Kill switched",
            version="1.0.0",
            manifest={"pricing_type": "free"},
            publisher=self.publisher,
        )
        MarketplaceListing.objects.create(
            app=good_app,
            publisher=self.publisher,
            status=MarketplaceListing.Status.APPROVED,
            short_description="ok",
            kill_switch_active=False,
        )
        MarketplaceListing.objects.create(
            app=bad_app,
            publisher=self.publisher,
            status=MarketplaceListing.Status.APPROVED,
            short_description="ks",
            kill_switch_active=True,
        )
        c = self._admin_client()
        base = reverse("tenant_app_catalog", urlconf="config.tenant_urls")
        r_ok = c.get(f"{base}?install_app={good_app.pk}")
        self.assertEqual(r_ok.status_code, 200)
        self.assertEqual(r_ok.context["catalog_install_app_id"], good_app.pk)
        self.assertContains(
            r_ok,
            f'data-app-id="{good_app.pk}"',
            html=False,
        )
        r_ks = c.get(f"{base}?install_app={bad_app.pk}")
        self.assertEqual(r_ks.status_code, 200)
        self.assertIsNone(r_ks.context["catalog_install_app_id"])
        r_bad = c.get(f"{base}?install_app=999999999")
        self.assertIsNone(r_bad.context["catalog_install_app_id"])

    def test_teacher_receives_403_on_catalog_with_install_app(self):
        good_app = MarketplaceApp.objects.create(
            slug="dl-teacher",
            name="Teachervis",
            version="1.0.0",
            manifest={"pricing_type": "free"},
            publisher=self.publisher,
        )
        MarketplaceListing.objects.create(
            app=good_app,
            publisher=self.publisher,
            status=MarketplaceListing.Status.APPROVED,
            short_description="ok",
        )
        t = User.objects.create_user(
            username=f"dl_teach_{uuid.uuid4().hex[:6]}",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        TeacherProfile.objects.create(user=t, school=self.school, staff_id="T99")
        SchoolMembership.objects.get_or_create(
            user=t,
            school=self.school,
            defaults={"role": User.Role.TEACHER, "is_primary": True},
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username=t.username, password="x" * 8)
        base = reverse("tenant_app_catalog", urlconf="config.tenant_urls")
        r = c.get(f"{base}?install_app={good_app.pk}")
        # May redirect to login / MFA / safe surface before 403 depending on stack.
        self.assertIn(
            r.status_code,
            (302, 403),
            msg=f"teacher must not get 200 for catalog; got {r.status_code} {r.get('Location', '')}",
        )
        self.assertNotEqual(r.status_code, 200)

    def test_install_app_non_digit_ignored(self):
        good_app = MarketplaceApp.objects.create(
            slug="dl-good2",
            name="Good2",
            version="1.0.0",
            manifest={"pricing_type": "free"},
            publisher=self.publisher,
        )
        MarketplaceListing.objects.create(
            app=good_app,
            publisher=self.publisher,
            status=MarketplaceListing.Status.APPROVED,
            short_description="ok",
        )
        c = self._admin_client()
        base = reverse("tenant_app_catalog", urlconf="config.tenant_urls")
        r = c.get(f"{base}?install_app=abc")
        self.assertIsNone(r.context["catalog_install_app_id"])

    def test_catalog_deep_link_modal_script_is_optional_when_no_auto_open(self):
        """When catalog_install_app_id is absent, auto-open script block is omitted (safe without JS)."""
        c = self._admin_client()
        base = reverse("tenant_app_catalog", urlconf="config.tenant_urls")
        r = c.get(base)
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        self.assertNotIn(
            "if (btn && !btn.disabled)",
            body,
            msg="auto-open install-impact snippet should not render without install_app",
        )

"""N17: install impact preview JSON before sandbox install."""

import os
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.marketplace.install_impact import build_tenant_install_impact
from apps.marketplace.models import (
    AppScope,
    MarketplaceApp,
    MarketplaceListing,
    PublisherOrganization,
)
from apps.schools.models import School


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class TenantInstallImpactPreviewTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Impact School",
            slug="impact-school",
            subdomain="impact-school",
            is_active=True,
        )
        pub, _ = PublisherOrganization.objects.get_or_create(
            slug="pub-impact",
            defaults={
                "name": "Pub",
                "verification_status": PublisherOrganization.VerificationStatus.VERIFIED,
            },
        )
        self.app = MarketplaceApp.objects.create(
            publisher=pub,
            slug="impact-test-app",
            name="Impact Test App",
            version="1.0",
            kind=MarketplaceApp.AppKind.FIRST_PARTY,
        )
        AppScope.objects.create(
            app=self.app,
            scope_code="students.read",
            description="Read students",
            sensitive=False,
        )
        MarketplaceListing.objects.create(
            app=self.app,
            publisher=pub,
            status=MarketplaceListing.Status.APPROVED,
            short_description="Test",
        )
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.superuser = User.objects.create_superuser(
            "su_impact", "su_impact@x.edu", "pw"
        )
        self.user = User.objects.create_user(
            username="adm",
            email="a@x.edu",
            password="x",
            role=User.Role.ADMIN,
        )

    def test_build_tenant_install_impact_includes_scopes(self):
        data = build_tenant_install_impact(self.school, self.app)
        self.assertEqual(data["app"]["slug"], "impact-test-app")
        self.assertTrue(any(s["scope_code"] == "students.read" for s in data["scopes"]))

    def test_super_preview_requires_both_ids(self):
        c = Client()
        c.force_login(self.superuser)
        r = c.get(
            reverse("super:marketplace_install_impact_preview")
            + f"?app_id={self.app.pk}"
        )
        self.assertEqual(r.status_code, 400)
        r2 = c.get(
            reverse("super:marketplace_install_impact_preview")
            + f"?app_id={self.app.pk}&school_id={self.school.pk}",
        )
        self.assertEqual(r2.status_code, 200)
        data = r2.json()
        self.assertEqual(data["app"]["slug"], "impact-test-app")
        self.assertTrue(any(s["scope_code"] == "students.read" for s in data["scopes"]))

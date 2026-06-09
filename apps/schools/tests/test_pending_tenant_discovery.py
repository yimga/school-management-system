"""Pending (inactive) tenant discovery — school-not-found + find campus."""

from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership, SignupVerification


@override_settings(
    ALLOWED_HOSTS=["*", "runmycampus.com", "testserver"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    RMC_PUBLIC_SITE_URL="https://runmycampus.com",
    SECURE_SSL_REDIRECT=False,
)
class PendingTenantDiscoveryTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="NewssBell School of Arts",
            slug="newssbell-school-of-arts",
            subdomain="newssbell-school-of-arts",
            is_active=False,
        )
        self.owner = User.objects.create_user(
            username="owner@newssbell.test",
            email="owner@newssbell.test",
            password="unused",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.owner,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        SignupVerification.objects.create(
            school=self.school,
            email=self.owner.email,
            expires_at=timezone.now() + timezone.timedelta(days=2),
            verified_at=timezone.now(),
        )

    def test_school_not_found_shows_pending_setup_for_inactive_slug(self):
        client = Client(HTTP_HOST="runmycampus.com")
        response = client.get(
            "/school-not-found/?slug=newssbell-school-of-arts", follow=False
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Campus setup in progress")
        self.assertContains(response, "NewssBell School of Arts")
        self.assertContains(response, "Continue setup")

    def test_find_campus_lists_inactive_school_by_exact_slug(self):
        client = Client(HTTP_HOST="runmycampus.com")
        response = client.get(
            "/find/?q=newssbell-school-of-arts", follow=False
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "NewssBell School of Arts")
        self.assertContains(response, "Continue setup")

    def test_email_discovery_finds_inactive_membership(self):
        client = Client(HTTP_HOST="runmycampus.com")
        response = client.post(
            "/discover/",
            {"email": "owner@newssbell.test"},
            follow=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Campus setup in progress")

    def test_pending_recovery_links_use_tenant_workspace_login(self):
        from apps.schools.pending_tenant_discovery import build_pending_recovery_links

        links = build_pending_recovery_links(self.school)
        self.assertIn(
            "newssbell-school-of-arts.runmycampus.com/authentication/login",
            links["login_url"],
        )

    def test_inactive_subdomain_login_is_reachable(self):
        client = Client(HTTP_HOST="newssbell-school-of-arts.runmycampus.com")
        response = client.get("/authentication/login/", follow=False)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.status_code, 302)

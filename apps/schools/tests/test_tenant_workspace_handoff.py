"""Public-host sign-in must hand off to the tenant slug URL."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School, SchoolMembership

User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["*", "runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    RMC_PUBLIC_SITE_URL="https://runmycampus.com",
    SECURE_SSL_REDIRECT=False,
    RATELIMIT_ENABLE=False,
)
class TenantWorkspaceHandoffTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="handoff@test",
            email="handoff@test",
            password="Zaq12wsx!RmC9",
            role=User.Role.ADMIN,
        )
        self.school = School.objects.create(
            name="Handoff School",
            slug="handoff-school",
            subdomain="handoff-school",
            is_active=False,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        self.client = Client(HTTP_HOST="runmycampus.com")

    def test_redirect_view_sends_pending_owner_to_tenant_workspace(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:redirect"), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("handoff-school.runmycampus.com", response["Location"])
        self.assertIn("/authentication/login/", response["Location"])

    def _satisfy_mfa_gate(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.create(user=self.user, name="test-totp", confirmed=True)
        session = self.client.session
        session["mfa_verified"] = True
        session.save()

    def test_apex_login_redirects_to_discovery_not_tenant_form(self):
        response = self.client.get(reverse("accounts:login"), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/discover/", response["Location"])

    def test_tenant_subdomain_still_serves_login_form(self):
        client = Client(HTTP_HOST="handoff-school.runmycampus.com")
        response = client.get(reverse("accounts:login"), follow=False)
        # Unlike the apex (which redirects to /discover/), the tenant subdomain
        # still serves the credential login form. The heading was reworded from
        # "Secure sign in" to "Sign in"; assert on that stable login marker.
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in", status_code=200)

    def test_school_picker_posts_to_tenant_workspace(self):
        other = School.objects.create(
            name="Other School",
            slug="other-school",
            subdomain="other-school",
            is_active=True,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=other,
            role=User.Role.ADMIN,
            is_primary=False,
        )
        self.client.force_login(self.user)
        self._satisfy_mfa_gate()
        response = self.client.post(
            reverse("accounts:school_picker"),
            {"school_id": str(self.school.pk)},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("handoff-school.runmycampus.com", response["Location"])

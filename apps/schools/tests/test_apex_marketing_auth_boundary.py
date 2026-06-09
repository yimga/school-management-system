"""Marketing apex must never accept tenant credential authentication."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School, SchoolMembership
from apps.schools.provision_email_urls import build_public_login_url

User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["*", "runmycampus.com", "st-jude.runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    RMC_PUBLIC_SITE_URL="https://runmycampus.com",
    SECURE_SSL_REDIRECT=False,
    RATELIMIT_ENABLE=False,
    LOGIN_POW_ENABLED=False,
    LOGIN_MIN_FORM_SECONDS=0,
)
class ApexMarketingAuthBoundaryTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner@stjude.test",
            email="owner@stjude.test",
            password="OwnerPass123!",
            role=User.Role.ADMIN,
        )
        self.school = School.objects.create(
            name="St Jude",
            slug="st-jude",
            subdomain="st-jude",
            is_active=True,
        )
        SchoolMembership.objects.create(
            user=self.owner,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        self.apex = Client(HTTP_HOST="runmycampus.com")
        self.tenant = Client(HTTP_HOST="st-jude.runmycampus.com")

    def test_apex_login_get_redirects_to_discovery(self):
        response = self.apex.get("/authentication/login/", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/discover/", response["Location"])

    def test_apex_login_post_does_not_authenticate(self):
        response = self.apex.post(
            reverse("accounts:login"),
            {"username": "owner@stjude.test", "password": "OwnerPass123!"},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/discover/", response["Location"])
        session_key = self.apex.session.session_key
        self.assertFalse(
            "_auth_user_id" in self.apex.session,
            msg="apex login POST must not create an authenticated session",
        )
        del session_key

    def test_apex_password_reset_redirects_to_discovery(self):
        response = self.apex.get("/authentication/password_reset/", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/discover/", response["Location"])

    def test_apex_school_picker_redirects_without_session(self):
        response = self.apex.get(reverse("accounts:school_picker"), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/discover/", response["Location"])

    def test_apex_school_picker_hands_off_authenticated_user_to_tenant(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.create(user=self.owner, name="test-totp", confirmed=True)
        self.apex.force_login(self.owner)
        session = self.apex.session
        session["mfa_verified"] = True
        session.save()
        response = self.apex.get(reverse("accounts:school_picker"), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("st-jude.runmycampus.com", response["Location"])

    def test_tenant_subdomain_accepts_credential_login(self):
        response = self.tenant.post(
            reverse("accounts:login"),
            {"username": "owner@stjude.test", "password": "OwnerPass123!"},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/discover/", response.get("Location", ""))

    def test_public_login_url_is_discovery_not_credential_form(self):
        url = build_public_login_url()
        self.assertIn("/discover/", url)
        self.assertNotIn("/authentication/login", url)

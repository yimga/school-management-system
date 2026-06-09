"""Manager-host login ``next`` sanitization and tenant-staff escape hatch."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.manager_login_next import (
    build_public_post_login_url,
    is_toxic_login_next_for_manager,
    sanitize_manager_login_next,
    tenant_staff_should_use_public_host,
)
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class ManagerLoginNextSanitizerTests(TestCase):
    def test_detects_nested_mfa_activation_chain(self):
        raw = "/authentication/mfa/setup/?next=/activation/first-action/"
        self.assertTrue(is_toxic_login_next_for_manager(raw))

    def test_detects_url_encoded_nested_chain(self):
        raw = "/authentication/mfa/setup/%3Fnext%3D/activation/first-action/"
        self.assertTrue(is_toxic_login_next_for_manager(raw))

    def test_onboarding_path_is_toxic(self):
        self.assertTrue(
            is_toxic_login_next_for_manager(
                "/authentication/onboarding/account/abc/def/"
            )
        )

    def test_super_dashboard_next_is_allowed(self):
        self.assertFalse(is_toxic_login_next_for_manager("/super/"))

    def test_sanitize_strips_toxic(self):
        self.assertEqual(
            sanitize_manager_login_next(
                "/authentication/mfa/setup/?next=/activation/first-action/"
            ),
            "",
        )

    def test_build_public_post_login_url(self):
        with override_settings(RMC_PUBLIC_SITE_URL="https://runmycampus.com"):
            self.assertEqual(
                build_public_post_login_url(),
                "https://runmycampus.com/authentication/redirect/",
            )


@override_settings(
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ROOT_URLCONF="config.manager_urls",
    RMC_PUBLIC_SITE_URL="https://runmycampus.com",
)
class ManagerLoginViewNextTests(TestCase):
    def test_get_strips_toxic_next_with_redirect(self):
        client = Client(HTTP_HOST="manager.runmycampus.com")
        toxic = (
            "/authentication/login/"
            "?next=/authentication/mfa/setup/%3Fnext%3D/activation/first-action/"
        )
        resp = client.get(toxic)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("accounts:login"))

    def test_tenant_admin_login_escapes_to_public_host(self):
        school = School.objects.create(
            name="Toxic Next Academy",
            slug="toxic-next-academy",
            subdomain="toxic-next-academy",
            is_active=False,
        )
        user = User.objects.create_user(
            username="owner-toxic",
            email="owner-toxic@example.com",
            password="Test1234!",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(user=user, school=school, is_primary=True)
        self.assertTrue(tenant_staff_should_use_public_host(user))
        client = Client(HTTP_HOST="manager.runmycampus.com")
        resp = client.post(
            reverse("accounts:login")
            + "?next=/authentication/mfa/setup/%3Fnext%3D/activation/first-action/",
            {"username": "owner-toxic", "password": "Test1234!"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            resp.url.endswith("/authentication/redirect/"),
            msg=f"unexpected redirect target: {resp.url!r}",
        )
        if resp.url.startswith("http"):
            self.assertTrue(resp.url.startswith("https://runmycampus.com"))

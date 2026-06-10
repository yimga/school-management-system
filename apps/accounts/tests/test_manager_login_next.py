"""Manager-host login ``next`` sanitization and tenant-staff escape hatch."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.manager_login_next import (
    build_public_post_login_url,
    is_toxic_login_next_for_manager,
    manager_login_next_is_operator_intent,
    sanitize_manager_login_next,
    should_show_manager_login_surface,
    tenant_staff_should_use_public_host,
)
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class ManagerHomeFrontDoorTests(TestCase):
    """The manager host root is the operator front door; it must not eject operators
    to the public campus-discovery page (regression: typing manager.runmycampus.com
    redirected to runmycampus.com/discover/)."""

    def test_manager_home_unauthenticated_carries_cp_marker(self):
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from config.manager_urls import manager_home

        req = RequestFactory().get("/")
        req.user = AnonymousUser()
        resp = manager_home(req)
        self.assertEqual(resp.status_code, 302)
        # Must point at the operator login WITH the cp=1 control-plane marker.
        self.assertEqual(resp.url, f"{reverse('accounts:login')}?cp=1")

    def test_cp_marker_shows_operator_surface_not_discovery_eject(self):
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        req = RequestFactory().get(f"{reverse('accounts:login')}?cp=1")
        req.user = AnonymousUser()
        req.public_host_kind = "manager"
        self.assertTrue(should_show_manager_login_surface(req))


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

    def test_tenant_path_prefix_is_toxic(self):
        self.assertTrue(is_toxic_login_next_for_manager("/t/st-jude/authentication/login/"))

    def test_operator_intent_detects_super_paths(self):
        self.assertTrue(manager_login_next_is_operator_intent("/super/schools/"))
        self.assertFalse(manager_login_next_is_operator_intent("/authentication/login/"))

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
        self.assertTrue(resp.url.startswith("https://runmycampus.com/discover/"))

    def test_unauthenticated_manager_login_redirects_to_public_host(self):
        client = Client(HTTP_HOST="manager.runmycampus.com")
        resp = client.get(reverse("accounts:login"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "https://runmycampus.com/discover/")

    def test_operator_super_next_keeps_manager_login_surface(self):
        client = Client(HTTP_HOST="manager.runmycampus.com")
        resp = client.get(reverse("accounts:login") + "?next=/super/schools/")
        self.assertEqual(resp.status_code, 200)

    def test_cp_query_keeps_manager_login_surface(self):
        client = Client(HTTP_HOST="manager.runmycampus.com")
        resp = client.get(reverse("accounts:login") + "?cp=1")
        self.assertEqual(resp.status_code, 200)

    def test_tenant_admin_login_escapes_to_tenant_host(self):
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
            resp.url.startswith("https://toxic-next-academy.runmycampus.com/"),
            msg=f"unexpected redirect target: {resp.url!r}",
        )

    def test_active_tenant_staff_login_on_manager_goes_to_tenant_backend(self):
        school = School.objects.create(
            name="Campus Live Academy",
            slug="campus-live",
            subdomain="campus-live",
            is_active=True,
        )
        user = User.objects.create_user(
            username="teacher-live",
            email="teacher-live@example.com",
            password="Test1234!",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(user=user, school=school, is_primary=True)
        client = Client(HTTP_HOST="manager.runmycampus.com")
        resp = client.post(
            reverse("accounts:login"),
            {"username": "teacher-live", "password": "Test1234!"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            resp.url.startswith("https://campus-live.runmycampus.com/"),
            msg=f"unexpected redirect target: {resp.url!r}",
        )

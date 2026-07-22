"""Password login must land on MFA before handoff / backend."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.post_login_mfa import resolve_post_login_mfa_redirect
from apps.schools.models import School, SchoolMembership

User = get_user_model()


@override_settings(
    LOGIN_POW_ENABLED=False,
    LOGIN_MIN_FORM_SECONDS=0,
    ALLOWED_HOSTS=["*", "demo.runmycampus.com", "manager.runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class PostLoginMfaRoutingTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="mfa-admin@test.local",
            email="mfa-admin@test.local",
            password="MfaPass123!",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.school = School.objects.create(
            name="MFA School",
            slug="mfa-school",
            subdomain="mfa-school",
            is_active=True,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        TOTPDevice.objects.create(user=self.user, name="default", confirmed=True)

    def _request(self, path="/authentication/login/", *, host="mfa-school.runmycampus.com"):
        request = self.factory.post(path, HTTP_HOST=host)
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        request.user = self.user
        request.school = self.school
        return request

    def test_device_holder_redirects_to_mfa_verify(self):
        request = self._request()
        response = resolve_post_login_mfa_redirect(request, self.user)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/authentication/mfa/verify", response["Location"])

    def test_unconfirmed_device_does_not_send_to_verify(self):
        TOTPDevice.objects.filter(user=self.user).delete()
        TOTPDevice.objects.create(user=self.user, name="draft", confirmed=False)
        request = self._request()
        with patch(
            "apps.accounts.post_login_mfa._resolve_enforcement_mode",
            return_value=("optional", 7),
        ):
            response = resolve_post_login_mfa_redirect(request, self.user)
        self.assertIsNone(response)

    def test_strict_no_device_redirects_to_setup_not_verify(self):
        TOTPDevice.objects.filter(user=self.user).delete()
        request = self._request()
        with patch(
            "apps.accounts.post_login_mfa._resolve_enforcement_mode",
            return_value=("strict", None),
        ):
            response = resolve_post_login_mfa_redirect(request, self.user)
        self.assertIsNotNone(response)
        self.assertIn("/mfa/setup", response["Location"])
        self.assertNotIn("/mfa/verify", response["Location"])

    def test_incomplete_owner_onboarding_skips_post_login_mfa(self):
        TOTPDevice.objects.filter(user=self.user).delete()
        self.school.settings = {
            "owner_onboarding": {"step": "school", "completed": False}
        }
        self.school.save(update_fields=["settings"])
        SchoolMembership.objects.filter(user=self.user, school=self.school).update(
            is_school_owner=True
        )
        request = self._request()
        with patch(
            "apps.accounts.post_login_mfa._resolve_enforcement_mode",
            return_value=("strict", None),
        ):
            response = resolve_post_login_mfa_redirect(request, self.user)
        self.assertIsNone(response)

    def test_mfa_before_manager_handoff_for_tenant_admin(self):
        """Manager-host password must not bounce to school login before MFA."""
        self.client.force_login(self.user)
        request = self._request(host="manager.runmycampus.com")
        request.public_host_kind = "manager"
        with patch(
            "apps.schools.tenant_login_redirect.resolve_public_post_login_handoff"
        ) as handoff:
            handoff.return_value = None
            response = resolve_post_login_mfa_redirect(request, self.user)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/mfa/verify", response["Location"])
        handoff.assert_not_called()

    def test_login_post_with_totp_device_redirects_to_mfa(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": "mfa-admin@test.local",
                "password": "MfaPass123!",
            },
            HTTP_HOST="mfa-school.runmycampus.com",
        )
        self.assertEqual(
            response.status_code, 302, msg=getattr(response, "content", b"")[:500]
        )
        self.assertIn("/authentication/mfa/verify", response.url)


class RequireMfaBackendNotBypassedTests(TestCase):
    def test_backend_path_enforces_mfa_when_device_present(self):
        from django.http import HttpResponse

        from apps.accounts.middleware import RequireMFAMiddleware

        user = User.objects.create_user(
            username="backend-mfa",
            email="backend-mfa@test.local",
            password="Pass1234!",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        TOTPDevice.objects.create(user=user, name="default", confirmed=True)
        factory = RequestFactory()
        request = factory.get("/authentication/backend/")
        request.user = user
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        site = type(
            "S",
            (),
            {
                "require_mfa_all_staff": False,
                "require_mfa_roles": ["ADMIN"],
                "mfa_enforcement_mode": "strict",
                "mfa_grace_period_days": 0,
            },
        )()
        with patch(
            "apps.accounts.middleware.get_effective_site_settings",
            return_value=site,
        ):
            response = RequireMFAMiddleware(lambda r: HttpResponse("ok"))(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/mfa/verify", response.url)

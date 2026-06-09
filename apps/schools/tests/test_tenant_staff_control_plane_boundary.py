"""Tenant staff must never inherit manager-host / control-plane access."""

from __future__ import annotations

import os
from unittest import mock

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.schools.control_plane import user_has_control_plane_access
from apps.schools.models import School, SchoolMembership


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "runmycampus.com", "manager.runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    RMC_PUBLIC_SITE_URL="https://runmycampus.com",
    SECURE_SSL_REDIRECT=False,
)
class TenantStaffControlPlaneBoundaryTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Saint Jude the Great",
            slug="saint-jude-the-great",
            subdomain="saint-jude-the-great",
            is_active=False,
        )
        self.owner = User.objects.create_user(
            username="owner@saintjude.test",
            email="owner@saintjude.test",
            password="unused",
            role=User.Role.ADMIN,
        )
        self.owner.set_unusable_password()
        self.owner.save(update_fields=["password"])
        SchoolMembership.objects.create(
            user=self.owner,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )

    @mock.patch.dict(os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": "SUPERADMIN,ADMIN"})
    def test_tenant_admin_blocked_from_control_plane_even_when_env_lists_admin(self):
        self.assertFalse(user_has_control_plane_access(self.owner))

    @mock.patch.dict(os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": "SUPERADMIN,ADMIN"})
    def test_tenant_admin_forbidden_on_manager_super_dashboard(self):
        client = Client(HTTP_HOST="manager.runmycampus.com")
        client.force_login(self.owner)
        response = client.get("/super/", follow=False)
        self.assertEqual(response.status_code, 403)

    def test_public_login_stays_on_marketing_host_not_manager(self):
        client = Client(HTTP_HOST="runmycampus.com")
        response = client.get("/authentication/login/", follow=False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.wsgi_request.META.get("HTTP_HOST"), "runmycampus.com"
        )

    def test_manager_verify_signup_redirects_to_public_host(self):
        client = Client(HTTP_HOST="manager.runmycampus.com")
        response = client.get(
            "/verify-signup/?token=00000000-0000-0000-0000-000000000001",
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("runmycampus.com", response["Location"])
        self.assertIn("/verify-signup/", response["Location"])
        self.assertNotIn("manager.", response["Location"])

    @mock.patch.dict(os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": "SUPERADMIN,ADMIN"})
    def test_tenant_admin_not_platform_operator(self):
        from apps.platform_runtime.operator_identity import (
            queryset_platform_operators,
            user_effective_platform_scopes,
            user_is_platform_operator,
        )

        self.assertFalse(user_is_platform_operator(self.owner))
        self.assertNotIn(
            self.owner.pk,
            queryset_platform_operators().values_list("pk", flat=True),
        )
        self.assertFalse(user_effective_platform_scopes(self.owner))

    @mock.patch.dict(os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": "SUPERADMIN,ADMIN"})
    def test_tenant_admin_manager_login_redirects_to_public(self):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        from apps.accounts.views import redirect_view

        factory = RequestFactory()
        request = factory.get(
            "/authentication/redirect/", HTTP_HOST="manager.runmycampus.com"
        )
        request.user = self.owner
        request.public_host_kind = "manager"
        request.session = {}
        request._messages = FallbackStorage(request)
        response = redirect_view(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("runmycampus.com", response["Location"])
        self.assertNotIn("manager.", response["Location"])

    def test_manager_resend_verification_redirects_to_public_host(self):
        client = Client(HTTP_HOST="manager.runmycampus.com")
        response = client.get("/verify-signup/resend/", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("runmycampus.com", response["Location"])
        self.assertIn("/verify-signup/resend/", response["Location"])
        self.assertNotIn("manager.", response["Location"])

    def test_public_resend_verification_stays_on_marketing_host(self):
        client = Client(HTTP_HOST="runmycampus.com")
        response = client.get("/verify-signup/resend/", follow=False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.wsgi_request.META.get("HTTP_HOST"), "runmycampus.com"
        )

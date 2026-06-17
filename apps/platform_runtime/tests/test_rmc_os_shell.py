"""resolve_rmc_os_shell honors nav portal role (session hat)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.accounts.portal_roles import ACTIVE_PORTAL_ROLE_KEY
from apps.platform_runtime.rmc_os_shell import resolve_rmc_os_shell

UserModel = get_user_model()


class RmcOsShellNavRoleTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_admin_with_parent_session_is_parent_cluster(self):
        user = UserModel.objects.create_user(
            username="os_admin_parent",
            email="os_admin_parent@example.com",
            password="Test1234!long",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        request = self.factory.get("/portal/parent/")
        request.user = user
        request.session = {ACTIVE_PORTAL_ROLE_KEY: User.Role.PARENT}
        request.public_host_kind = "tenant"
        request.path = "/portal/parent/"

        ctx = resolve_rmc_os_shell(request)
        self.assertEqual(ctx["role_cluster"], "parent")
        self.assertEqual(ctx["surface_kind"], "tenant-portal")

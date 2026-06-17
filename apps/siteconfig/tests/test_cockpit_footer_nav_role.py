"""Footer descriptor honors nav portal role (session parent hat on admin)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.accounts.portal_roles import ACTIVE_PORTAL_ROLE_KEY
from apps.siteconfig.cockpit_context import _tenant_footer_defaults

UserModel = get_user_model()


class CockpitFooterNavRoleTests(TestCase):
    def test_admin_with_parent_hat_gets_family_descriptor(self):
        user = UserModel.objects.create_user(
            username="footer_admin_parent",
            email="footer_admin_parent@example.com",
            password="Test1234!long",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        request = RequestFactory().get("/portal/parent/")
        request.user = user
        request.session = {ACTIVE_PORTAL_ROLE_KEY: User.Role.PARENT}

        ctx = _tenant_footer_defaults(site=None, request=request)
        descriptor = ctx.get("brand", {}).get("descriptor", "")
        self.assertIn("Family", descriptor)

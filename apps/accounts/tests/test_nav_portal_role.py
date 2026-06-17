"""Unit tests for get_nav_portal_role session-hat contract."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.accounts.portal_roles import ACTIVE_PORTAL_ROLE_KEY, get_nav_portal_role

UserModel = get_user_model()


class NavPortalRoleTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_session_parent_hat_overrides_admin_primary(self):
        user = UserModel.objects.create_user(
            username="nav_admin",
            email="nav_admin@example.com",
            password="Test1234!long",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        request = self.factory.get("/")
        request.user = user
        request.session = {ACTIVE_PORTAL_ROLE_KEY: User.Role.PARENT}
        self.assertEqual(get_nav_portal_role(request), User.Role.PARENT)

    def test_session_parent_hat_without_guardian_still_wins(self):
        user = UserModel.objects.create_user(
            username="nav_admin_no_guardian",
            email="nav_admin_no_guardian@example.com",
            password="Test1234!long",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        request = self.factory.get("/")
        request.user = user
        request.session = {ACTIVE_PORTAL_ROLE_KEY: User.Role.PARENT}
        self.assertEqual(get_nav_portal_role(request), User.Role.PARENT)

    def test_primary_parent_without_session(self):
        user = UserModel.objects.create_user(
            username="nav_parent",
            email="nav_parent@example.com",
            password="Test1234!long",
            role=User.Role.PARENT,
        )
        request = self.factory.get("/")
        request.user = user
        request.session = {}
        self.assertEqual(get_nav_portal_role(request), User.Role.PARENT)

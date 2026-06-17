"""Post-login redirect must honor family/student hats before staff backend."""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.portal_roles import ACTIVE_PORTAL_ROLE_KEY

UserModel = get_user_model()


class RedirectNavRoleTests(TestCase):
    def _redirect_url(self, user, *, session_role=None):
        self.client.force_login(user)
        if session_role is not None:
            session = self.client.session
            session[ACTIVE_PORTAL_ROLE_KEY] = session_role
            session.save()
        resp = self.client.get(reverse("accounts:redirect"), follow=False)
        self.assertEqual(resp.status_code, 302)
        return resp.url or ""

    @mock.patch(
        "apps.accounts.models.User.has_feature_permission",
        lambda self, code, **kwargs: code == "settings.manage",
    )
    def test_parent_with_settings_manage_goes_to_family_home(self):
        user = UserModel.objects.create_user(
            username="parent_admin",
            email="parent_admin@example.com",
            password="Test1234!long",
            role=User.Role.PARENT,
            is_staff=True,
        )
        url = self._redirect_url(user)
        self.assertIn("parent", url.lower())
        self.assertNotIn("backend", url.lower())

    @mock.patch(
        "apps.accounts.models.User.has_feature_permission",
        lambda self, code, **kwargs: code == "settings.manage",
    )
    def test_admin_with_parent_session_hat_goes_to_parent(self):
        user = UserModel.objects.create_user(
            username="admin_parent_hat",
            email="admin_parent_hat@example.com",
            password="Test1234!long",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        url = self._redirect_url(user, session_role=User.Role.PARENT)
        self.assertIn("parent", url.lower())
        self.assertNotIn("backend", url.lower())

    @mock.patch(
        "apps.accounts.models.User.has_feature_permission",
        lambda self, code, **kwargs: code == "settings.manage",
    )
    def test_student_not_sent_to_backend_when_staff(self):
        user = UserModel.objects.create_user(
            username="student_staff",
            email="student_staff@example.com",
            password="Test1234!long",
            role=User.Role.STUDENT,
            is_staff=True,
        )
        url = self._redirect_url(user)
        lowered = url.lower()
        self.assertTrue(
            "student" in lowered or "grades" in lowered,
            f"Expected student portal URL, got {url}",
        )

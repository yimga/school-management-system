"""AI assistant registry permission helpers."""

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.siteconfig.ai_assistants import user_may_use_assistant


class UserMayUseAssistantTests(SimpleTestCase):
    def _user(self, **kwargs):
        base = {
            "is_authenticated": True,
            "is_superuser": False,
            "is_staff": False,
            "role": "TEACHER",
        }
        base.update(kwargs)
        user = SimpleNamespace(**base)
        user.has_feature_permission = lambda code: kwargs.get("has_settings_manage", False)
        return user

    def test_superuser_always_allowed(self):
        u = self._user(is_superuser=True)
        self.assertTrue(user_may_use_assistant(u, "settings.manage"))

    def test_superadmin_control_plane_allowed_without_feature_perm(self):
        u = self._user(role="SUPERADMIN")
        self.assertTrue(user_may_use_assistant(u, "settings.manage"))

    def test_teacher_denied_without_feature_perm(self):
        u = self._user(role="TEACHER")
        self.assertFalse(user_may_use_assistant(u, "settings.manage"))

    def test_tenant_admin_with_settings_manage(self):
        u = self._user(role="ADMIN", has_settings_manage=True)
        self.assertTrue(user_may_use_assistant(u, "settings.manage"))

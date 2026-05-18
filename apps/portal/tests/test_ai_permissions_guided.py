"""Permissions for domain guided-assistant task types (§2.3 extension)."""

from types import SimpleNamespace

from django.test import SimpleTestCase

from services.ai_permissions import get_ai_permission_for_user


class GuidedAssistantPermissionsTests(SimpleTestCase):
    def _user(self, **kwargs):
        base = {
            "is_authenticated": True,
            "is_staff": False,
            "is_superuser": False,
            "role": "TEACHER",
        }
        base.update(kwargs)
        return SimpleNamespace(**base)

    def test_interop_staff_no_school_ok(self):
        u = self._user(is_staff=True, role="TEACHER")
        self.assertTrue(get_ai_permission_for_user(u, "interop_assistant", None))

    def test_interop_tenant_admin_with_school_ok(self):
        u = self._user(role="ADMIN")
        self.assertTrue(get_ai_permission_for_user(u, "interop_assistant", object()))

    def test_interop_teacher_denied(self):
        u = self._user(role="TEACHER")
        self.assertFalse(get_ai_permission_for_user(u, "interop_assistant", object()))

    def test_observability_requires_staff(self):
        # Use TEACHER — ADMIN may be listed in CONTROL_PLANE_OPERATOR_ROLES on some hosts.
        u = self._user(role="TEACHER")
        self.assertFalse(get_ai_permission_for_user(u, "observability_assistant", object()))
        u2 = self._user(is_staff=True, role="TEACHER")
        self.assertTrue(get_ai_permission_for_user(u2, "observability_assistant", None))

    def test_trust_compliance_staff(self):
        u = self._user(is_staff=True)
        self.assertTrue(get_ai_permission_for_user(u, "trust_compliance_assistant", None))

    def test_billing_bursar_on_tenant(self):
        u = self._user(role="BURSAR")
        self.assertTrue(get_ai_permission_for_user(u, "billing_usage_explain", object()))

    def test_billing_teacher_denied(self):
        u = self._user(role="TEACHER")
        self.assertFalse(get_ai_permission_for_user(u, "billing_usage_explain", object()))

    def test_superadmin_control_plane_without_staff_ok(self):
        """Manager operators: role=SUPERADMIN, not necessarily is_staff."""
        u = self._user(role="SUPERADMIN", is_staff=False)
        self.assertTrue(get_ai_permission_for_user(u, "interop_assistant", None))
        self.assertTrue(get_ai_permission_for_user(u, "runtime_config_explain", None))
        self.assertTrue(get_ai_permission_for_user(u, "observability_assistant", None))
        self.assertTrue(get_ai_permission_for_user(u, "trust_compliance_assistant", None))
        self.assertTrue(get_ai_permission_for_user(u, "billing_usage_explain", None))

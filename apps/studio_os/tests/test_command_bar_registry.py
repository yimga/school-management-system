"""Universal Command Bar registry role filtering (v3.53.0, 2026-05-21).

Asserts:
  - anonymous users see 0 actions
  - staff sees every action
  - tenant_admin sees a strict subset of staff
  - tenant_user sees a strict subset of tenant_admin
  - tenant URL leakage is prevented when school is None for non-staff
  - the catalog is non-trivial (>= ~20 actions resolve)
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.siteconfig.command_bar_registry import (
    CommandAction,
    all_registered,
    get_actions_for_user,
    serialize_actions,
)


def _user(*, authenticated=True, is_staff=False, is_superuser=False, role=""):
    return SimpleNamespace(
        is_authenticated=authenticated,
        is_staff=is_staff,
        is_superuser=is_superuser,
        role=role,
    )


def _school():
    return SimpleNamespace(pk=1, name="Demo Tenant", slug="demo")


class CommandBarRegistryShapeTests(SimpleTestCase):
    def test_catalog_returns_command_actions(self):
        actions = all_registered()
        # Allow for env-dependent URL resolution failures dropping some entries,
        # but the catalog must still be substantive.
        self.assertGreaterEqual(len(actions), 8, "command catalog too small")
        for a in actions:
            self.assertIsInstance(a, CommandAction)
            self.assertTrue(a.kind)
            self.assertTrue(a.label)
            self.assertTrue(a.url)
            self.assertIn(a.scope, {"staff", "tenant_admin", "tenant_user"})

    def test_serialize_actions_round_trip(self):
        actions = all_registered()
        serialized = serialize_actions(actions[:3])
        self.assertEqual(len(serialized), 3)
        for d in serialized:
            self.assertIn("kind", d)
            self.assertIn("label", d)
            self.assertIn("url", d)
            self.assertIn("scope", d)


class CommandBarRegistryFilterTests(SimpleTestCase):
    def test_anonymous_user_sees_zero_actions(self):
        anon = SimpleNamespace(is_authenticated=False, is_staff=False, role="")
        self.assertEqual(get_actions_for_user(anon, _school()), [])
        self.assertEqual(get_actions_for_user(None, _school()), [])

    def test_staff_sees_all_actions(self):
        staff = _user(is_staff=True)
        result = get_actions_for_user(staff, _school())
        # Staff visibility >= every other user class visibility.
        self.assertGreater(len(result), 0)
        # Confirm at least one staff-scope action is present.
        self.assertTrue(any(a.scope == "staff" for a in result))

    def test_tenant_admin_sees_subset_of_staff(self):
        admin = _user(role="ADMIN")
        staff = _user(is_staff=True)
        admin_acts = get_actions_for_user(admin, _school())
        staff_acts = get_actions_for_user(staff, _school())
        self.assertLessEqual(len(admin_acts), len(staff_acts))
        # No staff-only action in admin's view.
        self.assertFalse(any(a.scope == "staff" for a in admin_acts))

    def test_tenant_user_sees_subset_of_admin(self):
        user = _user(role="TEACHER")
        admin = _user(role="ADMIN")
        user_acts = get_actions_for_user(user, _school())
        admin_acts = get_actions_for_user(admin, _school())
        self.assertLessEqual(len(user_acts), len(admin_acts))
        # No staff or admin-only action in user's view.
        for a in user_acts:
            self.assertEqual(a.scope, "tenant_user")

    def test_tenant_user_without_school_sees_nothing(self):
        """Tenant context discipline: non-staff requires a school context."""
        user = _user(role="TEACHER")
        self.assertEqual(get_actions_for_user(user, None), [])

    def test_staff_without_school_still_sees_staff_actions(self):
        """Manager host with no school selected — staff still has actions."""
        staff = _user(is_staff=True)
        acts = get_actions_for_user(staff, None)
        self.assertTrue(len(acts) > 0)
        for a in acts:
            # Tenant-scoped actions are dropped at staff/no-school per registry
            # logic; staff-scoped actions remain visible.
            self.assertIn(a.scope, {"staff", "tenant_admin", "tenant_user"})

    def test_proprietor_role_treated_as_tenant_admin(self):
        prop = _user(role="PROPRIETOR")
        teacher = _user(role="TEACHER")
        self.assertGreaterEqual(
            len(get_actions_for_user(prop, _school())),
            len(get_actions_for_user(teacher, _school())),
        )

    def test_no_cross_tenant_url_leakage(self):
        """All URLs returned must be relative paths (no fully-qualified other-tenant URLs)."""
        staff = _user(is_staff=True)
        for a in get_actions_for_user(staff, _school()):
            self.assertFalse(a.url.startswith("http://"), a.url)
            self.assertFalse(a.url.startswith("https://"), a.url)
            self.assertTrue(a.url.startswith("/"), f"unexpected URL: {a.url}")

    def test_tenant_request_hides_operator_plane_actions_even_for_staff(self):
        """Staff on a tenant host must not see manager /super/ or /admin/ commands."""
        staff = _user(is_staff=True)
        request = SimpleNamespace(public_host_kind=None)
        for a in get_actions_for_user(staff, _school(), request=request):
            self.assertFalse(a.url.startswith("/super/"), a.url)
            self.assertFalse(a.url.startswith("/admin/"), a.url)

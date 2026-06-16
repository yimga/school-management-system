"""Resilient portal-sidebar baseline + context-processor fallback (no DB).

The under-provisioned new-tenant symptom: ``build_portal_sidebar_items`` raises or
returns nothing → the template used to drop to a hardcoded, ungated fallback nav.
These tests lock the replacement: a role + permission gated BASELINE of known-good
routes, and the context processor wiring that serves it instead of ``[]``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.siteconfig import portal_sidebar_items as psi

# Make every route "resolve" so the tests exercise the role/permission LOGIC, not
# which URL names happen to exist in the test URLconf.
_FAKE_REVERSE = lambda name, kwargs=None, args=None, default=None: "/" + name.replace(":", "/")  # noqa: E731


def _user(*, authed=True, role="", is_staff=False, is_superuser=False, perms=()):
    return SimpleNamespace(
        is_authenticated=authed,
        role=role,
        is_staff=is_staff,
        is_superuser=is_superuser,
        has_feature_permission=lambda code: code in perms,
    )


class BaselineRoleGatingTests(SimpleTestCase):
    def _build(self, user):
        with mock.patch.object(psi, "_safe_reverse", _FAKE_REVERSE):
            return psi.build_portal_sidebar_baseline(SimpleNamespace(user=user))

    def _ids(self, items):
        return {it["id"] for it in items}

    def test_anonymous_gets_empty_list(self):
        self.assertEqual(self._build(_user(authed=False)), [])
        self.assertEqual(
            psi.build_portal_sidebar_baseline(SimpleNamespace(user=None)), []
        )

    def test_every_item_has_a_resolved_url(self):
        items = self._build(_user(role="TEACHER"))
        self.assertTrue(items)
        for it in items:
            self.assertTrue(it["url"])
            self.assertIn("section", it)
            self.assertIn(it["surface"], ("ops", "config"))

    def test_teacher_floor(self):
        ids = self._ids(self._build(_user(role="TEACHER")))
        self.assertIn("home", ids)
        self.assertIn("teacher_marks", ids)
        self.assertIn("teacher_attendance", ids)
        # A teacher never gets the admin floor.
        self.assertNotIn("backend_dashboard", ids)
        self.assertNotIn("finance", ids)

    def test_parent_floor(self):
        ids = self._ids(self._build(_user(role="PARENT")))
        self.assertIn("parent_home", ids)
        self.assertIn("parent_finance", ids)
        self.assertNotIn("teacher_home", ids)
        self.assertNotIn("backend_dashboard", ids)

    def test_student_floor(self):
        ids = self._ids(self._build(_user(role="STUDENT")))
        self.assertIn("student_home", ids)
        self.assertNotIn("backend_dashboard", ids)

    def test_admin_always_gets_command_center_and_setup_wizards(self):
        # Even with NO feature perms, a new admin must be able to finish setup.
        ids = self._ids(self._build(_user(role="ADMIN", perms=())))
        self.assertIn("backend_dashboard", ids)
        self.assertIn("setup_wizards", ids)
        self.assertIn("people", ids)
        # Feature-gated items are withheld without the permission.
        self.assertNotIn("finance", ids)
        self.assertNotIn("config", ids)

    def test_admin_with_settings_manage_gets_gated_items(self):
        ids = self._ids(self._build(_user(role="ADMIN", perms=("settings.manage",))))
        self.assertIn("finance", ids)
        self.assertIn("config", ids)

    def test_superuser_passes_feature_gate(self):
        ids = self._ids(self._build(_user(role="", is_superuser=True)))
        self.assertIn("backend_dashboard", ids)
        self.assertIn("finance", ids)  # superuser short-circuits the perm check

    def test_is_staff_non_admin_role_still_gets_admin_floor(self):
        ids = self._ids(self._build(_user(role="", is_staff=True)))
        self.assertIn("backend_dashboard", ids)

    def test_never_raises_on_malformed_user(self):
        # A user object missing attributes must not blow up the sidebar.
        with mock.patch.object(psi, "_safe_reverse", _FAKE_REVERSE):
            out = psi.build_portal_sidebar_baseline(SimpleNamespace(user=SimpleNamespace()))
        self.assertEqual(out, [])  # not authenticated → empty, no exception


class ContextProcessorFallbackTests(SimpleTestCase):
    def test_full_builder_result_is_used_when_present(self):
        from apps.siteconfig import context_processors as cp

        sentinel = [{"id": "real", "url": "/x", "section": "Home"}]
        with mock.patch.object(cp, "build_portal_sidebar_items", return_value=sentinel), \
                mock.patch.object(cp, "build_portal_sidebar_baseline") as baseline:
            result = cp._get_portal_sidebar_items(SimpleNamespace(user=_user()), None)
        self.assertEqual(result, sentinel)
        baseline.assert_not_called()

    def test_empty_full_builder_falls_back_to_baseline(self):
        from apps.siteconfig import context_processors as cp

        with mock.patch.object(cp, "build_portal_sidebar_items", return_value=[]), \
                mock.patch.object(cp, "build_portal_sidebar_baseline", return_value=["BASE"]) as baseline:
            result = cp._get_portal_sidebar_items(SimpleNamespace(user=_user()), None)
        self.assertEqual(result, ["BASE"])
        baseline.assert_called_once()

    def test_raising_full_builder_falls_back_to_baseline(self):
        from apps.siteconfig import context_processors as cp

        with mock.patch.object(cp, "build_portal_sidebar_items", side_effect=ValueError("boom")), \
                mock.patch.object(cp, "build_portal_sidebar_baseline", return_value=["BASE"]):
            result = cp._get_portal_sidebar_items(SimpleNamespace(user=_user()), None)
        self.assertEqual(result, ["BASE"])

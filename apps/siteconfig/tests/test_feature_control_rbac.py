"""Per-category RBAC for the Feature Control panel (2026-07-06 follow-up).

Proves the access model the write-enforcement relies on: a delegate holding one category's
granular code sees/edits ONLY that category; a settings.feature_control (or admin-tier)
holder sees every category (additive); and the system category is never delegated.
"""
from django.test import SimpleTestCase

from apps.siteconfig.views_feature_control import (
    FEATURE_CATEGORIES,
    FEATURE_CATEGORY_PERMISSION,
    _FEATURE_CONTROL_PANEL_CODES,
    _feature_key_to_category,
    accessible_feature_categories,
)


class _FakeUser:
    def __init__(self, *, authed=True, superuser=False, role="", codes=()):
        self.is_authenticated = authed
        self.is_superuser = superuser
        self.role = role
        self._codes = set(codes)
        self.pk = 1

    def has_feature_permission(self, code, *, school=None):
        return code in self._codes


class AccessibleCategoriesTest(SimpleTestCase):
    def test_base_grant_unlocks_all(self):
        u = _FakeUser(codes=("settings.feature_control",))
        self.assertEqual(
            accessible_feature_categories(u, None), set(FEATURE_CATEGORIES.keys())
        )

    def test_admin_tier_unlocks_all(self):
        u = _FakeUser(role="ADMIN", codes=())  # ADMIN is admin-like -> base via allow_admin
        self.assertEqual(
            accessible_feature_categories(u, None), set(FEATURE_CATEGORIES.keys())
        )

    def test_finance_delegate_sees_only_finance(self):
        u = _FakeUser(role="BURSAR", codes=("finance.manage",))
        self.assertEqual(accessible_feature_categories(u, None), {"finance_permissions"})

    def test_grades_delegate_sees_only_academic(self):
        u = _FakeUser(role="HOD", codes=("grades.manage",))
        self.assertEqual(accessible_feature_categories(u, None), {"academic"})

    def test_grade_entry_teacher_has_no_categories(self):
        # grades.enter is NOT a category code -> a plain teacher cannot open the panel.
        u = _FakeUser(role="TEACHER", codes=("grades.enter",))
        self.assertEqual(accessible_feature_categories(u, None), set())

    def test_unauthenticated_empty(self):
        self.assertEqual(accessible_feature_categories(_FakeUser(authed=False), None), set())


class CategoryContractTest(SimpleTestCase):
    def test_every_category_has_a_permission(self):
        self.assertEqual(
            set(FEATURE_CATEGORY_PERMISSION.keys()), set(FEATURE_CATEGORIES.keys())
        )

    def test_system_category_is_admin_only(self):
        # system maps to the base gate -> never delegated to a granular category code.
        self.assertEqual(FEATURE_CATEGORY_PERMISSION["system"], "settings.feature_control")

    def test_panel_codes_include_base_and_categories(self):
        self.assertIn("settings.feature_control", _FEATURE_CONTROL_PANEL_CODES)
        self.assertIn("finance.manage", _FEATURE_CONTROL_PANEL_CODES)
        self.assertIn("grades.manage", _FEATURE_CONTROL_PANEL_CODES)

    def test_key_to_category_covers_finance_and_system(self):
        # The write-enforcement reverts posted changes to keys whose category the delegate
        # can't manage; this proves finance + system keys resolve to their categories.
        m = _feature_key_to_category()
        cats = set(m.values())
        self.assertIn("finance_permissions", cats)
        self.assertIn("system", cats)
        # Every mapped key belongs to a real category.
        self.assertTrue(set(m.values()) <= set(FEATURE_CATEGORIES.keys()))

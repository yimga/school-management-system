"""Phase 4A — Group Console visibility and context tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.schools.group_console import (
    build_group_console_context,
    group_console_visible,
)


class GroupConsoleVisibilityTests(SimpleTestCase):
    def test_standalone_school_not_visible(self):
        school = SimpleNamespace(
            organization_id=None,
            governance_operating_mode="standalone",
        )
        self.assertFalse(group_console_visible(school))

    def test_group_member_with_org_is_visible(self):
        school = SimpleNamespace(
            organization_id="org-1",
            governance_operating_mode="group_member",
        )
        self.assertTrue(group_console_visible(school))

    def test_group_member_without_org_not_visible(self):
        school = SimpleNamespace(
            organization_id=None,
            governance_operating_mode="group_member",
        )
        self.assertFalse(group_console_visible(school))


class GroupConsoleContextTests(SimpleTestCase):
    @patch("apps.schools.group_console.member_schools_for_organization")
    @patch("apps.schools.group_console._organization_for_school")
    @patch("apps.schools.group_console.matrix_admin_labels", return_value=[{"level": 1}])
    def test_build_context_includes_members(self, _labels, mock_org_for, mock_members):
        org = SimpleNamespace(pk="org-1", name="Trust")
        school = SimpleNamespace(
            pk="s1",
            name="Alpha",
            slug="alpha",
            country_code="CM",
            settings={"governance_inherit": {"fees": "inherit"}},
            governance_operating_mode="group_member",
            organization_id="org-1",
        )
        mock_org_for.return_value = org
        member = SimpleNamespace(pk="s2", name="Beta", slug="beta", governance_operating_mode="group_member")
        mock_members.return_value = [school, member]

        ctx = build_group_console_context(school, MagicMock(is_authenticated=False))
        self.assertEqual(ctx["member_count"], 2)
        self.assertEqual(ctx["inherit_domains"]["fees"], "inherit")
        self.assertEqual(len(ctx["admin_level_labels"]), 1)

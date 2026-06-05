"""v4.02.15 — default quick actions seed tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.assist_dock.default_quick_actions import register_default_quick_actions
from apps.assist_dock.quick_actions import actions_for, all_actions, reset_actions_for_tests


class DefaultQuickActionsTests(SimpleTestCase):
    def setUp(self):
        reset_actions_for_tests()
        register_default_quick_actions()

    def tearDown(self):
        reset_actions_for_tests()

    def test_seeds_register_expected_ids(self):
        ids = {action.id for action in all_actions()}
        self.assertIn("tools-qa-finance-hub", ids)
        self.assertIn("tools-qa-backend-home", ids)

    def test_finance_hub_visible_on_finance_path(self):
        visible = {
            action.id
            for action in actions_for(
                surface="portal", role="TEACHER", page_path="/finance/invoices/"
            )
        }
        self.assertIn("tools-qa-finance-hub", visible)

    def test_super_home_hidden_on_tenant_finance(self):
        visible = {
            action.id
            for action in actions_for(
                surface="portal", role="TEACHER", page_path="/finance/invoices/"
            )
        }
        self.assertNotIn("tools-qa-super-home", visible)

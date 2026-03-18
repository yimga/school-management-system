"""
Tests for the role-home engine (Phase F: single source of truth for role-native dashboard config).
"""

from django.test import TestCase

from apps.dashboard.role_home_engine import (
    INTENT_KPI_PRIORITY,
    VALID_DASHBOARD_INTENTS,
    prioritize_destinations,
    resolve_role_home,
    select_kpis_for_intent,
    select_role_home_actions,
)


class RoleHomeEngineTests(TestCase):
    """Resolve role-home config and action selection by role and intent."""

    def test_resolve_role_home_principal_default(self):
        role_home = resolve_role_home("PRINCIPAL", None)
        self.assertEqual(role_home["key"], "principal")
        self.assertEqual(role_home["active_intent"], "executive")
        self.assertIn("School pulse", role_home["focus_areas"])

    def test_resolve_role_home_teacher_academic(self):
        role_home = resolve_role_home("TEACHER", "academic")
        self.assertEqual(role_home["key"], "teacher")
        self.assertEqual(role_home["active_intent"], "academic")

    def test_resolve_role_home_finance_intent(self):
        role_home = resolve_role_home("BURSAR", "finance")
        self.assertEqual(role_home["key"], "finance")
        self.assertEqual(role_home["active_intent"], "finance")

    def test_resolve_role_home_admin_setup(self):
        role_home = resolve_role_home("ADMIN", "setup")
        self.assertEqual(role_home["key"], "implementation")
        self.assertEqual(role_home["active_intent"], "setup")

    def test_resolve_role_home_unknown_role_falls_back_to_principal(self):
        role_home = resolve_role_home("UNKNOWN_ROLE", None)
        self.assertEqual(role_home["key"], "principal")

    def test_prioritize_destinations_prefers_role_destinations(self):
        role_home = {"destinations": ["workflow_center", "preferences"]}
        action_chips = [{"id": "preferences", "label": "Prefs", "url": "/prefs/"}]
        quick_links = [
            {"id": "workflow_center", "label": "Workflow", "url": "/workflow/"}
        ]
        contextual = []
        result = prioritize_destinations(
            role_home, action_chips, quick_links, contextual, max_items=5
        )
        self.assertGreaterEqual(len(result), 1)
        ids = [r.get("id") for r in result if r.get("id")]
        self.assertIn("workflow_center", ids)
        self.assertIn("preferences", ids)

    def test_select_role_home_actions_primary_and_supporting(self):
        next_best = [{"label": "Setup", "url": "/setup/"}]
        primary_ctas = [{"label": "Studio", "url": "/studio/"}]
        destinations = [{"label": "Workflow", "url": "/workflow/"}]
        primary, supporting = select_role_home_actions(
            next_best, primary_ctas, destinations
        )
        self.assertIsNotNone(primary)
        self.assertEqual(primary["label"], "Setup")
        self.assertLessEqual(len(supporting), 3)

    def test_select_kpis_for_intent_orders_by_priority(self):
        kpis = [
            {"id": "recent_admissions", "label": "Admissions"},
            {"id": "top_performing", "label": "Top"},
            {"id": "attendance_today", "label": "Attendance"},
        ]
        ordered = select_kpis_for_intent(kpis, "executive")
        self.assertEqual(len(ordered), 3)
        self.assertEqual(ordered[0]["id"], "top_performing")
        self.assertEqual(ordered[1]["id"], "attendance_today")
        self.assertEqual(ordered[2]["id"], "recent_admissions")

    def test_valid_intents_match_config(self):
        self.assertEqual(VALID_DASHBOARD_INTENTS, frozenset(INTENT_KPI_PRIORITY.keys()))
        self.assertIn("setup", VALID_DASHBOARD_INTENTS)
        self.assertIn("finance", VALID_DASHBOARD_INTENTS)

    def test_registrar_maps_to_admissions_home(self):
        role_home = resolve_role_home("REGISTRAR", None)
        self.assertEqual(role_home["key"], "admissions")

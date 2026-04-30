"""Phase 8 — decision surface mapping for backend role home."""

from django.test import SimpleTestCase

from apps.dashboard.decision_surface_context import (
    build_backend_dashboard_phase7_de,
    build_role_home_declaration,
)


class DecisionSurfaceContextTests(SimpleTestCase):
    def test_build_phase7_maps_zones(self):
        role_home = {
            "eyebrow": "Test home",
            "dashboard_type": "operational",
            "jtbd": "Do the thing",
            "main_question": "What now?",
            "main_action": "Click primary",
        }
        kpis = [
            {
                "label": "L1",
                "value": "10",
                "meta": "m1",
                "status": "ok",
            },
            {"label": "L2", "value": 2, "meta": "", "status": "warn"},
        ]
        queue = [
            {"label": "Q1", "url": "/q/", "meta": "hint", "value": 1, "status": "ok"}
        ]
        nba = [{"label": "Next", "url": "/n/"}]
        primary = {"label": "Primary", "url": "/p/"}
        supporting = [{"label": "S1", "url": "/s1/"}]
        activity = [{"title": "T", "actor": "A", "action": "did"}]

        d = build_backend_dashboard_phase7_de(
            role_home=role_home,
            kpi_strip_cards=kpis,
            dashboard_priority_queue=queue,
            dashboard_next_best_actions=nba,
            role_home_primary_action=primary,
            role_home_supporting_actions=supporting,
            dashboard_recent_activity=activity,
        )
        self.assertEqual(d["eyebrow"], "Test home")
        self.assertEqual(d["headline_label"], "L1")
        self.assertEqual(d["headline_value"], "10")
        self.assertEqual(len(d["metrics"]), 1)
        self.assertEqual(d["metrics"][0]["label"], "L2")
        self.assertTrue(d["urgent_queue"])
        self.assertTrue(d["next_actions"])
        self.assertTrue(d["activity"])

    def test_empty_next_actions_strict_fallback(self):
        """Strict single-action surfaces always expose one next step (destinations or copy)."""
        d = build_backend_dashboard_phase7_de(
            role_home={
                "eyebrow": "X",
                "main_action": "Use workflow links",
            },
            kpi_strip_cards=[],
            dashboard_priority_queue=[],
            dashboard_next_best_actions=[],
            role_home_primary_action=None,
            role_home_supporting_actions=[],
            dashboard_recent_activity=[],
            max_next_actions=1,
            role_home_destinations=[{"label": "Workflow", "url": "/w/", "id": "wf"}],
        )
        self.assertEqual(len(d["next_actions"]), 1)
        self.assertEqual(d["next_actions"][0]["label"], "Workflow")
        self.assertEqual(d["next_actions"][0]["url"], "/w/")

    def test_empty_next_actions_main_action_fallback(self):
        d = build_backend_dashboard_phase7_de(
            role_home={"eyebrow": "X", "main_action": "Ship work"},
            kpi_strip_cards=[],
            dashboard_priority_queue=[],
            dashboard_next_best_actions=[],
            role_home_primary_action=None,
            role_home_supporting_actions=[],
            dashboard_recent_activity=[],
            max_next_actions=1,
            role_home_destinations=[],
        )
        self.assertEqual(d["next_actions"][0]["label"], "Ship work")

    def test_build_role_home_declaration_defaults(self):
        decl = build_role_home_declaration({})
        self.assertEqual(decl["dashboard_type"], "operational")

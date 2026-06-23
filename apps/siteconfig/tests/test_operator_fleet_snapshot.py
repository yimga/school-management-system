"""Tests for operator fleet snapshot + context LLM default."""
from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.siteconfig.fleet_context_service import build_fleet_context, should_use_llm_brief
from apps.siteconfig.operator_fleet_snapshot import (
    bump_operator_fleet_revision,
    rules_fleet_brief,
    rules_whisper_line,
)


class OperatorFleetSnapshotTests(TestCase):
    def test_rules_whisper_suspended(self):
        line = rules_whisper_line(schools_live=10, suspended=2, frozen=0)
        self.assertIn("2", line)

    def test_rules_fleet_brief_shape(self):
        brief = rules_fleet_brief(
            schools_live=5,
            suspended=1,
            frozen=0,
            pulse_events=[{"text": "School now live · West Africa"}],
        )
        self.assertIn("headline", brief)
        self.assertIn("body", brief)
        self.assertIn("5", brief["headline"])

    @patch("apps.siteconfig.operator_fleet_snapshot.fetch_fleet_pulse_events", return_value=[])
    @patch("apps.schools.fleet_live_payload.build_fleet_live_payload")
    def test_build_snapshot_keys(self, mock_fleet, _mock_pulse):
        from apps.siteconfig.operator_fleet_snapshot import build_operator_fleet_snapshot

        mock_fleet.return_value = {"summary": {"live": 3}, "summary_label": "3 live"}
        snap = build_operator_fleet_snapshot()
        self.assertIn("operator_fleet_revision", snap)
        self.assertIn("pulse_events", snap)
        self.assertIn("whisper_line", snap)
        self.assertIn("fleet_brief", snap)
        self.assertIn("features", snap)

    def test_should_use_llm_brief_opt_out(self):
        factory = RequestFactory()
        req = factory.get("/super/api/operator/fleet/context/", {"llm": "0"})
        self.assertFalse(should_use_llm_brief(req))

    @patch("apps.portal.ai_provider.probe_ai_provider_reachable", return_value={"reachable": True})
    def test_should_use_llm_brief_default_on(self, _mock_probe):
        factory = RequestFactory()
        req = factory.get("/super/api/operator/fleet/context/")
        self.assertTrue(should_use_llm_brief(req))

    def test_bump_revision_changes(self):
        a = bump_operator_fleet_revision()
        b = bump_operator_fleet_revision()
        self.assertNotEqual(a, b)


class OperatorFleetApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(
            username="fleet_admin",
            email="fleet@example.com",
            password="Test1234!",
        )
        self.client = Client()
        self.client.force_login(self.user)

    @patch("apps.siteconfig.views_operator_fleet_api.build_operator_fleet_snapshot")
    def test_snapshot_api(self, mock_snap):
        mock_snap.return_value = {"schools_live": 1, "pulse_events": []}
        url = reverse("super:api_operator_fleet_snapshot")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["schools_live"], 1)

    @patch("apps.siteconfig.fleet_context_service.build_operator_fleet_snapshot")
    def test_context_api(self, mock_snap):
        mock_snap.return_value = {
            "schools_live": 2,
            "suspended": 0,
            "frozen": 0,
            "pulse_events": [],
            "fleet_brief": {"headline": "ok", "body": "ok"},
            "operator_fleet_revision": "abc",
            "globe_revision": "def",
            "fleet_summary": {},
            "summary_label": "",
            "school_hours_regions": 0,
            "aurora": "good",
        }
        url = reverse("super:api_operator_fleet_context")
        resp = self.client.get(url, {"region": "West Africa", "pins_in_view": "3"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["lens"], "operator-dashboard-fleet")
        self.assertIn("whisper_line", data)
        self.assertIn("brief_source", data)

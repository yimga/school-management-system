"""Tenant role-home parity (batch 1484 — teacher/backend hero + legacy gates)."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from apps.portal.tenant_role_home import (
    build_tp_hero_context,
    role_home_show_legacy,
    tp_hero_ai_tier_line,
)

ROOT = Path(__file__).resolve().parents[3]


class TenantRoleHomeHelperTests(SimpleTestCase):
    def test_legacy_flag_simple_query(self):
        class _Req:
            GET = {"simple": "1"}

        self.assertTrue(role_home_show_legacy(_Req()))

    def test_ai_tier_line_has_no_urls(self):
        line = tp_hero_ai_tier_line()
        self.assertIn("Assist tier:", line)
        self.assertNotIn("http", line.lower())
        self.assertNotIn("@", line)

    def test_build_tp_hero_context_keys(self):
        class _Req:
            GET = {}

        ctx = build_tp_hero_context(_Req(), role="TEACHER")
        self.assertEqual(ctx["tp_greeting_role"], "TEACHER")
        self.assertIn("portal_quick_actions", ctx)
        self.assertIn("tp_hero_ai_tier_line", ctx)


class TenantRoleHomeTemplateTests(SimpleTestCase):
    def test_teacher_dashboard_has_hero_and_legacy_gate(self):
        text = (ROOT / "templates/teacher/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("hero_greeting.html", text)
        self.assertIn("teacher_show_legacy_dashboard", text)
        self.assertIn("tdm-bg", text)
        gate_idx = text.find("teacher_show_legacy_dashboard")
        legacy_idx = text.find('class="tdm-bg"')
        self.assertGreater(legacy_idx, 0)
        self.assertGreater(gate_idx, 0)
        self.assertLess(gate_idx, legacy_idx)

    def test_backend_dashboard_has_hero_and_legacy_gate(self):
        text = (ROOT / "templates/accounts/backend_dashboard.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("hero_greeting.html", text)
        self.assertIn("backend_show_legacy_dashboard", text)
        gate_idx = text.find("backend_show_legacy_dashboard")
        legacy_idx = text.find("backend-dashboard-content")
        self.assertGreater(legacy_idx, 0)
        self.assertGreater(gate_idx, 0)
        self.assertLess(gate_idx, legacy_idx)

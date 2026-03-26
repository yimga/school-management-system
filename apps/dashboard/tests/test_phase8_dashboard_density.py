"""Phase 8: high-card dashboards must fold secondary density (collapsible contract)."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from apps.dashboard.dashboard_density_check import assert_dashboard_density_ok


class Phase8DashboardDensityTests(SimpleTestCase):
    def test_phase7_registry_passes_density_gate(self) -> None:
        root = Path(__file__).resolve().parents[3] / "templates"
        assert_dashboard_density_ok(templates_root=root)

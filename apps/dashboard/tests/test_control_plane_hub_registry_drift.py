from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from apps.dashboard.control_plane_hub_scan import (
    EXEMPT_CONTROL_PLANE_TEMPLATES,
    TEMPLATES_DIR,
    assert_control_plane_hub_registry_closed,
)

from apps.dashboard.phase7_dashboard_templates import PHASE7_DASHBOARD_TEMPLATES


class ControlPlaneHubRegistryDriftTests(SimpleTestCase):
    def test_no_unlisted_control_plane_templates(self) -> None:
        assert_control_plane_hub_registry_closed()

    def test_exempt_paths_exist(self) -> None:
        root = Path(TEMPLATES_DIR)
        for rel in sorted(EXEMPT_CONTROL_PLANE_TEMPLATES):
            with self.subTest(path=rel):
                self.assertTrue(
                    (root / rel).is_file(),
                    msg=f"EXEMPT path missing on disk: {rel}",
                )

    def test_exempt_disjoint_from_phase7(self) -> None:
        overlap = EXEMPT_CONTROL_PLANE_TEMPLATES & frozenset(PHASE7_DASHBOARD_TEMPLATES)
        self.assertFalse(overlap, msg=f"EXEMPT ∩ PHASE7 must be empty: {sorted(overlap)}")

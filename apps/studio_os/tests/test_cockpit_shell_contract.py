"""Studio OS shell layout contract.

The old additive Mission Cockpit chrome is retired in the active shell because
it created an empty first viewport before the real Studio workbench. Static
checks keep the historical partials present while asserting the active shell
uses the single-workspace contract.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[3]
SHELL_PATH = REPO_ROOT / "templates" / "studio_os" / "shell.html"
PARTIALS_DIR = REPO_ROOT / "templates" / "studio_os" / "partials"


class CockpitShellContractTests(SimpleTestCase):
    """Static-only contract checks on shell.html + retired cockpit partials."""

    def setUp(self) -> None:
        self.assertTrue(
            SHELL_PATH.exists(), f"missing studio_os shell template: {SHELL_PATH}"
        )
        self.shell_text = SHELL_PATH.read_text(encoding="utf-8")

    def test_shell_keeps_retired_cockpit_markup_unreachable(self) -> None:
        self.assertIn("rmc-cockpit", self.shell_text)
        self.assertIn("{% if False %}", self.shell_text)
        self.assertNotIn(
            "studio-os-cockpit.css",
            self.shell_text,
            "the retired cockpit stylesheet must not load in the active shell",
        )

    def test_historical_cockpit_partials_still_exist(self) -> None:
        expected = {
            "cockpit_signal_strip.html": "rmc-cockpit__signal",
            "cockpit_canvas.html": "rmc-cockpit__canvas",
            "cockpit_copilot_rail.html": "rmc-cockpit__rail",
        }
        for filename, marker in expected.items():
            path = PARTIALS_DIR / filename
            self.assertTrue(path.exists(), f"missing partial: {path}")
            self.assertIn(marker, path.read_text(encoding="utf-8"))

    def test_shell_uses_single_workspace_grid(self) -> None:
        self.assertIn(
            'studio-os{% if current_mode %} studio-os--mode-owned',
            self.shell_text,
            "mode pages must be marked as mode-owned so the duplicate shell rail hides",
        )
        self.assertIn("{% block studio_canvas %}", self.shell_text)
        self.assertIn("{% endblock %}", self.shell_text)

    def test_mode_template_inherits_cleanly(self) -> None:
        modes_dir = REPO_ROOT / "templates" / "studio_os" / "modes"
        for mode_file in (
            "experience.html",
            "automation.html",
            "output.html",
            "launch.html",
            "control.html",
        ):
            path = modes_dir / mode_file
            self.assertTrue(path.exists(), f"missing mode template: {path}")
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                "studio_os/shell.html",
                text,
                f"{mode_file} must extend studio_os/shell.html",
            )

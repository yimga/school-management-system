"""Studio OS Mission Cockpit shell contract (v3.53.0, 2026-05-21).

Asserts the cockpit chrome lands in templates/studio_os/shell.html
alongside the legacy studio-os grid, and that the 3 cockpit partials
referenced from the shell exist on disk.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[3]
SHELL_PATH = REPO_ROOT / "templates" / "studio_os" / "shell.html"
PARTIALS_DIR = REPO_ROOT / "templates" / "studio_os" / "partials"


class CockpitShellContractTests(SimpleTestCase):
    """Static-only contract checks on shell.html + cockpit partials."""

    def setUp(self) -> None:
        self.assertTrue(
            SHELL_PATH.exists(), f"missing studio_os shell template: {SHELL_PATH}"
        )
        self.shell_text = SHELL_PATH.read_text(encoding="utf-8")

    def test_shell_includes_signal_strip_partial(self) -> None:
        self.assertIn(
            'studio_os/partials/cockpit_signal_strip.html',
            self.shell_text,
            "shell.html must include the cockpit signal strip partial",
        )

    def test_shell_includes_canvas_partial(self) -> None:
        self.assertIn(
            'studio_os/partials/cockpit_canvas.html',
            self.shell_text,
            "shell.html must include the cockpit canvas partial",
        )

    def test_shell_includes_copilot_rail_partial(self) -> None:
        self.assertIn(
            'studio_os/partials/cockpit_copilot_rail.html',
            self.shell_text,
            "shell.html must include the cockpit co-pilot rail partial",
        )

    def test_shell_loads_cockpit_stylesheet(self) -> None:
        self.assertIn(
            'studio-os-cockpit.css', self.shell_text,
            "shell.html must load the cockpit stylesheet",
        )

    def test_shell_uses_cockpit_grid_class(self) -> None:
        self.assertIn(
            'rmc-cockpit', self.shell_text,
            "shell.html must instantiate the .rmc-cockpit grid",
        )

    def test_signal_strip_partial_exists(self) -> None:
        path = PARTIALS_DIR / "cockpit_signal_strip.html"
        self.assertTrue(path.exists(), f"missing partial: {path}")
        text = path.read_text(encoding="utf-8")
        self.assertIn("rmc-cockpit__signal", text)

    def test_canvas_partial_exists(self) -> None:
        path = PARTIALS_DIR / "cockpit_canvas.html"
        self.assertTrue(path.exists(), f"missing partial: {path}")
        text = path.read_text(encoding="utf-8")
        self.assertIn("rmc-cockpit__canvas", text)

    def test_copilot_rail_partial_exists(self) -> None:
        path = PARTIALS_DIR / "cockpit_copilot_rail.html"
        self.assertTrue(path.exists(), f"missing partial: {path}")
        text = path.read_text(encoding="utf-8")
        self.assertIn("rmc-cockpit__rail", text)

    def test_shell_preserves_legacy_studio_os_grid(self) -> None:
        """Cockpit chrome must be ADDITIVE — legacy .studio-os grid still present."""
        self.assertIn(
            '<div class="studio-os">', self.shell_text,
            "shell.html must keep the legacy .studio-os grid for backward-compat",
        )

    def test_shell_preserves_studio_canvas_block(self) -> None:
        """{% block studio_canvas %} must remain so mode templates inherit cleanly."""
        self.assertIn("{% block studio_canvas %}", self.shell_text)
        self.assertIn("{% endblock %}", self.shell_text)

    def test_mode_template_inherits_cleanly(self) -> None:
        """Each mode template still extends shell.html for the canvas block."""
        modes_dir = REPO_ROOT / "templates" / "studio_os" / "modes"
        for mode_file in ("experience.html", "automation.html", "output.html", "launch.html", "control.html"):
            path = modes_dir / mode_file
            self.assertTrue(path.exists(), f"missing mode template: {path}")
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                'studio_os/shell.html', text,
                f"{mode_file} must extend studio_os/shell.html",
            )

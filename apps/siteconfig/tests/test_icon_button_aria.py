"""Icon-only controls must carry an accessible name (a11y wave, 2026-06-22).

Runs scripts/scan_icon_button_aria.py inside the test suite so the zero-tolerance
gate is enforced on every CI run (not only via the architectural-boundaries
workflow). An icon-only <button>/<a> with no aria-label/title is invisible to
screen readers (WCAG 4.1.2).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from django.test import SimpleTestCase

REPO = Path(__file__).resolve().parents[3]
SCANNER = REPO / "scripts" / "scan_icon_button_aria.py"


def _load_scanner():
    spec = importlib.util.spec_from_file_location("scan_icon_button_aria", SCANNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class IconButtonAriaTests(SimpleTestCase):
    def test_no_icon_only_controls_without_accessible_name(self) -> None:
        mod = _load_scanner()
        findings = mod.collect()
        self.assertEqual(
            findings, [],
            "Icon-only <button>/<a> without an accessible name (add aria-label/"
            "title, or an <!-- icon-aria-allow: reason --> marker):\n  "
            + "\n  ".join(findings),
        )

    def test_fixed_controls_now_labelled(self) -> None:
        # spot-check the controls fixed in this wave carry a label
        checks = {
            "templates/components/ai_copilot.html": ['id="aiCopilotClose" aria-label=', 'id="aiCopilotSend" disabled aria-label='],
            "templates/schools/custom_domain_wizard.html": ["copy-txt", "aria-label="],
            "templates/communication/group_list.html": ["bi-chat-dots", "aria-label="],
        }
        for rel, needles in checks.items():
            src = (REPO / rel).read_text(encoding="utf-8")
            for needle in needles:
                with self.subTest(template=rel, needle=needle):
                    self.assertIn(needle, src)

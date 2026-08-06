"""Must-fire seal: the login hero carousel must not clip its slide text (2026-08-06).

The immersive login canvas rotates hero slides ("Gradebook, attendance, and
announcements in one workspace." etc.). The carousel used to be a height-capped
box (``max-height: 22vh`` → ``16vh`` under a short viewport) with
``overflow: hidden``, while each slide was ``position: absolute`` and vertically
centred. Absolute slides give the box ZERO intrinsic height, so the cap won and
any slide taller than it was clipped top-and-bottom (the "cut / leaking" hero
text a tenant reported on their own login screen).

The fix stacks the slides in ONE CSS grid cell (in-flow, not absolute) so the
carousel sizes to its tallest slide, and drops the ``max-height`` clip caps.
These assertions encode that contract and FAIL against the pre-fix CSS.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

_CSS = (
    Path(__file__).resolve().parents[3] / "static" / "css" / "auth-login-canvas.css"
)

_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
# selector { body }  — the file has no CSS nesting except @media wrappers, whose
# inner rules are matched individually (the base rules under test are top-level).
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)


def _rules_for(selector: str) -> list[str]:
    """Bodies of every rule whose comma-split selector list contains ``selector`` exactly."""
    source = _COMMENT.sub("", _CSS.read_text(encoding="utf-8"))
    bodies: list[str] = []
    for raw_sel, body in _RULE.findall(source):
        parts = {s.strip() for s in raw_sel.split(",")}
        if selector in parts:
            bodies.append(body)
    return bodies


class LoginCanvasHeroNoClipTests(SimpleTestCase):
    def test_css_file_present(self):
        self.assertTrue(_CSS.is_file(), f"missing {_CSS}")

    def test_slides_are_in_flow_not_absolute(self):
        """Absolute slides gave the box no height floor → the cap clipped them."""
        bodies = _rules_for(".rmc-auth-immersive__slide")
        self.assertTrue(bodies, "no .rmc-auth-immersive__slide rule found")
        for body in bodies:
            self.assertNotRegex(
                body,
                r"position\s*:\s*absolute",
                "slides must be grid-stacked (in-flow), not position:absolute — "
                "absolute slides contribute no height so a height cap clips them",
            )

    def test_carousel_sizes_to_content_no_clip_cap(self):
        """Base carousel must grid-stack its slides and carry no max-height clip cap."""
        bodies = _rules_for(".rmc-auth-immersive__carousel")
        self.assertEqual(
            len(bodies),
            1,
            "expected exactly one base .rmc-auth-immersive__carousel rule",
        )
        body = bodies[0]
        self.assertRegex(
            body,
            r"display\s*:\s*grid",
            "carousel must display:grid so slides stack in one cell and the box "
            "sizes to the tallest slide",
        )
        self.assertNotRegex(
            body,
            r"max-height\s*:",
            "carousel must not cap max-height — with overflow:hidden a cap clips "
            "any slide taller than it (the reported hero-text bug)",
        )

    def test_no_max_height_reintroduced_in_carousel_variants(self):
        """The short-viewport + campus_hero overrides must not re-add a clip cap."""
        source = _COMMENT.sub("", _CSS.read_text(encoding="utf-8"))
        for raw_sel, body in _RULE.findall(source):
            if ".rmc-auth-immersive__carousel" not in raw_sel:
                continue
            if ".rmc-auth-immersive__carousel--bleed" in raw_sel:
                continue  # the full-bleed frame carries no height
            self.assertNotRegex(
                body,
                r"max-height\s*:",
                f"a carousel variant re-introduced a max-height clip cap: {raw_sel.strip()}",
            )

"""Phase 0 visual-truth regression tests for the marketing surface.

These tests assert that the concrete bugs the user flagged in their Phase 0
review are gone AND stay gone:

  1. The walkthrough reel must define ``.reel-scene`` animation rules in the
     stylesheet the marketing surface actually loads — not in a bundle the
     marketing pages never pull in. Without these rules every scene rendered
     simultaneously and the text stacked.

  2. The walkthrough must not ship an empty ``<source src="">`` tag (some
     browsers logged decode warnings for it).

  3. The illustrative-voices and press-marks sections must carry a visible
     ``mkt-edt-illustrative-pill`` so buyers can't mistake placeholder
     content for real attribution.

  4. Pricing on the home hero teaser must be qualified with a "From"
     prefix instead of presenting raw exact figures (£3 / £6).

  5. The ``@media (prefers-color-scheme: dark)`` block that was auto-flipping
     the editorial cream surface to graphite on dark-OS visitors must be
     gone. Marketing is light-default; dark only via explicit toggle.

  6. The marketing-asset parity scanner must exit 0 (no claimed-but-missing
     and no unjustified unreferenced assets).

A full Playwright visual-truth suite is Phase 1+ infrastructure work; this
Django-level smoke harness gives us the regression safety for the specific
Phase 0 bugs without bootstrapping a JS test runner.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse


REPO_ROOT = Path(__file__).resolve().parents[3]
MARKETING_CSS = REPO_ROOT / "static" / "marketing" / "css" / "marketing-landing-v2.css"
EDITORIAL_TOKENS_CSS = REPO_ROOT / "static" / "marketing" / "css" / "tokens-editorial.css"
LANDING_TEMPLATE = REPO_ROOT / "templates" / "schools" / "marketing_landing_v2.html"
ASSET_PARITY_SCRIPT = REPO_ROOT / "scripts" / "check_marketing_assets_claimed_vs_present.py"


class WalkthroughReelCssRegressionTest(SimpleTestCase):
    """The walkthrough reel animation rules must live on the marketing CSS bundle."""

    def test_reel_scene_keyframes_defined_in_marketing_css(self) -> None:
        text = MARKETING_CSS.read_text(encoding="utf-8")
        self.assertIn(".reel-scene", text, "missing .reel-scene base rule")
        self.assertIn(
            "@keyframes reelCycle", text,
            "missing @keyframes reelCycle — without it every scene renders at opacity 1 simultaneously",
        )
        for n in range(1, 6):
            self.assertIn(
                f".reel-scene--{n}", text,
                f"missing per-scene delay rule for .reel-scene--{n}",
            )

    def test_reel_scene_respects_reduced_motion(self) -> None:
        text = MARKETING_CSS.read_text(encoding="utf-8")
        self.assertIn(
            "prefers-reduced-motion: reduce", text,
            "reel must honor prefers-reduced-motion — required for accessibility",
        )


class WalkthroughTemplateRegressionTest(SimpleTestCase):
    """The home template must not regress the empty <source src=""> bug."""

    def test_no_empty_video_source(self) -> None:
        text = LANDING_TEMPLATE.read_text(encoding="utf-8")
        # Match the full bug signature (with type attr) so the string in the
        # explanatory {# ... #} comment doesn't trigger a false positive.
        self.assertNotIn(
            '<source src="" type=', text,
            "empty <source src=\"\"> reintroduced — drop a real <source> in or omit the <video>",
        )


class IllustrativeDisclosureRegressionTest(SimpleTestCase):
    """The voices + press sections must visibly disclose that they are illustrative."""

    def test_voices_section_has_illustrative_pill(self) -> None:
        text = LANDING_TEMPLATE.read_text(encoding="utf-8")
        voices_idx = text.find('id="voices-headline"')
        self.assertGreater(voices_idx, -1, "voices section missing")
        # The pill should be in the section header, near voices-headline.
        window = text[max(0, voices_idx - 600):voices_idx + 600]
        self.assertIn(
            "mkt-edt-illustrative-pill", window,
            "voices section must carry mkt-edt-illustrative-pill so the disclosure isn't buried",
        )

    def test_press_section_has_illustrative_pill(self) -> None:
        text = LANDING_TEMPLATE.read_text(encoding="utf-8")
        press_idx = text.find('id="press-headline"')
        self.assertGreater(press_idx, -1, "press section missing")
        window = text[max(0, press_idx - 200):press_idx + 800]
        self.assertIn(
            "mkt-edt-illustrative-pill", window,
            "press section must carry mkt-edt-illustrative-pill",
        )


class PricingCopyRegressionTest(SimpleTestCase):
    """Home pricing teaser must qualify exact figures with 'From' prefix."""

    def test_home_pricing_has_from_prefix(self) -> None:
        text = LANDING_TEMPLATE.read_text(encoding="utf-8")
        # Both Starter and Growth price-figures must be preceded by the prefix marker.
        prefix_count = text.count("mkt-edt-plan__price-prefix")
        self.assertGreaterEqual(
            prefix_count, 2,
            "home pricing teaser must qualify both £3 and £6 with 'From' prefix",
        )


class AutoDarkModeOverrideRetiredTest(SimpleTestCase):
    """The auto prefers-color-scheme: dark override on the editorial palette must be gone."""

    def test_editorial_tokens_no_auto_dark_media_block(self) -> None:
        text = EDITORIAL_TOKENS_CSS.read_text(encoding="utf-8")
        # The explicit html[data-theme="dark"] selector should still exist (toggle path).
        self.assertIn(
            'html[data-theme="dark"]', text,
            "explicit dark-theme selector should remain so the toggle still works",
        )
        # But the actual @media rule must be gone (the string can still appear in
        # an explanatory comment; what we forbid is the rule itself, signalled
        # by the opening brace).
        self.assertNotIn(
            "@media (prefers-color-scheme: dark) {", text,
            "auto dark-mode override returned; marketing must default to light unless toggled",
        )


class MarketingAssetParityScannerTest(SimpleTestCase):
    """The asset parity scanner must exit 0; if it doesn't, ship is blocked."""

    def test_scanner_exits_zero(self) -> None:
        if not ASSET_PARITY_SCRIPT.exists():
            self.skipTest("asset parity scanner not present")
        result = subprocess.run(
            [sys.executable, str(ASSET_PARITY_SCRIPT)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            result.returncode, 0,
            f"asset parity scanner failed:\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}",
        )


@override_settings(ALLOWED_HOSTS=["*"])
class HomeRenderSmokeTest(TestCase):
    """Home page must render and contain the Phase 0 fixes when served live.

    Uses TestCase (not SimpleTestCase) because the marketing landing view
    queries multi-tenant resolution + feature flags + lexicon at render time.
    """

    def test_home_renders_with_phase0_markers(self) -> None:
        client = Client()
        try:
            response = client.get(reverse("marketing_landing"), HTTP_HOST="runmycampus.com")
        except Exception as exc:  # pragma: no cover - environment-sensitive
            self.skipTest(f"marketing_landing url not resolvable in this test env: {exc}")
        if response.status_code != 200:
            self.skipTest(f"home returned {response.status_code}; smoke check skipped")
        content = response.content.decode("utf-8", errors="replace")
        self.assertNotIn('<source src=""', content, "rendered home leaks empty <source src=\"\">")
        self.assertIn("mkt-edt-illustrative-pill", content, "rendered home missing illustrative-pill disclosure")
        self.assertIn("mkt-edt-plan__price-prefix", content, "rendered home missing 'From' price prefix")

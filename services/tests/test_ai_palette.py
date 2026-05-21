"""Tests for services.ai_palette — Intelligent palette system (batch 1371, P1)."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from services.ai_palette import (
    PALETTE_TONES,
    STOP_KEYS,
    PaletteResult,
    generate_palette_from_seed,
)
from services.theme_intelligence import wcag_contrast_ratio


class GeneratePaletteRulesFallbackTests(SimpleTestCase):
    """Rules-fallback path: AI unavailable → deterministic palette."""

    def test_returns_palette_result_with_11_stops(self):
        with patch(
            "services.ai_palette.invoke_with_request", return_value=None
        ):
            result = generate_palette_from_seed("#4F46E5")
        self.assertIsInstance(result, PaletteResult)
        self.assertEqual(set(result.stops.keys()), set(STOP_KEYS))
        for hex_value in result.stops.values():
            self.assertRegex(hex_value, r"^#[0-9A-F]{6}$")

    def test_surface_and_text_chains_present(self):
        with patch(
            "services.ai_palette.invoke_with_request", return_value=None
        ):
            result = generate_palette_from_seed("#4F46E5")
        self.assertEqual(
            set(result.surface_chain.keys()),
            {"bg", "canvas", "elevated", "popover"},
        )
        self.assertEqual(
            set(result.text_chain.keys()),
            {"primary", "secondary", "tertiary", "muted"},
        )

    def test_source_is_rules_when_ai_returns_none(self):
        with override_settings(AI_ALLOW_RULES_FALLBACK=True), patch(
            "services.ai_palette.invoke_with_request", return_value=None
        ):
            result = generate_palette_from_seed("#4F46E5")
        self.assertEqual(result.source, "rules")

    def test_source_is_fallback_when_rules_disabled(self):
        with override_settings(AI_ALLOW_RULES_FALLBACK=False), patch(
            "services.ai_palette.invoke_with_request", return_value=None
        ):
            result = generate_palette_from_seed("#4F46E5")
        self.assertEqual(result.source, "fallback")
        # We still return a usable palette.
        self.assertEqual(set(result.stops.keys()), set(STOP_KEYS))

    def test_dual_mode_returns_dark_chains(self):
        with patch(
            "services.ai_palette.invoke_with_request", return_value=None
        ):
            result = generate_palette_from_seed("#0EA5E9", mode="dual")
        self.assertEqual(set(result.dark_stops.keys()), set(STOP_KEYS))
        self.assertEqual(
            set(result.dark_surface_chain.keys()),
            {"bg", "canvas", "elevated", "popover"},
        )
        # Dark bg should be darker than light bg.
        self.assertLess(
            _luminance(result.dark_surface_chain["bg"]),
            _luminance(result.surface_chain["bg"]),
        )

    def test_light_only_mode_omits_dark(self):
        with patch(
            "services.ai_palette.invoke_with_request", return_value=None
        ):
            result = generate_palette_from_seed("#0EA5E9", mode="light")
        self.assertEqual(result.dark_stops, {})
        self.assertEqual(result.dark_surface_chain, {})

    def test_invalid_seed_does_not_raise(self):
        with patch(
            "services.ai_palette.invoke_with_request", return_value=None
        ):
            result = generate_palette_from_seed("not-a-color")
        self.assertIsInstance(result, PaletteResult)
        # Should fall back to indigo.
        self.assertEqual(set(result.stops.keys()), set(STOP_KEYS))


class WcagSnapCorrectnessTests(SimpleTestCase):
    """Manufactured low-contrast stops → snapped to compliant lightness."""

    def test_500_on_50_reaches_aa_after_snap(self):
        # The rules ramp produces stops that should clear 4.5:1 from
        # stop-50 to stop-500 (canonical text-on-canvas pair).
        with patch(
            "services.ai_palette.invoke_with_request", return_value=None
        ):
            result = generate_palette_from_seed("#4F46E5")
        ratio = wcag_contrast_ratio(result.stops["500"], result.stops["50"])
        self.assertGreaterEqual(ratio, 4.5)

    def test_900_on_50_reaches_strong_contrast(self):
        with patch(
            "services.ai_palette.invoke_with_request", return_value=None
        ):
            result = generate_palette_from_seed("#4F46E5")
        ratio = wcag_contrast_ratio(result.stops["900"], result.stops["50"])
        self.assertGreaterEqual(ratio, 6.0)

    def test_cloud_low_contrast_is_snapped(self):
        # Manufactured cloud response with deliberately low-contrast 500.
        bad_payload = (
            '{"stops":{'
            '"50":"#FFFFFF","100":"#FFFFFF","200":"#EEEEEE","300":"#DDDDDD",'
            '"400":"#CCCCCC","500":"#BBBBBB","600":"#AAAAAA","700":"#888888",'
            '"800":"#444444","900":"#222222","950":"#000000"'
            '},"surface_chain":{"bg":"#FFFFFF","canvas":"#FAFAFA","elevated":"#FFFFFF","popover":"#FFFFFF"},'
            '"text_chain":{"primary":"#111111","secondary":"#333333","tertiary":"#555555","muted":"#777777"},'
            '"accent_hex":"#4F46E5","reasoning_summary":"test"}'
        )
        with patch(
            "services.ai_palette.invoke_with_request",
            return_value=(bad_payload, {}),
        ), patch(
            "services.ai_palette._rules_fallback_allowed", return_value=True
        ):
            result = generate_palette_from_seed("#4F46E5")
        # Even with low-contrast cloud input, the snap should push 500-on-50 to AA.
        ratio = wcag_contrast_ratio(result.stops["500"], result.stops["50"])
        self.assertGreaterEqual(ratio, 4.5)


class CloudSourceAttributionTests(SimpleTestCase):
    """The ``source`` field correctly attributes cloud vs rules."""

    def test_cloud_source_when_gateway_returns_payload(self):
        good_payload = (
            '{"stops":{'
            '"50":"#F5F4FF","100":"#E0DCFF","200":"#C2BAFF","300":"#9F95FF",'
            '"400":"#7B6CFF","500":"#4F46E5","600":"#3F38B7","700":"#2F2A89",'
            '"800":"#1F1B5B","900":"#0F0D2D","950":"#070617"'
            '},"surface_chain":{"bg":"#F5F4FF","canvas":"#FFFFFF","elevated":"#FFFFFF","popover":"#F5F4FF"},'
            '"text_chain":{"primary":"#0F0D2D","secondary":"#2F2A89","tertiary":"#3F38B7","muted":"#4F46E5"},'
            '"accent_hex":"#4F46E5","reasoning_summary":"Indigo gradient."}'
        )
        with patch(
            "services.ai_palette.invoke_with_request",
            return_value=(good_payload, {}),
        ):
            result = generate_palette_from_seed("#4F46E5")
        self.assertEqual(result.source, "cloud")
        self.assertEqual(result.accent_hex, "#4F46E5")

    def test_cloud_unparseable_payload_marks_fallback(self):
        with patch(
            "services.ai_palette.invoke_with_request",
            return_value=("not json at all, sorry", {}),
        ), patch(
            "services.ai_palette._rules_fallback_allowed", return_value=True
        ):
            result = generate_palette_from_seed("#4F46E5")
        # Gateway answered but with garbage → fallback marker.
        self.assertEqual(result.source, "fallback")
        # Still a usable palette.
        self.assertEqual(set(result.stops.keys()), set(STOP_KEYS))

    def test_cloud_failure_does_not_raise(self):
        def raise_on_invoke(**_kwargs):
            raise RuntimeError("simulated gateway crash")

        with patch(
            "services.ai_palette.invoke_with_request",
            side_effect=raise_on_invoke,
        ), patch(
            "services.ai_palette._rules_fallback_allowed", return_value=True
        ):
            # Should NOT propagate the RuntimeError.
            result = generate_palette_from_seed("#4F46E5")
        self.assertEqual(result.source, "rules")


class ArchitecturalBoundaryTests(SimpleTestCase):
    """The ai_palette module must NEVER import services.ai_gateway directly."""

    def test_ai_palette_does_not_import_ai_gateway_directly(self):
        repo_root = Path(__file__).resolve().parents[2]
        module_path = repo_root / "services" / "ai_palette.py"
        source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "services.ai_gateway" or module.startswith(
                    "services.ai_gateway."
                ):
                    forbidden.append(f"from {module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "services.ai_gateway" or alias.name.startswith(
                        "services.ai_gateway."
                    ):
                        forbidden.append(f"import {alias.name}")
        self.assertEqual(
            forbidden,
            [],
            f"ai_palette.py must route via services.ai_helpers, found: {forbidden}",
        )


# ---------------------------------------------------------------------------
# Tone-aware overload (R4 ship list, batch 1372 residual closeout)
# ---------------------------------------------------------------------------


def _hex_to_hsl_for_tests(hex_value: str) -> tuple[float, float, float]:
    """Pure-function HSL converter that mirrors the module's math.

    Kept local to the test file so the assertion math doesn't import a
    private symbol from the module under test (which would let an
    accidental rename in the module fail loudly here, not silently).
    """
    v = hex_value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c + c for c in v)
    r, g, b = int(v[0:2], 16) / 255.0, int(v[2:4], 16) / 255.0, int(v[4:6], 16) / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2.0
    if mx == mn:
        return (0.0, 0.0, l)
    d = mx - mn
    s = d / (2.0 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = (g - b) / d + (6.0 if g < b else 0.0)
    elif mx == g:
        h = (b - r) / d + 2.0
    else:
        h = (r - g) / d + 4.0
    return (h * 60.0, s, l)


def _hue_distance_deg(a: float, b: float) -> float:
    """Shortest-arc hue distance in degrees, in [0, 180]."""
    delta = abs(a - b) % 360.0
    return min(delta, 360.0 - delta)


class ToneAwareOverloadTests(SimpleTestCase):
    """Tone parameter biases the palette toward classic/warm/vibrant/neutral."""

    SEED = "#4F46E5"  # RMC indigo (hue ~244 deg)

    def _rules_palette(self, tone):
        with patch(
            "services.ai_palette.invoke_with_request", return_value=None
        ):
            return generate_palette_from_seed(self.SEED, tone=tone)

    def test_tone_classic_returns_seed_proximate_palette(self):
        """Classic tone stays within ~15 deg of the seed hue at the anchor stop."""
        seed_hue, _, _ = _hex_to_hsl_for_tests(self.SEED)
        result = self._rules_palette("classic")
        # Hue at the anchor (500) should stay near the seed; the WCAG snap
        # only shifts lightness, so the hue invariant holds.
        h500, _, _ = _hex_to_hsl_for_tests(result.stops["500"])
        self.assertLessEqual(_hue_distance_deg(h500, seed_hue), 15.0)

    def test_tone_warm_shifts_hue_warmer(self):
        """Warm tone moves the hue meaningfully toward orange (30 deg)."""
        result_warm = self._rules_palette("warm")
        result_classic = self._rules_palette("classic")
        # Hue at the anchor stop diverges from the classic baseline.
        h_warm, _, _ = _hex_to_hsl_for_tests(result_warm.stops["500"])
        h_classic, _, _ = _hex_to_hsl_for_tests(result_classic.stops["500"])
        self.assertGreater(_hue_distance_deg(h_warm, h_classic), 10.0)
        # AND the warm anchor is closer to 30 deg (orange) than the classic
        # anchor is — proves direction, not just magnitude.
        self.assertLess(
            _hue_distance_deg(h_warm, 30.0),
            _hue_distance_deg(h_classic, 30.0),
        )

    def test_tone_vibrant_boosts_saturation(self):
        """Vibrant tone produces higher saturation at critical mid stops."""
        result_vibrant = self._rules_palette("vibrant")
        result_classic = self._rules_palette("classic")
        # Critical mid stops: 400 / 500 / 600. The WCAG snap may equalize
        # the very-light/very-dark ends, so we anchor on the mid band.
        sums_vibrant = sum(
            _hex_to_hsl_for_tests(result_vibrant.stops[k])[1]
            for k in ("400", "500", "600")
        )
        sums_classic = sum(
            _hex_to_hsl_for_tests(result_classic.stops[k])[1]
            for k in ("400", "500", "600")
        )
        self.assertGreaterEqual(sums_vibrant, sums_classic)

    def test_tone_neutral_desaturates(self):
        """Neutral tone collapses saturation in the mid band to a quiet level."""
        result_neutral = self._rules_palette("neutral")
        # Pre-snap target was sat=0.25; the snap may nudge lightness but
        # NOT saturation. Mid stops should sit well under 0.45 in HSL.
        for k in ("400", "500", "600"):
            _, sat, _ = _hex_to_hsl_for_tests(result_neutral.stops[k])
            self.assertLessEqual(sat, 0.45)

    def test_tone_propagates_to_palette_result_field(self):
        """The PaletteResult records what tone was requested."""
        for tone in PALETTE_TONES:
            with patch(
                "services.ai_palette.invoke_with_request", return_value=None
            ):
                result = generate_palette_from_seed(self.SEED, tone=tone)
            self.assertEqual(result.tone, tone)

    def test_tone_none_preserves_existing_behavior(self):
        """tone=None preserves the pre-tone contract — exact same output as no kwarg."""
        with patch(
            "services.ai_palette.invoke_with_request", return_value=None
        ):
            with_none = generate_palette_from_seed(self.SEED, tone=None)
            without = generate_palette_from_seed(self.SEED)
        # Both should have ``tone is None`` and identical 11-stop ramps.
        self.assertIsNone(with_none.tone)
        self.assertIsNone(without.tone)
        self.assertEqual(with_none.stops, without.stops)
        self.assertEqual(with_none.surface_chain, without.surface_chain)
        self.assertEqual(with_none.text_chain, without.text_chain)

    def test_tone_appears_in_ai_prompt(self):
        """When tone is set the prompt argument to the gateway includes the directive."""
        captured = {}

        def _capture(**kwargs):
            captured.update(kwargs)
            return None  # force rules fallback

        with patch(
            "services.ai_palette.invoke_with_request", side_effect=_capture
        ):
            generate_palette_from_seed(self.SEED, tone="warm")
        self.assertIn("prompt", captured)
        prompt_text = captured["prompt"]
        self.assertIsInstance(prompt_text, str)
        # The tone directive appears as a literal substring in the prompt.
        self.assertIn("warm", prompt_text.lower())
        # AND the metadata kwarg carries the tone for AI observability rollups.
        meta = captured.get("metadata") or {}
        self.assertEqual(meta.get("palette_tone"), "warm")

    def test_tone_rules_fallback_diversity(self):
        """Different tones produce hue-distinct rules palettes from the same seed."""
        palettes = {}
        for tone in ("classic", "warm", "vibrant"):
            with patch(
                "services.ai_palette.invoke_with_request", return_value=None
            ):
                palettes[tone] = generate_palette_from_seed(self.SEED, tone=tone)
        # Pairwise hue distance at the anchor stop > 10 deg between AT LEAST
        # one pair (warm clearly diverges; vibrant boosts saturation not hue,
        # so warm-vs-classic is the strongest signal — we still require
        # warm-vs-classic > 10 explicitly to prove tone routing is wired).
        hues = {
            tone: _hex_to_hsl_for_tests(p.stops["500"])[0]
            for tone, p in palettes.items()
        }
        self.assertGreater(_hue_distance_deg(hues["warm"], hues["classic"]), 10.0)
        # AND vibrant saturation > classic saturation at the anchor.
        sat_vibrant = _hex_to_hsl_for_tests(palettes["vibrant"].stops["500"])[1]
        sat_classic = _hex_to_hsl_for_tests(palettes["classic"].stops["500"])[1]
        self.assertGreaterEqual(sat_vibrant, sat_classic)


class ToneAwareWcagComplianceTests(SimpleTestCase):
    """Tone-shifted palettes still clear the WCAG 4.5:1 anchor pair."""

    def test_every_tone_passes_wcag_anchor(self):
        for tone in PALETTE_TONES:
            with patch(
                "services.ai_palette.invoke_with_request", return_value=None
            ):
                result = generate_palette_from_seed("#4F46E5", tone=tone)
            ratio = wcag_contrast_ratio(result.stops["500"], result.stops["50"])
            self.assertGreaterEqual(
                ratio,
                4.5,
                msg=f"tone={tone} 500-on-50 ratio={ratio:.2f} < 4.5",
            )


# ---------------------------------------------------------------------------
# Local helper (mirrors the math used in the module — kept simple)
# ---------------------------------------------------------------------------


def _luminance(hex_value: str) -> float:
    v = hex_value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c + c for c in v)
    r, g, b = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)

    def _ch(c: int) -> float:
        cs = c / 255.0
        return cs / 12.92 if cs <= 0.03928 else ((cs + 0.055) / 1.055) ** 2.4

    return 0.2126 * _ch(r) + 0.7152 * _ch(g) + 0.0722 * _ch(b)

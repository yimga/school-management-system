"""Must-fire seal: the 2026-08-08 legibility fixes stay AA-legible.

The platform-wide low-contrast wash-out (studio "Publish guardrail", App Catalog,
captions, empty-states, footer) came from token-tier + opacity-on-text failures
that the CSS-literal contrast scanner is blind to. This contract test computes the
actual WCAG-AA ratios for the fixed tokens and asserts each structural fix is in
place. Every assertion FAILS against the pre-fix CSS.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

_CSS = Path(__file__).resolve().parents[3] / "static" / "css"


def _lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _ratio(fg: str, bg: str) -> float:
    a, b = _luminance(fg), _luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _read(name: str) -> str:
    src = (_CSS / name).read_text(encoding="utf-8")
    return re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)  # strip comments


def _blocks(source: str):
    return re.findall(r"([^{}]+)\{([^{}]*)\}", source, re.DOTALL)


def _rule_body(source: str, selector_substr: str) -> str:
    """Body of the first block whose selector contains the substring."""
    for sel, body in _blocks(source):
        if selector_substr in sel:
            return body
    return ""


def _exact_rule(source: str, selector: str) -> str:
    """Body of the block whose selector is exactly `selector` (the base rule)."""
    for sel, body in _blocks(source):
        if sel.strip() == selector:
            return body
    return ""


def _rule_with(source: str, selector_substr: str, must_contain: str) -> str:
    """First block whose selector contains the substring AND body has `must_contain`."""
    for sel, body in _blocks(source):
        if selector_substr in sel and must_contain in body:
            return body
    return ""


def _token(body: str, token: str) -> str:
    m = re.search(re.escape(token) + r"\s*:\s*(#[0-9a-fA-F]{6})", body)
    return m.group(1) if m else ""


AA = 4.5


class WarmBrightTokenFloorAA(SimpleTestCase):
    """The platform-default aesthetic must not sink muted/tertiary below AA."""

    def setUp(self):
        self.src = _read("rmc-warm-bright-school.css")

    def test_warm_bright_muted_and_tertiary_are_AA(self):
        body = _rule_body(self.src, 'data-rmc-aesthetic="warm-bright"')
        tertiary = _token(body, "--text-tertiary")
        muted = _token(body, "--text-muted")
        self.assertTrue(tertiary and muted, "warm-bright text tokens not found")
        # lightest warm surface the tokens paint on
        for tok, name in ((tertiary, "tertiary"), (muted, "muted")):
            self.assertGreaterEqual(
                _ratio(tok, "#fffaf0"), AA,
                f"warm-bright --text-{name} {tok} fails AA on #fffaf0",
            )
        # regression guard: the exact failing values must not return
        self.assertNotEqual(muted.lower(), "#9a9082")
        self.assertNotEqual(tertiary.lower(), "#857c70")

    def test_cool_apple_muted_is_AA(self):
        body = _rule_body(self.src, 'data-rmc-aesthetic="cool-apple"')
        muted = _token(body, "--text-muted")
        self.assertTrue(muted, "cool-apple --text-muted not found")
        self.assertGreaterEqual(_ratio(muted, "#f8fafc"), AA,
                                f"cool-apple --text-muted {muted} fails AA")
        self.assertNotEqual(muted.lower(), "#94a3b8")  # slate-400 = 2.5:1


class AppCatalogLightInkScoped(SimpleTestCase):
    """Near-white catalog ink must be scoped to dark surfaces, not unconditional."""

    def test_base_wrap_does_not_pin_light_text(self):
        src = _read("marketplace-tenant-app-catalog.css")
        base = _exact_rule(src, ".tenant-app-catalog-wrap")
        self.assertTrue(base, "base .tenant-app-catalog-wrap rule not found")
        # the base rule must NOT set the light secondary/tertiary text tokens
        self.assertNotIn("--text-secondary: var(--color-base-200", base)
        self.assertNotIn("--text-tertiary: var(--color-base-300", base)
        # and the light ink must be re-applied under a dark scope somewhere
        self.assertTrue(
            re.search(r'\[data-theme="dark"\][^{]*tenant-app-catalog-wrap', src)
            or re.search(r'portal-backend-dark[^{]*tenant-app-catalog-wrap', src),
            "no dark-scoped catalog ink block found",
        )


class SharedGrammarLifted(SimpleTestCase):
    def test_caption_and_eyebrow_use_secondary_tier(self):
        src = _read("design-tokens.css")
        for cls in (".rmc-type-caption", ".rmc-type-eyebrow"):
            body = _rule_with(src, cls, "color:")  # the color rule, not the font rule
            self.assertIn("--text-secondary", body,
                          f"{cls} must use --text-secondary (was --text-tertiary)")

    def test_dashboard_empty_state_off_bs_secondary(self):
        body = _exact_rule(_read("dashboard-layout-unified.css"), ".dashboard-empty-state")
        self.assertNotIn("--bs-secondary", body)  # brand tint ~2.0:1
        self.assertIn("--text-secondary", body)

    def test_footer_legal_sep_has_no_opacity_on_text(self):
        src = _read("rmc-civic-footer.css")
        body = _rule_body(src, ".rmc-civic-footer__legal-sep")
        self.assertNotRegex(body, r"opacity\s*:", "opacity-on-text reintroduced")

    def test_command_eyebrow_has_color_fallback(self):
        body = _rule_body(_read("rmc-class-grammar.css"), ".rmc-command-eyebrow")
        self.assertRegex(body, r"var\(--text-secondary,\s*var\(--bs-secondary-color\)")


class BackToTopVariants(SimpleTestCase):
    def test_both_variant_skins_present(self):
        src = _read("rmc-back-to-top.css")
        self.assertIn(".rmc-back-to-top--aurora", src)
        self.assertIn(".rmc-back-to-top--mercury", src)


class Day1CtaAndAccentTokens(SimpleTestCase):
    """The Day-1 studio wizard must not paint controls with the UNDEFINED
    --accent-primary token. It silently fell through to --text-primary; the
    primary CTA then paired that against `color: var(--surface-bg)`, and on the
    dark studio canvas --text-primary flips near-white while --surface-bg stays
    light -> the reported white-on-white 'See three palette options' pill."""

    def setUp(self):
        self.src = _read("tenant-studio-day1.css")

    def test_primary_cta_uses_brand_on_brand_pair(self):
        body = _exact_rule(self.src, ".rmc-day1-cta-primary")
        self.assertTrue(body, "primary CTA rule not found")
        self.assertTrue(
            "--brand-gradient" in body or "--school-primary" in body,
            "primary CTA must fill with the brand token, not --accent-primary",
        )
        self.assertIn("--text-on-brand", body, "primary CTA text must be on-brand ink")
        self.assertNotIn("--accent-primary", body)
        # the old collapsing text token must be gone from this control
        self.assertNotIn("--surface-bg", body)

    def test_no_live_accent_primary_reference_remains(self):
        # _read strips /* */ comments, so a mention inside the fix note is fine;
        # any surviving hit here is a LIVE declaration on the undefined token.
        self.assertNotIn("--accent-primary", self.src)


class OnBrandInkTokensDeclared(SimpleTestCase):
    """--brand-accent-ink and --brand-on-primary were referenced platform-wide
    (workflow-progress chips, field-intelligence save-bar, portal-shell) but
    NEVER declared, so foreground text fell back to a surface token and went
    invisible-grade. They must now be declared and AA-legible on their fills."""

    def setUp(self):
        self.src = _read("design-tokens.css")

    def test_brand_accent_ink_declared_and_AA_on_emerald(self):
        ink = _token(self.src, "--brand-accent-ink")
        self.assertTrue(ink, "--brand-accent-ink is not declared")
        # It is the ink on --brand-accent (= --school-accent #10b981, a LIGHT
        # emerald), so it must be dark enough to clear AA. White-on-emerald ~2.5:1.
        self.assertGreaterEqual(
            _ratio(ink, "#10b981"), AA,
            f"--brand-accent-ink {ink} fails AA on the emerald accent #10b981",
        )

    def test_brand_on_primary_declared_and_tracks_on_brand(self):
        self.assertRegex(
            self.src, r"--brand-on-primary\s*:\s*var\(--text-on-brand",
            "--brand-on-primary must be declared and track --text-on-brand (white)",
        )
        # documents the pairing it protects: white on the indigo primary is AA
        self.assertGreaterEqual(_ratio("#ffffff", "#4f46e5"), AA)

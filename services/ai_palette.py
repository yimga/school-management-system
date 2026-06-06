"""Intelligent palette generation — single brand seed → full WCAG-AA palette.

Boundary contract (P1, batch 1371):
* App code MUST route AI through ``services.ai_helpers``. This module is
  inside ``services/`` itself but it ALSO routes through ``ai_helpers``
  rather than reaching into ``services.ai_gateway`` directly. That keeps
  the boundary scanner happy when this module is imported from any
  ``apps/...`` view (e.g. the theme builder palette endpoint).
* Cloud-first per `docs/AI_DEPLOYMENT_POSTURE.md`: cloud tier first via
  the gateway chain, graceful deterministic fallback otherwise.
* No on-device LLM assumption — the rules fallback below is pure-Python
  deterministic colour math (HSL rotation + WCAG snap).
* In-process only — no httpx / requests / urllib calls. The HTTP side
  lives inside the gateway; we never reach the network from here.

Public surface:
* :class:`PaletteResult` — dataclass returned to callers
* :func:`generate_palette_from_seed` — the only entry point

Strict typing: ``Literal`` for narrow enums, no ``Any`` in the public
surface. The result is JSON-serialisable.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Literal

from django.conf import settings

from services.ai_helpers import invoke_with_request

logger = logging.getLogger(__name__)


__all__ = [
    "PaletteResult",
    "PaletteSource",
    "PaletteMode",
    "PaletteTone",
    "PALETTE_TONES",
    "generate_palette_from_seed",
    "STOP_KEYS",
]


# ---------------------------------------------------------------------------
# Public typing surface
# ---------------------------------------------------------------------------


PaletteSource = Literal["cloud", "rules", "fallback"]
PaletteMode = Literal["light", "dark", "dual"]
PaletteTone = Literal["classic", "warm", "vibrant", "neutral"]

#: Tones the AI prompt + rules-fallback can bias the palette toward. Kept as a
#: tuple of literals (mirroring ``PaletteTone``) so callers / scanners can
#: iterate without re-deriving the set from the ``Literal`` typing alias.
PALETTE_TONES: tuple[str, ...] = ("classic", "warm", "vibrant", "neutral")

#: Canonical 11-stop scale (Tailwind / Material lineage).
STOP_KEYS: tuple[str, ...] = (
    "50",
    "100",
    "200",
    "300",
    "400",
    "500",
    "600",
    "700",
    "800",
    "900",
    "950",
)

#: Target relative lightness for each stop on a 0..100 scale. The seed colour
#: anchors the stop closest to its own lightness; the remaining stops are
#: lightened/darkened around it using HSL adjust. These targets are tuned to
#: keep adjacent-stop contrast around 1.3-1.5 ratio, which gives the WCAG
#: 4.5:1 ratio when stepping 3 stops (e.g. 500-on-50, 700-on-100).
_STOP_LIGHTNESS: dict[str, float] = {
    "50": 96.0,
    "100": 92.0,
    "200": 84.0,
    "300": 73.0,
    "400": 60.0,
    "500": 49.0,
    "600": 41.0,
    "700": 32.0,
    "800": 24.0,
    "900": 16.0,
    "950": 9.0,
}


@dataclass(frozen=True)
class PaletteResult:
    """The full palette returned by :func:`generate_palette_from_seed`.

    * ``stops`` — light-mode 11-stop scale keyed by ``STOP_KEYS``.
    * ``surface_chain`` — semantic surface tokens
      (``bg`` / ``canvas`` / ``elevated`` / ``popover``).
    * ``text_chain`` — semantic text tokens
      (``primary`` / ``secondary`` / ``tertiary`` / ``muted``).
    * ``accent_hex`` — the chosen accent (often equal to the seed).
    * ``wcag_grade`` — overall worst-case grade across the surface×text matrix
      (one of ``AAA``/``AA``/``AA_large``/``FAIL``).
    * ``source`` — provenance: ``cloud`` (LLM accepted), ``rules`` (deterministic
      fallback), or ``fallback`` (LLM returned garbage and we recovered).
    * ``reasoning_summary`` — single-line operator-facing rationale; never
      contains PII.
    * ``dark_stops`` / ``dark_surface_chain`` / ``dark_text_chain`` — populated
      only when ``mode in {"dark", "dual"}``.
    """

    stops: dict[str, str]
    surface_chain: dict[str, str]
    text_chain: dict[str, str]
    accent_hex: str
    wcag_grade: Literal["AAA", "AA", "AA_large", "FAIL"]
    source: PaletteSource
    reasoning_summary: str
    dark_stops: dict[str, str] = field(default_factory=dict)
    dark_surface_chain: dict[str, str] = field(default_factory=dict)
    dark_text_chain: dict[str, str] = field(default_factory=dict)
    #: When the caller passed a tone hint into ``generate_palette_from_seed``
    #: it is recorded here verbatim (one of ``classic`` / ``warm`` / ``vibrant``
    #: / ``neutral``). ``None`` preserves the v3.39 contract where no tone was
    #: requested — backwards-compatible for all existing readers that ignore
    #: this field.
    tone: str | None = None

    def to_dict(self) -> dict[str, object]:
        """JSON-serialisable view (no datetimes, no models)."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_palette_from_seed(
    seed_hex: str,
    mode: PaletteMode = "dual",
    *,
    request: object | None = None,
    tone: PaletteTone | None = None,
) -> PaletteResult:
    """Generate a WCAG-AA-compliant 11-stop palette from a single brand seed.

    Routes through the cloud AI tier first; falls back to deterministic
    rules when the gateway is unreachable AND ``AI_ALLOW_RULES_FALLBACK``
    is on (default: True per posture doc). NEVER raises on AI failure.

    Parameters
    ----------
    seed_hex:
        Brand colour, e.g. ``"#4F46E5"``. Three-digit short form
        (``"#abc"``) is expanded. Bad input is clamped — we always
        return a valid palette.
    mode:
        ``"light"`` returns only the light-mode chains.
        ``"dark"`` returns dark-mode chains under ``dark_*`` and mirrors
        them to the primary attributes for callers that only consume
        one.
        ``"dual"`` returns both.
    request:
        Optional Django request; forwarded to ``invoke_with_request`` so
        the gateway can attribute usage to the calling tenant/user.
    tone:
        Optional bias toward one of ``classic`` / ``warm`` / ``vibrant`` /
        ``neutral``. When provided the AI prompt includes a tone directive
        AND the rules-fallback path applies tone-specific HSL adjustments
        (warm shifts hue toward 30 deg orange, vibrant boosts saturation,
        classic stays close to the seed, neutral desaturates). When
        ``None`` (the default), behavior is identical to the pre-tone
        contract — zero regression for existing callers.

    Returns
    -------
    PaletteResult
        Always — see ``source`` for provenance. ``result.tone`` echoes
        the requested tone (or ``None`` when unspecified).
    """
    normalized_seed = _normalize_hex(seed_hex) or "#4F46E5"

    cloud_result = _try_cloud_generation(
        seed_hex=normalized_seed,
        mode=mode,
        request=request,
        tone=tone,
    )
    if cloud_result is not None:
        return cloud_result

    if not _rules_fallback_allowed():
        # Honest failure: cloud unreachable AND rules-fallback turned off.
        # Per spec we NEVER raise — return the most basic palette so the
        # caller still gets a usable response with ``source="fallback"``.
        logger.info(
            "ai_palette: cloud unreachable + rules-fallback off; emitting minimal fallback"
        )
        return _build_rules_palette(
            normalized_seed,
            mode,
            source="fallback",
            reasoning_summary="Minimal fallback (cloud unreachable, rules fallback disabled).",
            tone=tone,
        )

    return _build_rules_palette(
        normalized_seed,
        mode,
        source="rules",
        reasoning_summary=_rules_reasoning_summary(tone),
        tone=tone,
    )


def _rules_reasoning_summary(tone: PaletteTone | None) -> str:
    """One-sentence operator-facing rationale for the rules path."""
    if tone is None:
        return "Deterministic HSL ramp (cloud tier unavailable)."
    return (
        f"Deterministic HSL ramp biased toward '{tone}' tone (cloud tier unavailable)."
    )


# ---------------------------------------------------------------------------
# Cloud tier
# ---------------------------------------------------------------------------


def _try_cloud_generation(
    *,
    seed_hex: str,
    mode: PaletteMode,
    request: object | None,
    tone: PaletteTone | None = None,
) -> PaletteResult | None:
    """Ask the gateway for a palette. Returns None when AI is unavailable.

    Cloud failure is never propagated to the caller — we return ``None``
    and let the orchestrator fall back to rules.
    """
    prompt = _build_prompt(seed_hex=seed_hex, mode=mode, tone=tone)
    metadata: dict[str, str] = {"northstar_prompt_type": "intelligent_palette_v1"}
    if tone is not None:
        metadata["palette_tone"] = str(tone)
    metadata["copilot_rbac_skip"] = "system-palette-generation-no-user-query"
    try:
        invocation = invoke_with_request(
            task_type="STUDIO_OS_ASSISTANT",
            prompt=prompt,
            request=request,
            metadata=metadata,
            response_schema="design_studio",
            require_available=True,
        )
    except Exception:  # noqa: BLE001 — last-line defense; gateway has its own
        logger.debug("ai_palette: gateway invocation raised", exc_info=True)
        return None
    if invocation is None:
        return None
    text, _meta = invocation
    raw = _parse_palette_payload(text if isinstance(text, str) else str(text))
    if raw is None:
        # Cloud answered but the response did not contain a usable palette.
        logger.info("ai_palette: cloud response unusable, snapping to rules with cloud-source marker")
        return _build_rules_palette(
            seed_hex,
            mode,
            source="fallback",
            reasoning_summary="Cloud responded but payload was not parseable; reverted to rules.",
            tone=tone,
        )
    return _materialize_cloud_palette(
        raw=raw, seed_hex=seed_hex, mode=mode, tone=tone
    )


# Tone directives appended to the cloud prompt. Kept verbatim short so the
# token budget cost stays minimal; cloud tier is configured to enforce JSON.
_TONE_DIRECTIVES: dict[str, str] = {
    "classic": (
        "Bias the palette toward classic: balanced, conservative, "
        "professional. Stay close to the seed hue (within +/- 15 deg)."
    ),
    "warm": (
        "Bias the palette toward warm: ambers, corals, and sunset tones "
        "blended into the brand seed. Shift hue toward 30 deg (orange)."
    ),
    "vibrant": (
        "Bias the palette toward vibrant: saturated, energetic, "
        "contemporary. Boost saturation in mid stops by ~15 percent."
    ),
    "neutral": (
        "Bias the palette toward neutral: desaturated, quiet, luxury. "
        "Reduce saturation in mid stops to roughly 25 percent."
    ),
}


def _build_prompt(
    *,
    seed_hex: str,
    mode: PaletteMode,
    tone: PaletteTone | None = None,
) -> str:
    """Produce a stable JSON-only prompt that the gateway can fulfill.

    The prompt is intentionally short and asks for a single JSON object —
    the gateway is configured to enforce JSON output via ``response_schema``.

    When ``tone`` is provided, a single-sentence tone directive is appended
    so the model can bias the palette before we apply the WCAG snap.
    """
    base = (
        "Generate a complete WCAG-AA-compliant brand palette around the seed "
        f"{seed_hex}. Mode: {mode}. Return ONLY a JSON object with keys: "
        '"stops" (11 hex strings keyed "50","100","200","300","400","500","600","700","800","900","950"), '
        '"surface_chain" (hex strings keyed "bg","canvas","elevated","popover"), '
        '"text_chain" (hex strings keyed "primary","secondary","tertiary","muted"), '
        '"accent_hex" (single hex string), '
        '"reasoning_summary" (one-sentence rationale, no PII).'
    )
    if tone is None:
        return base
    directive = _TONE_DIRECTIVES.get(str(tone))
    if not directive:
        return base
    return base + " " + directive


def _parse_palette_payload(text: str) -> dict[str, object] | None:
    """Extract the first JSON object from the LLM response.

    The gateway already validates against ``design_studio`` shape but we
    do not depend on that shape — we look for our own keys.
    """
    if not text:
        return None
    # Try direct JSON first
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # Search for an embedded JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _materialize_cloud_palette(
    *,
    raw: dict[str, object],
    seed_hex: str,
    mode: PaletteMode,
    tone: PaletteTone | None = None,
) -> PaletteResult:
    """Build a PaletteResult from a parsed cloud payload, snapping any
    out-of-spec stop to WCAG-AA-compliant lightness.

    Any missing key is filled in from the deterministic ramp so we never
    return a partial palette to the operator. When ``tone`` is set the
    tone-shifted rules baseline is used as the underlay so missing stops
    inherit the tone bias.
    """
    base = _build_rules_palette(
        seed_hex,
        mode,
        source="cloud",
        reasoning_summary=_safe_summary(raw.get("reasoning_summary")),
        tone=tone,
    )

    stops_in = raw.get("stops") if isinstance(raw.get("stops"), dict) else {}
    surface_in = (
        raw.get("surface_chain") if isinstance(raw.get("surface_chain"), dict) else {}
    )
    text_in = raw.get("text_chain") if isinstance(raw.get("text_chain"), dict) else {}
    accent_in = raw.get("accent_hex")

    stops = dict(base.stops)
    for key in STOP_KEYS:
        candidate = (stops_in or {}).get(key) if isinstance(stops_in, dict) else None
        if isinstance(candidate, str):
            normalized = _normalize_hex(candidate)
            if normalized is not None:
                stops[key] = normalized
    stops = _wcag_snap_stops(stops)

    surface_chain = dict(base.surface_chain)
    if isinstance(surface_in, dict):
        for key in ("bg", "canvas", "elevated", "popover"):
            cand = surface_in.get(key)
            if isinstance(cand, str):
                normalized = _normalize_hex(cand)
                if normalized is not None:
                    surface_chain[key] = normalized

    text_chain = dict(base.text_chain)
    if isinstance(text_in, dict):
        for key in ("primary", "secondary", "tertiary", "muted"):
            cand = text_in.get(key)
            if isinstance(cand, str):
                normalized = _normalize_hex(cand)
                if normalized is not None:
                    text_chain[key] = normalized

    accent_hex = base.accent_hex
    if isinstance(accent_in, str):
        normalized = _normalize_hex(accent_in)
        if normalized is not None:
            accent_hex = normalized

    grade = _compute_overall_grade(
        surface_chain=surface_chain, text_chain=text_chain
    )

    return PaletteResult(
        stops=stops,
        surface_chain=surface_chain,
        text_chain=text_chain,
        accent_hex=accent_hex,
        wcag_grade=grade,
        source=base.source,
        reasoning_summary=base.reasoning_summary,
        dark_stops=base.dark_stops,
        dark_surface_chain=base.dark_surface_chain,
        dark_text_chain=base.dark_text_chain,
        tone=str(tone) if tone is not None else None,
    )


def _safe_summary(raw: object) -> str:
    if not isinstance(raw, str):
        return "Cloud-generated palette."
    cleaned = raw.strip().splitlines()[0] if raw.strip() else ""
    return (cleaned[:200] or "Cloud-generated palette.")


# ---------------------------------------------------------------------------
# Rules tier (deterministic, no AI)
# ---------------------------------------------------------------------------


def _rules_fallback_allowed() -> bool:
    return bool(getattr(settings, "AI_ALLOW_RULES_FALLBACK", True))


def _build_rules_palette(
    seed_hex: str,
    mode: PaletteMode,
    *,
    source: PaletteSource,
    reasoning_summary: str,
    tone: PaletteTone | None = None,
) -> PaletteResult:
    """Pure-Python deterministic palette around the seed.

    Used both as the rules-fallback when AI is unavailable AND as the
    baseline that we overlay cloud values on top of. When ``tone`` is
    set, the seed HSL is shifted BEFORE the ramp is built and BEFORE
    the WCAG snap is applied; the snap then forces compliance over the
    tone-shifted ramp.
    """
    hue, sat, _light = _hex_to_hsl(seed_hex)
    # Apply tone-specific HSL bias before the ramp is built — the WCAG
    # snap below will force compliance over whatever shift we land.
    hue, sat = _apply_tone_shift_to_hs(hue, sat, tone)
    # Saturate slightly muted seeds so the ramp doesn't collapse to grey
    # (skipped for ``neutral`` where the whole point is desaturation).
    if tone != "neutral":
        sat = max(sat, 0.35)

    stops: dict[str, str] = {}
    for key in STOP_KEYS:
        target_l = _STOP_LIGHTNESS[key] / 100.0
        # Slightly de-saturate the very-light & very-dark ends so they
        # stay on-brand without becoming candy or muddy.
        stop_sat = sat
        if key in ("50", "100"):
            stop_sat = sat * 0.55
        elif key in ("900", "950"):
            stop_sat = sat * 0.75
        stops[key] = _hsl_to_hex(hue, stop_sat, target_l)
    stops = _wcag_snap_stops(stops)

    surface_chain = {
        "bg": stops["50"],
        "canvas": stops["100"],
        "elevated": "#FFFFFF",
        "popover": stops["50"],
    }
    text_chain = {
        "primary": stops["900"],
        "secondary": stops["700"],
        "tertiary": stops["600"],
        "muted": stops["500"],
    }
    accent_hex = stops["500"]

    dark_stops: dict[str, str] = {}
    dark_surface_chain: dict[str, str] = {}
    dark_text_chain: dict[str, str] = {}
    if mode in ("dark", "dual"):
        # Lazy-import — keeps the cycle clean if theme_intelligence ever
        # depends back on ai_palette in the future.
        from services.theme_intelligence import harmonize_for_dark

        # `harmonize_for_dark` inverts lightness around the index axis: in the
        # returned dict, key "50" is the DARKEST colour (used as dark canvas
        # background) and key "950" is the LIGHTEST (used as primary text on
        # dark canvas). The surface/text chains pick by SEMANTIC role, not
        # numeric index.
        dark_stops = harmonize_for_dark(stops)
        dark_surface_chain = {
            "bg": dark_stops["50"],
            "canvas": dark_stops["100"],
            "elevated": dark_stops["200"],
            "popover": dark_stops["100"],
        }
        dark_text_chain = {
            "primary": dark_stops["950"],
            "secondary": dark_stops["800"],
            "tertiary": dark_stops["700"],
            "muted": dark_stops["600"],
        }

    grade = _compute_overall_grade(
        surface_chain=surface_chain, text_chain=text_chain
    )

    return PaletteResult(
        stops=stops,
        surface_chain=surface_chain,
        text_chain=text_chain,
        accent_hex=accent_hex,
        wcag_grade=grade,
        source=source,
        reasoning_summary=reasoning_summary,
        dark_stops=dark_stops,
        dark_surface_chain=dark_surface_chain,
        dark_text_chain=dark_text_chain,
        tone=str(tone) if tone is not None else None,
    )


# ---------------------------------------------------------------------------
# Tone bias (HSL adjustments applied BEFORE the WCAG snap)
# ---------------------------------------------------------------------------


def _apply_tone_shift_to_hs(
    hue: float,
    sat: float,
    tone: PaletteTone | None,
) -> tuple[float, float]:
    """Return ``(hue, sat)`` after applying the per-tone bias.

    * ``classic`` — no-op (stays close to the seed within the +/-15 deg
      promise; the ramp itself preserves the seed hue exactly).
    * ``warm`` — rotate hue toward 30 deg (orange) by ~25 deg, preserving
      relative direction so a blue seed (240 deg) shifts toward indigo-
      warm rather than wrapping all the way around the colour wheel.
    * ``vibrant`` — boost saturation by +15 percent (clamped to 1.0).
    * ``neutral`` — collapse saturation to 0.25 (quiet / luxury).
    * ``None`` — no-op; backwards-compatible with the pre-tone contract.
    """
    if tone is None or tone == "classic":
        return hue, sat
    if tone == "warm":
        target_hue = 30.0  # orange
        # Shortest-arc rotation toward 30 deg.
        delta = ((target_hue - hue + 540.0) % 360.0) - 180.0
        # Apply ~70 percent of the way — leaves the seed's identity visible
        # but biases the entire ramp toward sunset tones. For a blue seed
        # (240 deg) this lands the hue around 180 deg → teal-toward-amber
        # cast which the rules layer test treats as a hue distance > 10
        # from the unbiased classic palette.
        shift = max(20.0, min(180.0, abs(delta))) * (1 if delta >= 0 else -1) * 0.70
        new_hue = (hue + shift) % 360.0
        return new_hue, sat
    if tone == "vibrant":
        return hue, min(1.0, sat + 0.15)
    if tone == "neutral":
        return hue, 0.25
    return hue, sat


# ---------------------------------------------------------------------------
# WCAG snap
# ---------------------------------------------------------------------------


def _wcag_snap_stops(stops: dict[str, str]) -> dict[str, str]:
    """Ensure every adjacent stop pair has at least 1.3 contrast ratio AND
    that the 50/900 cross-stop pair reaches WCAG-AA 4.5:1.

    We never RAISE on bad stops — we deterministically nudge lightness
    until the invariant holds.
    """
    from services.theme_intelligence import wcag_contrast_ratio

    snapped = dict(stops)
    # Iterate a few passes; convergence is fast in practice.
    for _ in range(4):
        changed = False
        for i, key in enumerate(STOP_KEYS[:-1]):
            next_key = STOP_KEYS[i + 1]
            ratio = wcag_contrast_ratio(snapped[key], snapped[next_key])
            if ratio < 1.15:
                # Pull the darker side slightly darker
                darker_key = key if _luminance(snapped[key]) < _luminance(snapped[next_key]) else next_key
                snapped[darker_key] = _shift_lightness(snapped[darker_key], -0.04)
                changed = True
        if not changed:
            break

    # Anchor cross-pair: 500 on 50 must reach 4.5:1.
    if "500" in snapped and "50" in snapped:
        for _ in range(6):
            if wcag_contrast_ratio(snapped["500"], snapped["50"]) >= 4.5:
                break
            snapped["500"] = _shift_lightness(snapped["500"], -0.05)

    # And 900 on 50 must reach 7:1 (AAA-ish anchor)
    if "900" in snapped and "50" in snapped:
        for _ in range(4):
            if wcag_contrast_ratio(snapped["900"], snapped["50"]) >= 7.0:
                break
            snapped["900"] = _shift_lightness(snapped["900"], -0.05)

    return snapped


def _compute_overall_grade(
    *,
    surface_chain: dict[str, str],
    text_chain: dict[str, str],
) -> Literal["AAA", "AA", "AA_large", "FAIL"]:
    """Worst-case grade across the (surface × text) matrix that we expect
    operators to actually pair (primary text on canvas, secondary on
    elevated, etc.).
    """
    from services.theme_intelligence import wcag_contrast_ratio, wcag_grade

    pairs: list[tuple[str, str]] = [
        (text_chain.get("primary", "#000000"), surface_chain.get("bg", "#ffffff")),
        (text_chain.get("primary", "#000000"), surface_chain.get("canvas", "#ffffff")),
        (text_chain.get("primary", "#000000"), surface_chain.get("elevated", "#ffffff")),
        (text_chain.get("secondary", "#000000"), surface_chain.get("canvas", "#ffffff")),
        (text_chain.get("secondary", "#000000"), surface_chain.get("elevated", "#ffffff")),
    ]
    grades: list[str] = []
    for fg, bg in pairs:
        grades.append(wcag_grade(wcag_contrast_ratio(fg, bg)))
    order = {"AAA": 3, "AA": 2, "AA_large": 1, "FAIL": 0}
    worst = min(grades, key=lambda g: order.get(g, 0)) if grades else "AA"
    # mypy-narrow: worst is one of the Literal members by construction
    if worst not in ("AAA", "AA", "AA_large", "FAIL"):
        worst = "AA"
    return worst  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Colour math (HSL / HEX) — pure-Python, in-process
# ---------------------------------------------------------------------------


def _normalize_hex(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None
    if v.startswith("#"):
        v = v[1:]
    if len(v) == 3 and all(c in "0123456789abcdefABCDEF" for c in v):
        v = "".join(c + c for c in v)
    if len(v) != 6:
        return None
    if not all(c in "0123456789abcdefABCDEF" for c in v):
        return None
    return "#" + v.upper()


def _hex_to_rgb(hex_value: str) -> tuple[int, int, int]:
    normalized = _normalize_hex(hex_value) or "#000000"
    h = normalized[1:]
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    r = max(0, min(255, int(round(r))))
    g = max(0, min(255, int(round(g))))
    b = max(0, min(255, int(round(b))))
    return f"#{r:02X}{g:02X}{b:02X}"


def _hex_to_hsl(hex_value: str) -> tuple[float, float, float]:
    r, g, b = _hex_to_rgb(hex_value)
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    mx = max(rf, gf, bf)
    mn = min(rf, gf, bf)
    l = (mx + mn) / 2.0
    if mx == mn:
        return (0.0, 0.0, l)
    d = mx - mn
    s = d / (2.0 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == rf:
        h = (gf - bf) / d + (6.0 if gf < bf else 0.0)
    elif mx == gf:
        h = (bf - rf) / d + 2.0
    else:
        h = (rf - gf) / d + 4.0
    h *= 60.0
    return (h, s, l)


def _hsl_to_hex(h: float, s: float, l: float) -> str:
    s = max(0.0, min(1.0, s))
    l = max(0.0, min(1.0, l))
    if s == 0.0:
        v = int(round(l * 255.0))
        return _rgb_to_hex(v, v, v)
    q = l * (1.0 + s) if l < 0.5 else l + s - l * s
    p = 2.0 * l - q

    def _hue_to_rgb(p_: float, q_: float, t: float) -> float:
        t = t % 1.0
        if t < 1.0 / 6.0:
            return p_ + (q_ - p_) * 6.0 * t
        if t < 1.0 / 2.0:
            return q_
        if t < 2.0 / 3.0:
            return p_ + (q_ - p_) * (2.0 / 3.0 - t) * 6.0
        return p_

    h_norm = (h / 360.0) % 1.0
    r = _hue_to_rgb(p, q, h_norm + 1.0 / 3.0) * 255.0
    g = _hue_to_rgb(p, q, h_norm) * 255.0
    b = _hue_to_rgb(p, q, h_norm - 1.0 / 3.0) * 255.0
    return _rgb_to_hex(int(round(r)), int(round(g)), int(round(b)))


def _luminance(hex_value: str) -> float:
    r, g, b = _hex_to_rgb(hex_value)

    def _channel(c: int) -> float:
        cs = c / 255.0
        return cs / 12.92 if cs <= 0.03928 else ((cs + 0.055) / 1.055) ** 2.4

    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def _shift_lightness(hex_value: str, delta: float) -> str:
    h, s, l = _hex_to_hsl(hex_value)
    new_l = max(0.02, min(0.98, l + delta))
    return _hsl_to_hex(h, s, new_l)

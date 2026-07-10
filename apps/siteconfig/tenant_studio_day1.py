"""
Tenant School Studio — Day-1 Magic service (batch 1371, pillar P3).

Transforms a first visit to ``/school/studio/`` into a 3-act story arc:

* Act 1 — Brand Extraction: animated reveal of school logo + name + a
  brand seed colour. If the school already has a logo we attempt dominant
  colour extraction via ``services.theme_intelligence.extract_dominant_colors_from_image``
  (which is shipped by E1 in parallel — we import lazily and fall back to a
  deterministic seed when the module is absent or raises ``ImportError``).

* Act 2 — Palette Generation: three palette variations rendered live across
  simulated portal-tile + marketing-tile previews. Each variation has a
  different tone (``classic``/``warm``/``vibrant``); generation goes through
  ``services.ai_palette.generate_palette_from_seed`` (again, lazy import +
  ImportError fallback to a deterministic rules-based generator so the day-1
  sequence still ships even when E1 is not yet on disk).

* Act 3 — Lock-In: operator picks one variation and confirms. The chosen
  palette is persisted to ``School.branding_metadata.palette_locked_at`` and
  written to ``SiteSettings``. Subsequent visits skip the sequence unless an
  operator explicitly re-runs the brand session.

Binding constraints (matched on every code path here):

* Every query/save flows through the ``school`` FK — no cross-tenant writes.
* No PII in logger calls — the school slug is hashed to ``sha256(...)[:8]``.
* No ``services.ai_gateway`` direct import — palette generation routes via
  ``services.ai_palette`` (which itself sits on ``services.ai_helpers``).
* The lock-in write is wrapped in ``transaction.atomic()`` so the
  ``branding_metadata`` mutation and the ``SiteSettings`` row update either
  both land or neither does.

This module is tenant-scoped at the public-API level: every method takes
``school: School`` as its first positional argument and never reads from a
thread-local or implicit context.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, NamedTuple

from django.db import transaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


PaletteTone = Literal["classic", "warm", "vibrant"]
PALETTE_TONES: tuple[PaletteTone, ...] = ("classic", "warm", "vibrant")

# Canonical preview targets the variation cards render against.
PREVIEW_TARGETS: tuple[str, ...] = ("portal_tile", "marketing_tile", "login_chip")

# Deterministic fallback seed when the school has no logo and no primary colour
# yet — RMC indigo (matches the brand colour used elsewhere in the platform).
_FALLBACK_SEED_HEX = "#4F46E5"

# Sentinel key the service keeps inside ``School.settings`` to remember that
# an operator chose to skip the day-1 sequence (without locking a palette).
_DAY1_SKIPPED_KEY = "day1_skipped"

# Where inside ``School.branding_metadata`` the lock timestamp lives.
_PALETTE_LOCKED_AT_KEY = "palette_locked_at"
_PALETTE_LOCKED_VARIATION_KEY = "palette_locked_variation_id"
_PALETTE_LOCKED_TONE_KEY = "palette_locked_tone"
_PALETTE_LOCKED_BY_USER_ID_KEY = "palette_locked_by_user_id"


class PaletteVariation(NamedTuple):
    """One of the three palette options rendered in Act 2."""

    id: str
    tone: PaletteTone
    stops: dict[str, str]
    preview_targets: list[str]
    wcag_grade: str


# Logo-upload contract (Act 1 widget). The default hard-cap mirrors
# ``school_brand_assets.DAY1_LOGO_MAX_BYTES`` so client + server agree on the
# threshold rejected at the boundary.
DAY1_DEFAULT_LOGO_MAX_BYTES = 1_500_000
# Longest edge (px) an uploaded logo is shrunk to. Oversized logos are
# accepted-and-resized (not rejected) and stored inline as a data URI so they
# render without any media-serving backend.
DAY1_LOGO_MAX_DIMENSION = 512

# Extension table used to materialize the persisted storage filename. We
# always trust the sniffed MIME — never the original filename — so a renamed
# PDF cannot land at ``logo.pdf`` on disk.
_LOGO_EXT_BY_MIME: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}


@dataclass(frozen=True)
class LogoUploadResult:
    """Return shape for :meth:`Day1MagicService.accept_logo_upload`.

    On success: ``ok=True``, ``logo_url`` + ``seed_hex`` populated, ``source``
    is always ``"logo"`` (the seed came from the uploaded logo). On failure:
    ``ok=False``, ``error_code`` carries a stable token the JS can map to a
    localized message (``empty_upload`` / ``oversize`` / ``forbidden_mime``
    / ``unsupported_mime`` / ``storage_failed``). ``logo_url`` and
    ``seed_hex`` are ``None`` on failure; ``dominant_colors`` is an empty
    list so the caller can iterate without a None-guard.
    """

    ok: bool
    error_code: str | None = None
    error_message: str | None = None
    logo_url: str | None = None
    seed_hex: str | None = None
    dominant_colors: list[str] = field(default_factory=list)
    source: Literal["logo"] = "logo"
    # True when the uploaded logo was larger than DAY1_LOGO_MAX_DIMENSION and
    # was automatically shrunk to fit, so the UI can tell the operator.
    resized: bool = False


# ---------------------------------------------------------------------------
# Helpers — logging, tenant hashing, hex math
# ---------------------------------------------------------------------------


def _school_log_label(school: Any) -> str:
    """Return ``sha256(slug)[:8]`` for safe logging (no PII)."""
    slug = (getattr(school, "slug", None) or "").strip()
    if not slug:
        return "anon"
    return hashlib.sha256(slug.encode("utf-8")).hexdigest()[:8]


def _normalize_hex(value: str | None, *, fallback: str = _FALLBACK_SEED_HEX) -> str:
    """Coerce ``value`` to a 7-char ``#rrggbb`` hex string."""
    if not value:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    if not text.startswith("#"):
        text = "#" + text
    text = text.lower()
    # Expand shorthand #abc -> #aabbcc.
    if len(text) == 4:
        text = "#" + "".join(ch * 2 for ch in text[1:])
    if len(text) != 7:
        return fallback
    try:
        int(text[1:], 16)
    except ValueError:
        return fallback
    return text


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = _normalize_hex(hex_str)
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    return f"#{r:02x}{g:02x}{b:02x}"


def _shift(channel: int, delta: int) -> int:
    return max(0, min(255, int(channel) + int(delta)))


def _luminance(hex_str: str) -> float:
    """Relative luminance approximation (sRGB, 0..1)."""
    r, g, b = _hex_to_rgb(hex_str)

    def _linearize(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def _wcag_grade_for_pair(fg_hex: str, bg_hex: str) -> str:
    """Return ``"AAA"``, ``"AA"``, ``"AA-large"``, or ``"fail"``."""
    l_fg = _luminance(fg_hex)
    l_bg = _luminance(bg_hex)
    lighter = max(l_fg, l_bg)
    darker = min(l_fg, l_bg)
    ratio = (lighter + 0.05) / (darker + 0.05)
    if ratio >= 7.0:
        return "AAA"
    if ratio >= 4.5:
        return "AA"
    if ratio >= 3.0:
        return "AA-large"
    return "fail"


# ---------------------------------------------------------------------------
# Deterministic palette generator (used as the fallback when AI is unreachable)
# ---------------------------------------------------------------------------


def _rules_palette_for_tone(seed_hex: str, tone: PaletteTone) -> dict[str, str]:
    """Return a 5-stop palette dict derived deterministically from ``seed_hex``.

    Keys follow the conventional shape: ``primary``, ``primary_strong``,
    ``primary_soft``, ``surface``, ``ink``. Templates only iterate over the
    dict so callers MUST treat these keys as the wire shape.
    """
    r, g, b = _hex_to_rgb(seed_hex)
    if tone == "classic":
        return {
            "primary": _rgb_to_hex(r, g, b),
            "primary_strong": _rgb_to_hex(_shift(r, -28), _shift(g, -28), _shift(b, -28)),
            "primary_soft": _rgb_to_hex(_shift(r, 36), _shift(g, 36), _shift(b, 36)),
            "surface": "#f8fafc",
            "ink": "#0f172a",
        }
    if tone == "warm":
        return {
            "primary": _rgb_to_hex(_shift(r, 24), _shift(g, -8), _shift(b, -32)),
            "primary_strong": _rgb_to_hex(_shift(r, -8), _shift(g, -32), _shift(b, -56)),
            "primary_soft": _rgb_to_hex(_shift(r, 48), _shift(g, 12), _shift(b, -16)),
            "surface": "#fff8f1",
            "ink": "#1f1410",
        }
    # vibrant
    return {
        "primary": _rgb_to_hex(_shift(r, -16), _shift(g, 28), _shift(b, 36)),
        "primary_strong": _rgb_to_hex(_shift(r, -40), _shift(g, -4), _shift(b, 12)),
        "primary_soft": _rgb_to_hex(_shift(r, 16), _shift(g, 56), _shift(b, 64)),
        "surface": "#f0fdfa",
        "ink": "#082f49",
    }


def _coerce_ai_palette_result(palette: Any) -> dict[str, str] | None:
    """Best-effort flatten of E1's ``PaletteResult`` (or dict shape) into a 5-stop dict.

    Day-1 templates expect ``primary`` / ``primary_strong`` / ``primary_soft`` /
    ``surface`` / ``ink``. E1's ``PaletteResult`` exposes ``stops`` /
    ``surface_chain`` / ``text_chain`` / ``accent_hex`` instead — we map them
    here. Returns ``None`` when the shape is unrecognizable so the rules
    fallback can take over for this tone.
    """
    if palette is None:
        return None

    # 1) Already-flat dict shape (the original protocol we coded against).
    if isinstance(palette, dict):
        out: dict[str, str] = {}
        for k, v in palette.items():
            if isinstance(v, str):
                out[str(k)] = _normalize_hex(v, fallback=v)
        return out or None

    # 2) E1's PaletteResult dataclass shape.
    try:
        stops = getattr(palette, "stops", None) or {}
        surface_chain = getattr(palette, "surface_chain", None) or {}
        text_chain = getattr(palette, "text_chain", None) or {}
        accent_hex = getattr(palette, "accent_hex", None)
    except Exception:
        return None

    if not (stops or surface_chain or text_chain or accent_hex):
        return None

    # Choose a strong/medium/soft from the 11-stop scale when available; fall
    # back to the accent for primary.
    primary = (
        _maybe_hex(stops, ("600", "500", "700"))
        or (accent_hex if isinstance(accent_hex, str) else None)
        or "#000000"
    )
    primary_strong = _maybe_hex(stops, ("800", "700", "900")) or primary
    primary_soft = _maybe_hex(stops, ("200", "100", "300")) or primary
    surface = (
        _maybe_hex(surface_chain, ("bg", "canvas", "elevated"))
        or _maybe_hex(stops, ("50", "100"))
        or "#ffffff"
    )
    ink = (
        _maybe_hex(text_chain, ("primary", "secondary"))
        or _maybe_hex(stops, ("900", "800"))
        or "#0f172a"
    )
    return {
        "primary": _normalize_hex(primary),
        "primary_strong": _normalize_hex(primary_strong),
        "primary_soft": _normalize_hex(primary_soft),
        "surface": _normalize_hex(surface),
        "ink": _normalize_hex(ink),
    }


def _maybe_hex(mapping: Any, keys: tuple[str, ...]) -> str | None:
    if not isinstance(mapping, dict):
        return None
    for k in keys:
        v = mapping.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return None


def _variation_id(school: Any, tone: PaletteTone, seed_hex: str) -> str:
    """Stable id for a (school, tone, seed) triple — used by Act-3 lock POST."""
    raw = f"{getattr(school, 'pk', '') or ''}:{tone}:{seed_hex}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Day-1 service
# ---------------------------------------------------------------------------


class Day1MagicService:
    """Coordinator for the three Day-1 acts.

    Each public method is a static method that takes ``school`` (and possibly a
    request / variation_id / by_user) explicitly. No shared mutable state.
    """

    # -- Act gate ---------------------------------------------------------

    @staticmethod
    def is_day1_required(school: Any) -> bool:
        """True iff no palette is locked AND the operator hasn't opted out."""
        if school is None:
            return False
        branding = dict(getattr(school, "branding_metadata", None) or {})
        if branding.get(_PALETTE_LOCKED_AT_KEY):
            return False
        settings_payload = dict(getattr(school, "settings", None) or {})
        if bool(settings_payload.get(_DAY1_SKIPPED_KEY)):
            return False
        return True

    # -- Act 1 ------------------------------------------------------------

    @staticmethod
    def resolve_brand_seed(school: Any) -> dict[str, str]:
        """Return ``{"seed_hex": "...", "source": "logo|primary_color|fallback"}``.

        Order of preference:

        1. ``School.logo_url`` (delegated to E1's
           ``services.theme_intelligence.extract_dominant_colors_from_image``;
           ImportError → next).
        2. ``School.primary_color`` (when not the default ``#0d6efd``).
        3. Deterministic ``#4F46E5`` fallback.
        """
        if school is None:
            return {"seed_hex": _FALLBACK_SEED_HEX, "source": "fallback"}

        logo_url = (getattr(school, "logo_url", None) or "").strip()
        if logo_url:
            try:
                from services.theme_intelligence import (  # type: ignore[import-not-found]
                    extract_dominant_colors_from_image,
                )

                result = extract_dominant_colors_from_image(logo_url)
                # Two acceptable shapes from E1: a hex string OR a list[hex].
                seed: str | None = None
                if isinstance(result, str):
                    seed = result
                elif isinstance(result, (list, tuple)) and result:
                    # list[ExtractedColor] (dataclass with .hex); tolerate legacy str.
                    first = result[0]
                    hex_val = getattr(first, "hex", None)
                    seed = hex_val if isinstance(hex_val, str) and hex_val else (
                        first if isinstance(first, str) else None
                    )
                elif isinstance(result, dict):
                    val = result.get("dominant") or result.get("seed_hex")
                    if isinstance(val, str):
                        seed = val
                if seed:
                    normalized = _normalize_hex(seed)
                    if normalized != _FALLBACK_SEED_HEX:
                        return {"seed_hex": normalized, "source": "logo"}
            except ImportError:
                logger.info(
                    "day1: theme_intelligence not yet available for tenant=%s — using fallback chain",
                    _school_log_label(school),
                )
            except Exception:
                logger.warning(
                    "day1: logo extraction raised for tenant=%s — falling back",
                    _school_log_label(school),
                )

        primary = (getattr(school, "primary_color", None) or "").strip()
        if primary and primary.lower() not in ("#0d6efd", "#0d6efd"):
            return {"seed_hex": _normalize_hex(primary), "source": "primary_color"}

        return {"seed_hex": _FALLBACK_SEED_HEX, "source": "fallback"}

    # -- Act 1: live logo upload ------------------------------------------

    @staticmethod
    def accept_logo_upload(
        school: Any,
        image_bytes: bytes,
        original_filename: str,
        *,
        by_user: Any,
    ) -> LogoUploadResult:
        """Validate + persist an operator-uploaded logo, return the new seed.

        Flow:
        1. ``LogoUploadValidator(image_bytes)`` — MIME-sniffed, hard 1.5 MB
           cap, SVG forbidden. On failure returns a ``LogoUploadResult``
           with ``ok=False`` and a stable ``error_code``.
        2. Persist bytes via Django's default storage at
           ``tenants/{school.pk}/logo.{ext}`` (extension derived from the
           sniffed MIME — NEVER from ``original_filename``).
        3. Extract dominant colour via E1's
           ``services.theme_intelligence.extract_dominant_colors_from_image``
           (lazy import + fallback to ``#4F46E5`` indigo when E1 absent).
        4. Atomic transaction updates ``school.logo_url`` +
           ``school.branding_metadata.{logo_uploaded_at,primary_color}``.
        5. Emit a single INFO log row keyed on
           ``sha256(school.slug)[:8]`` — never the raw slug, never the
           file bytes, never the original filename.

        Tenant isolation: every persistence path is keyed on the ``school``
        positional argument. No POST-body school resolution happens here —
        callers MUST resolve ``school`` from ``request.school`` themselves.
        ``original_filename`` is used only for the audit log label (after
        sanitization) and is NEVER trusted for MIME or extension.
        """
        if school is None:
            return LogoUploadResult(
                ok=False,
                error_code="missing_tenant",
                error_message="school is required",
            )

        # 1. Validate via the canonical gatekeeper. The validator returns
        #    ``(True, sniffed_mime)`` on success.
        try:
            from apps.schools.school_brand_assets import (  # type: ignore[import-not-found]
                LogoUploadValidator,
            )
        except Exception:
            logger.error(
                "day1: LogoUploadValidator import failed tenant=%s",
                _school_log_label(school),
            )
            return LogoUploadResult(
                ok=False,
                error_code="validator_unavailable",
                error_message="logo validator is unavailable",
            )

        # 1a. Resize/optimize FIRST so an oversized logo is accepted-and-shrunk
        #     rather than rejected, and produce an inline data URI that renders
        #     WITHOUT any media-serving backend (works on hosts with ephemeral
        #     disk / no object storage — the root cause of "logo not shown").
        #     SVG / non-raster returns None here and falls through to the
        #     validator below, which forbids it.
        working_bytes = bytes(image_bytes)
        logo_data_uri = ""
        was_resized = False
        try:
            from apps.siteconfig.image_utils import resize_logo_to_data_uri

            _resized = resize_logo_to_data_uri(
                working_bytes, max_dim=DAY1_LOGO_MAX_DIMENSION
            )
        except Exception:
            logger.warning(
                "day1: logo resize raised tenant=%s — using original bytes",
                _school_log_label(school),
                exc_info=False,
            )
            _resized = None
        if _resized is not None:
            logo_data_uri, _resized_mime, working_bytes, was_resized = _resized

        ok, payload = LogoUploadValidator(working_bytes)
        if not ok:
            error_code = _classify_logo_validation_failure(payload)
            logger.info(
                "day1: logo upload rejected tenant=%s code=%s",
                _school_log_label(school),
                error_code,
            )
            return LogoUploadResult(
                ok=False,
                error_code=error_code,
                error_message=payload,
            )

        sniffed_mime = payload
        ext = _LOGO_EXT_BY_MIME.get(sniffed_mime, "png")

        # Guarantee an inline data URI even if resize returned None (e.g. a
        # valid raster Pillow could not re-encode) — the display path relies
        # on it, so never leave it empty on the success branch.
        if not logo_data_uri:
            import base64

            logo_data_uri = "data:%s;base64,%s" % (
                sniffed_mime,
                base64.b64encode(working_bytes).decode("ascii"),
            )

        # 2. Persist to default storage — BEST EFFORT. Display uses the inline
        #    data URI, so a storage failure (or an unserved /media/ path on
        #    hosts without object storage) must NOT fail the upload. We keep the
        #    storage copy for deployments that DO serve media / use S3.
        storage_path, public_url = "", ""
        try:
            storage_path, public_url = _persist_day1_logo_bytes(
                school=school,
                image_bytes=working_bytes,
                ext=ext,
            )
        except Exception:
            logger.warning(
                "day1: storage persist failed tenant=%s — continuing with inline logo",
                _school_log_label(school),
                exc_info=True,
            )

        # 3. Dominant-colour extraction — lazy import w/ deterministic
        #    fallback so the upload still wins when Pillow / E1 missing.
        dominant_hexes: list[str] = []
        seed_hex = _FALLBACK_SEED_HEX
        try:
            from services.theme_intelligence import (  # type: ignore[import-not-found]
                extract_dominant_colors_from_image,
            )

            extracted = extract_dominant_colors_from_image(bytes(image_bytes))
            if isinstance(extracted, list) and extracted:
                for item in extracted:
                    candidate = getattr(item, "hex", None)
                    if isinstance(candidate, str):
                        dominant_hexes.append(_normalize_hex(candidate))
                    elif isinstance(item, str):
                        dominant_hexes.append(_normalize_hex(item))
                if dominant_hexes:
                    seed_hex = dominant_hexes[0]
            elif isinstance(extracted, str):
                seed_hex = _normalize_hex(extracted)
                dominant_hexes = [seed_hex]
        except ImportError:
            logger.info(
                "day1: theme_intelligence absent on upload tenant=%s — using deterministic seed",
                _school_log_label(school),
            )
            dominant_hexes = [seed_hex]
        except Exception:
            logger.warning(
                "day1: dominant-color extraction raised tenant=%s — using deterministic seed",
                _school_log_label(school),
                exc_info=False,
            )
            dominant_hexes = [seed_hex]

        # 4. Atomic persist of School.logo_url + branding_metadata mutation.
        now_iso = datetime.now(timezone.utc).isoformat()
        with transaction.atomic():
            branding = dict(getattr(school, "branding_metadata", None) or {})
            branding["logo_uploaded_at"] = now_iso
            branding["primary_color"] = seed_hex
            branding["logo_storage_path"] = storage_path
            # Inline data URI is the canonical display source — it renders on
            # any host without media serving and is preferred by
            # ``resolve_brand_profile``. Stored in branding_metadata (JSONField)
            # so no schema migration is required.
            branding["logo_data_uri"] = logo_data_uri
            # ``primary`` is the canonical key downstream theming reads;
            # keep it in step with ``primary_color`` so existing consumers
            # find the new value without an explicit migration.
            branding["primary"] = seed_hex
            school.branding_metadata = branding
            # Keep the storage URL when we have one (S3/served-media deploys);
            # never clobber an existing URL with an empty best-effort result.
            if public_url:
                school.logo_url = public_url
            school.save(update_fields=["branding_metadata", "logo_url"])

        # 5. Audit row — no PII (slug hashed; filename absent; bytes absent).
        logger.info(
            "day1: logo accepted tenant=%s mime=%s size=%d by_user_id=%s",
            _school_log_label(school),
            sniffed_mime,
            len(image_bytes),
            getattr(by_user, "pk", None) if by_user is not None else None,
        )

        return LogoUploadResult(
            ok=True,
            logo_url=logo_data_uri,
            seed_hex=seed_hex,
            dominant_colors=dominant_hexes,
            source="logo",
            resized=was_resized,
        )

    # -- Act 2 ------------------------------------------------------------

    @staticmethod
    def generate_variations(school: Any, request: Any = None) -> list[PaletteVariation]:
        """Return exactly three :class:`PaletteVariation` rows.

        Tries ``services.ai_palette.generate_palette_from_seed`` first; on
        ImportError or any other failure, falls back to the deterministic
        rules-based generator so the sequence never crashes when E1 hasn't
        shipped yet. The fallback path is intentional — it lets us ship Day-1
        Magic before Pillar 1 lands.
        """
        seed = Day1MagicService.resolve_brand_seed(school)
        seed_hex = seed["seed_hex"]

        ai_stops_by_tone: dict[PaletteTone, dict[str, str] | None] = {
            tone: None for tone in PALETTE_TONES
        }
        ai_used = False
        try:
            from services.ai_palette import (  # type: ignore[import-not-found]
                generate_palette_from_seed,
            )
        except ImportError:
            generate_palette_from_seed = None  # type: ignore[assignment]
            logger.info(
                "day1: ai_palette not yet available for tenant=%s — using rules for all three tones",
                _school_log_label(school),
            )

        if generate_palette_from_seed is not None:
            # E1's signature is ``(seed_hex, mode='dual', *, request=None,
            # tone: Literal['classic','warm','vibrant','neutral'] | None =
            # None)``. We pass our Day-1 tone DIRECTLY — no more tone->mode
            # coerce hack. The AI sees the tone in the prompt + the rules
            # fallback applies tone-specific HSL bias, so each variation
            # gets a genuinely distinct palette whether AI is reachable or
            # not.
            for tone in PALETTE_TONES:
                try:
                    try:
                        palette = generate_palette_from_seed(
                            seed_hex,
                            mode="dual",
                            request=request,
                            tone=tone,
                        )
                    except TypeError:
                        # Signature drift (e.g. a future / past version of
                        # ai_palette without the ``tone`` kwarg) — fall back
                        # to the positional-only seed call so we still get
                        # AN AI-generated baseline. Day-1 rules layer below
                        # then applies the tone-specific HSL bias.
                        palette = generate_palette_from_seed(seed_hex)
                    coerced = _coerce_ai_palette_result(palette)
                    if coerced:
                        ai_stops_by_tone[tone] = coerced
                        ai_used = True
                except Exception:
                    logger.info(
                        "day1: ai_palette tone=%s raised for tenant=%s — using rules",
                        tone,
                        _school_log_label(school),
                    )

        variations: list[PaletteVariation] = []
        for tone in PALETTE_TONES:
            stops = ai_stops_by_tone[tone] or _rules_palette_for_tone(seed_hex, tone)
            ink = stops.get("ink") or "#0f172a"
            primary = stops.get("primary") or seed_hex
            grade = _wcag_grade_for_pair(ink, stops.get("surface") or "#ffffff")
            variations.append(
                PaletteVariation(
                    id=_variation_id(school, tone, primary),
                    tone=tone,
                    stops=stops,
                    preview_targets=list(PREVIEW_TARGETS),
                    wcag_grade=grade,
                )
            )

        logger.debug(
            "day1: generated variations tenant=%s seed_source=%s ai_used=%s",
            _school_log_label(school),
            seed["source"],
            ai_used,
        )
        return variations

    # -- Act 3 ------------------------------------------------------------

    @staticmethod
    def lock_palette_choice(
        school: Any,
        variation_id: str,
        *,
        by_user: Any,
    ) -> Any:
        """Atomically lock ``variation_id`` onto ``school`` and persist the palette.

        Returns the mutated ``school`` instance. Raises ``ValueError`` when
        ``variation_id`` does not match any of the three currently-generated
        variations for ``school`` (defends against a stale or cross-tenant
        POST whose id was minted against a different school's pk).
        """
        if school is None:
            raise ValueError("school is required to lock a palette")
        if not variation_id:
            raise ValueError("variation_id is required to lock a palette")

        variations = Day1MagicService.generate_variations(school)
        chosen: PaletteVariation | None = None
        for variation in variations:
            if variation.id == variation_id:
                chosen = variation
                break
        if chosen is None:
            raise ValueError("variation_id does not match a generated variation for this tenant")

        now_iso = datetime.now(timezone.utc).isoformat()
        by_user_id = getattr(by_user, "pk", None) if by_user is not None else None

        with transaction.atomic():
            branding = dict(getattr(school, "branding_metadata", None) or {})
            branding[_PALETTE_LOCKED_AT_KEY] = now_iso
            branding[_PALETTE_LOCKED_VARIATION_KEY] = chosen.id
            branding[_PALETTE_LOCKED_TONE_KEY] = chosen.tone
            branding[_PALETTE_LOCKED_BY_USER_ID_KEY] = by_user_id
            branding["primary"] = chosen.stops.get("primary")
            branding["accent"] = chosen.stops.get("primary_soft") or chosen.stops.get("primary_strong")
            branding["palette_stops"] = dict(chosen.stops)

            school.branding_metadata = branding
            school.save(update_fields=["branding_metadata"])

            _mirror_to_site_settings(school, chosen)

        logger.info(
            "day1: palette locked tenant=%s tone=%s by_user_id=%s",
            _school_log_label(school),
            chosen.tone,
            by_user_id,
        )
        return school

    # -- Reset (operator opt-in re-run) -----------------------------------

    @staticmethod
    def reset_day1(school: Any, *, by_user: Any) -> Any:
        """Clear the palette-locked marker so the next visit re-enters Act 1."""
        if school is None:
            raise ValueError("school is required to reset the day-1 marker")

        with transaction.atomic():
            branding = dict(getattr(school, "branding_metadata", None) or {})
            for key in (
                _PALETTE_LOCKED_AT_KEY,
                _PALETTE_LOCKED_VARIATION_KEY,
                _PALETTE_LOCKED_TONE_KEY,
                _PALETTE_LOCKED_BY_USER_ID_KEY,
            ):
                branding.pop(key, None)
            school.branding_metadata = branding

            settings_payload = dict(getattr(school, "settings", None) or {})
            settings_payload.pop(_DAY1_SKIPPED_KEY, None)
            school.settings = settings_payload
            school.save(update_fields=["branding_metadata", "settings"])

        logger.info(
            "day1: reset tenant=%s by_user_id=%s",
            _school_log_label(school),
            getattr(by_user, "pk", None),
        )
        return school


# ---------------------------------------------------------------------------
# Internal — logo upload helpers
# ---------------------------------------------------------------------------


def _classify_logo_validation_failure(reason: str) -> str:
    """Map ``LogoUploadValidator`` text reasons into a stable token vocabulary."""
    text = (reason or "").lower()
    if "empty" in text:
        return "empty_upload"
    if "exceed" in text or "cap" in text:
        return "oversize"
    if "svg" in text:
        return "forbidden_mime"
    if "png" in text or "jpeg" in text or "webp" in text or "magic" in text:
        return "unsupported_mime"
    return "invalid_logo"


def _persist_day1_logo_bytes(
    *,
    school: Any,
    image_bytes: bytes,
    ext: str,
) -> tuple[str, str]:
    """Persist ``image_bytes`` to default storage under the tenant prefix.

    Returns ``(storage_path, public_url)``. The storage path is keyed off
    ``school.pk`` ONLY — never any caller-supplied identifier — so a
    cross-tenant POST cannot trick the writer into landing bytes under a
    foreign tenant.
    """
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    from apps.platform_runtime.storage import (  # local import keeps service importable in test stubs
        get_storage_url,
        tenant_media_path,
    )

    safe_ext = (ext or "png").lstrip(".").lower()
    if safe_ext not in {"png", "jpg", "webp"}:
        safe_ext = "png"
    storage_path = tenant_media_path(getattr(school, "pk", None), f"brand/logo.{safe_ext}")
    if default_storage.exists(storage_path):
        default_storage.delete(storage_path)
    # tenant-isolation-allow: day1-logo-upload-storage-keyed-on-school-pk-only
    default_storage.save(storage_path, ContentFile(image_bytes))
    return storage_path, get_storage_url(storage_path)


# ---------------------------------------------------------------------------
# Internal — SiteSettings mirror
# ---------------------------------------------------------------------------


def _mirror_to_site_settings(school: Any, chosen: PaletteVariation) -> None:
    """Write the resolved palette to the tenant's ``SiteSettings`` row.

    Lazy-imports the model so the day-1 service stays importable even if the
    siteconfig app graph shifts. Tenant isolation is preserved because we
    filter on ``school=school`` and ``update_or_create`` does the right thing
    — never crosses the school FK.
    """
    try:
        from apps.platform_runtime.helpers import update_school_site_settings_record
    except Exception:
        return

    payload_updates: dict[str, Any] = {}
    primary = chosen.stops.get("primary")
    accent = chosen.stops.get("primary_soft") or chosen.stops.get("primary_strong")
    if primary:
        payload_updates["primary_color"] = primary
    if accent:
        payload_updates["accent_color"] = accent

    if not payload_updates:
        return

    try:
        # tenant-isolation-allow: day1-palette-mirror-scoped-to-single-school-fk
        update_school_site_settings_record(school, payload_updates)
    except Exception:
        logger.warning(
            "day1: SiteSettings mirror failed tenant=%s — palette landed on School.branding_metadata only",
            _school_log_label(school),
        )

"""Canonical operational strands + code-prefix helpers for signup provisioning.

Maps hybrid multi-track intents onto existing Setup Studio curriculum-track
codes and ``Specialty`` rows. Rejects unknown codes instead of inventing a
parallel W31_* schema.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from django.utils.translation import gettext_lazy as _

# Setup Studio track codes (apps.setup_studio.wizard_resolvers.list_curriculum_tracks).
CURRICULUM_TRACK_CODES: frozenset[str] = frozenset(
    {
        "ib_diploma",
        "ib_myp",
        "ib_pyp",
        "cambridge_a_levels",
        "cambridge_igcse",
        "ap_advanced_placement",
        "local_k12",
        "local_ministry_track",
        "vocational_trade",
        "montessori",
        "cbse_in",
        "icse_in",
        "state_board_in",
        "bac_general_fr",
        "bac_d_cm",
        "gce_o_a_cm",
        "abitur_de",
        "matura_eu",
    }
)

# Operational strands shown on public signup (checkbox group).
OPERATIONAL_STRAND_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "code": "local_k12",
        "label": _("General Academic K-12"),
        "hint": _("Baseline academic programme."),
        "glyph": "K12",
        "curriculum_track": "local_k12",
        "specialty_name": "",  # uses the canonical General specialty
        "default": True,
    },
    {
        "code": "vocational_trade",
        "label": _("Technical / Vocational (TVET)"),
        "hint": _("Trade and technical pathways alongside academics."),
        "glyph": "TVET",
        "curriculum_track": "vocational_trade",
        "specialty_name": "Technical / Vocational (TVET)",
        "default": False,
    },
    {
        "code": "vocational_apprenticeship",
        "label": _("Trade Apprenticeship"),
        "hint": _("Dual apprenticeship / workplace training."),
        "glyph": "APP",
        "curriculum_track": "vocational_trade",
        "specialty_name": "Trade Apprenticeship",
        "default": False,
    },
    {
        "code": "special_education",
        "label": _("Special Education (IEP/SEND)"),
        "hint": _("Accommodations and specialised support tracks."),
        "glyph": "SEND",
        "curriculum_track": "local_ministry_track",
        "specialty_name": "Special Education",
        "default": False,
    },
)

_STRAND_BY_CODE: dict[str, dict[str, Any]] = {
    str(item["code"]): item for item in OPERATIONAL_STRAND_CATALOG
}

# Marketing / paste aliases → canonical strand codes.
_STRAND_ALIASES: dict[str, str] = {
    "w31_general_k12": "local_k12",
    "w32_tvet": "vocational_trade",
    "w33_trade_apprenticeship": "vocational_apprenticeship",
    "w40_special_education": "special_education",
    "k12": "local_k12",
    "tvet": "vocational_trade",
    "apprenticeship": "vocational_apprenticeship",
    "iep": "special_education",
    "send": "special_education",
}

_CODE_PREFIX_RE = re.compile(r"^[A-Z0-9]{2,8}$")
CODE_PREFIX_MAX_LEN = 8
CODE_PREFIX_MIN_LEN = 2

_BOARD_TO_TRACK: dict[str, str] = {
    "ib": "ib_diploma",
    "cambridge": "cambridge_igcse",
    "national-default": "local_ministry_track",
    "national": "local_ministry_track",
}


@dataclass(frozen=True)
class ProvisionSeedInputs:
    education_cycles: list[str]
    strands: list[str]
    curriculum_tracks: list[str]
    code_prefix: str


def signup_operational_strand_options() -> list[dict[str, Any]]:
    """Template-safe catalog (lazy labels resolve at render)."""
    return [dict(item) for item in OPERATIONAL_STRAND_CATALOG]


def normalize_code_prefix(raw: Any) -> str:
    """Uppercase alphanumeric prefix; empty when too short or invalid."""
    compact = "".join(ch for ch in str(raw or "").upper() if ch.isalnum())
    compact = compact[:CODE_PREFIX_MAX_LEN]
    if not _CODE_PREFIX_RE.match(compact):
        return ""
    if len(compact) < CODE_PREFIX_MIN_LEN:
        return ""
    return compact


def canonicalize_strand_code(raw: Any) -> str:
    token = str(raw or "").strip().lower().replace("-", "_")
    if not token:
        return ""
    if token in _STRAND_ALIASES:
        token = _STRAND_ALIASES[token]
    if token in _STRAND_BY_CODE:
        return token
    if token in CURRICULUM_TRACK_CODES:
        return token
    return ""


def parse_operational_strands(raw: Iterable[Any] | None) -> list[str]:
    out: list[str] = []
    for item in raw or []:
        code = canonicalize_strand_code(item)
        if code and code not in out:
            out.append(code)
    return out


def curriculum_tracks_for_strands(strands: Iterable[str]) -> list[str]:
    tracks: list[str] = []
    for code in strands:
        meta = _STRAND_BY_CODE.get(code)
        if meta:
            track = str(meta.get("curriculum_track") or "").strip()
            if track and track not in tracks:
                tracks.append(track)
        elif code in CURRICULUM_TRACK_CODES and code not in tracks:
            tracks.append(code)
    return tracks


def curriculum_tracks_for_board(board: str) -> list[str]:
    token = str(board or "").strip().lower()
    if not token:
        return []
    if token in CURRICULUM_TRACK_CODES:
        return [token]
    mapped = _BOARD_TO_TRACK.get(token, "")
    return [mapped] if mapped else []


def strand_specialty_specs(strands: Iterable[str]) -> list[tuple[str, str]]:
    """Return ``(code_slug, display_name)`` for strands that need their own Specialty."""
    specs: list[tuple[str, str]] = []
    for code in strands:
        meta = _STRAND_BY_CODE.get(code)
        if meta:
            name = str(meta.get("specialty_name") or "").strip()
            if name:
                specs.append((code, name))
            continue
        if code in CURRICULUM_TRACK_CODES:
            specs.append((code, code.replace("_", " ").title()))
    return specs


def _unique_str_list(raw: Any) -> list[str]:
    values: list[str] = []
    if isinstance(raw, str):
        raw = [part for part in raw.replace(",", "|").split("|") if part.strip()]
    if not isinstance(raw, (list, tuple, set)):
        return values
    for item in raw:
        token = str(item or "").strip()
        if token and token not in values:
            values.append(token)
    return values


def resolve_provision_seed_inputs(school: Any) -> ProvisionSeedInputs:
    settings = dict(getattr(school, "settings", None) or {})
    loc = dict(settings.get("localization") or {})
    intent = dict(settings.get("onboarding_intent") or {})
    profile = dict(intent.get("institution_profile") or {})

    cycles = _unique_str_list(loc.get("education_cycles") or intent.get("education_cycles"))
    if not cycles:
        raw_types = str(
            settings.get("school_type")
            or settings.get("school_type_raw")
            or loc.get("school_type_code")
            or ""
        ).strip()
        cycles = _unique_str_list(raw_types)

    strands = parse_operational_strands(
        loc.get("operational_strands")
        or intent.get("operational_strands")
        or profile.get("operational_strands")
        or []
    )
    tracks = _unique_str_list(
        loc.get("curriculum_tracks") or intent.get("curriculum_tracks")
    )
    if not tracks:
        tracks = curriculum_tracks_for_strands(strands)
        board = str(
            profile.get("curriculum_board") or loc.get("curriculum_board") or ""
        )
        for extra in curriculum_tracks_for_board(board):
            if extra not in tracks:
                tracks.append(extra)

    prefix = normalize_code_prefix(
        loc.get("code_prefix") or intent.get("code_prefix") or ""
    )
    return ProvisionSeedInputs(
        education_cycles=cycles,
        strands=strands,
        curriculum_tracks=tracks,
        code_prefix=prefix,
    )


def namespaced_structure_code(school: Any, *parts: Any) -> str:
    """School-scoped code, optionally prefixed; always ≤30 chars (global unique).

    Empty prefix preserves historical ``GEN-{id8}`` / ``SPEC-GEN-{id8}`` order
    (type tokens first, school id last). A custom prefix is prepended.
    """
    sid = str(getattr(school, "id", "") or "").replace("-", "")[:8]
    prefix = resolve_provision_seed_inputs(school).code_prefix
    tokens: list[str] = []
    for part in parts:
        token = "".join(ch if ch.isalnum() else "-" for ch in str(part or "").upper())
        token = token.strip("-")[:12]
        if token:
            tokens.append(token)
    if prefix:
        bits = [prefix, *tokens]
        if sid:
            bits.append(sid)
    else:
        bits = [*tokens]
        if sid:
            bits.append(sid)
    return "-".join(bits)[:30]

"""
Bridge signup / school localization settings into Migration Cloud mapping.

Reads ``signup_locale_context`` stamped on draft bundles (and falls back to
``school.settings``) so CSV column headers in local languages map cleanly
without extra AI calls.
"""

from __future__ import annotations

import re
from typing import Any

from apps.siteconfig.country_localization_service import get_terminology, normalize_country_code

# Canonical field → terminology key in country packs.
_TERMINOLOGY_FIELD_MAP: dict[tuple[str, str], str] = {
    ("students", "grade_level"): "grade_level",
    ("grades", "term"): "term",
    ("grades", "score"): "score",
    ("students", "external_id"): "external_id",
}


def resolve_signup_locale_context(bundle) -> dict[str, Any]:
    """Best-effort locale context for a migration bundle."""
    if bundle is None:
        return {}
    snap = getattr(bundle, "progress_snapshot", None) or {}
    if isinstance(snap, dict):
        ctx = snap.get("signup_locale_context")
        if isinstance(ctx, dict) and ctx:
            return dict(ctx)
    school = getattr(bundle, "school", None)
    if school is None:
        return {}
    settings = getattr(school, "settings", None) or {}
    if not isinstance(settings, dict):
        return {}
    intent = settings.get("migration_intent") or {}
    if isinstance(intent, dict):
        ctx = intent.get("locale_context")
        if isinstance(ctx, dict) and ctx:
            return dict(ctx)
    loc = settings.get("localization") or {}
    if isinstance(loc, dict) and loc:
        return {
            "country_code": str(loc.get("country_code") or ""),
            "language_code": str(loc.get("language_code") or ""),
            "calendar_code": str(loc.get("calendar_code") or ""),
            "education_cycles": list(loc.get("education_cycles") or []),
            "school_type_code": str(loc.get("school_type_code") or ""),
        }
    return {}


def _split_bilingual_label(raw: str) -> list[str]:
    parts = re.split(r"[/·|]", raw or "")
    out: list[str] = []
    for part in parts:
        text = part.strip()
        if not text:
            continue
        out.append(text.lower().replace(" ", "_"))
        out.append(text.strip())
    return out


def extra_synonyms_for_canonical(
    bundle,
    *,
    canonical_field: str,
    domain: str,
) -> list[str]:
    """Signup-aware synonyms merged into mapper layer 1."""
    ctx = resolve_signup_locale_context(bundle)
    cc = normalize_country_code(ctx.get("country_code"))
    if not cc:
        return []
    term_key = _TERMINOLOGY_FIELD_MAP.get((domain, canonical_field))
    if not term_key:
        return []
    terminology = get_terminology(cc)
    raw = str(terminology.get(term_key) or ctx.get("term_label") or "").strip()
    if not raw:
        return []
    extras: list[str] = []
    for token in _split_bilingual_label(raw):
        normalized = re.sub(r"[^a-z0-9\u0080-\uffff]+", "_", token.lower()).strip("_")
        if normalized:
            extras.append(normalized)
        if token and token not in extras:
            extras.append(token)
    return list(dict.fromkeys(extras))

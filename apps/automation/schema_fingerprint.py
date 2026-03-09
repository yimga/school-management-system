"""
Schema fingerprint / profile detection: suggest MigrationProfile from column headers.
Returns profiles with confidence score so wizard can auto-load or suggest.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.automation.models import MigrationProfile


def _normalize(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"[\s_\-]+", "_", str(s).strip().lower()).strip("_")


def suggest_profiles_from_headers(
    headers: list[str],
    *,
    domain: str | None = None,
    min_confidence: float = 0.0,
):
    """
    Score active MigrationProfiles with schema_hints against the given column headers.
    Returns list of (profile, confidence) sorted by confidence descending.
    confidence in [0, 1]: fraction of profile's hint keys that appear in normalized headers.
    If domain is set, only consider profiles with that domain.
    """
    from apps.automation.models import MigrationProfile

    if not headers:
        return []
    header_set = {_normalize(h) for h in headers if _normalize(h)}

    qs = MigrationProfile.objects.filter(is_active=True)
    if domain:
        qs = qs.filter(domain=domain)
    profiles = list(qs)

    scored = []
    for profile in profiles:
        hints = (profile.config or {}).get("schema_hints") or {}
        if not hints:
            continue
        hint_keys_normalized = {_normalize(k) for k in hints}
        matches = len(hint_keys_normalized & header_set)
        if not hint_keys_normalized:
            continue
        confidence = matches / len(hint_keys_normalized)
        if confidence >= min_confidence:
            scored.append((profile, confidence))

    scored.sort(key=lambda x: -x[1])
    return scored

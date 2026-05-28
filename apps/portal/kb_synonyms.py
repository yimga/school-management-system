"""
Config-driven KB search synonym expansion (batch 1339).

Aliases are lowercase keys → extra search terms (not stored in DB).
"""

from __future__ import annotations

# Canonical synonym map — extend via SiteSettings ``kb_search_synonyms`` JSON overlay.
DEFAULT_KB_SYNONYMS: dict[str, list[str]] = {
    "enrolment": ["enrollment", "register", "registration"],
    "enrollment": ["enrolment", "register", "registration"],
    "timetable": ["schedule", "calendar", "period"],
    "schedule": ["timetable", "calendar", "period"],
    "gradebook": ["grades", "marks", "assessment"],
    "grades": ["gradebook", "marks", "report card"],
    "invoice": ["billing", "fees", "payment"],
    "billing": ["invoice", "fees", "payment"],
    "parent": ["guardian", "family"],
    "guardian": ["parent", "family"],
    "sso": ["single sign on", "login", "authentication"],
    "mfa": ["two factor", "2fa", "multi factor"],
    "api": ["developer", "integration", "webhook"],
    "offline": ["pwa", "sync", "queue"],
    "ferpa": ["privacy", "student data", "compliance"],
}


def _merged_synonyms() -> dict[str, list[str]]:
    merged = {k: list(v) for k, v in DEFAULT_KB_SYNONYMS.items()}
    try:
        from apps.platform_runtime.helpers import get_effective_flags_for_school

        raw = (get_effective_flags_for_school() or {}).get("kb_search_synonyms")
        if isinstance(raw, dict):
            for key, vals in raw.items():
                if not key or not isinstance(vals, list):
                    continue
                merged[str(key).lower()] = [str(v).lower() for v in vals if v]
    except (AttributeError, ImportError, LookupError, TypeError, ValueError):
        pass
    return merged


def expand_query_synonyms(query: str) -> str:
    """Append synonym terms to the query string for ranked / icontains search."""
    q = (query or "").strip()
    if not q:
        return q
    table = _merged_synonyms()
    extra: list[str] = []
    for token in q.lower().split():
        for alt in table.get(token, []):
            if alt not in extra and alt not in q.lower():
                extra.append(alt)
    if not extra:
        return q
    return f"{q} {' '.join(extra)}"

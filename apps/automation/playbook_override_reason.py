"""
Normalized operator override reason for migration playbook preflight (release readiness bucket B).

Strips invisible / format characters so a "\u200b"-only string cannot bypass the low-confidence gate.
"""

from __future__ import annotations

import re

_OVERRIDE_REASON_INVISIBLE_CHARS_RE = re.compile(
    r"[\u200b\u200c\u200d\u2060\ufeff]+"
)


def normalize_playbook_override_reason(raw: str | None) -> str:
    """
    Strip visible whitespace, remove invisible format chars, cap length.
    Prevents zero-width-only "reasons" from satisfying the low-confidence override gate.
    """
    s = (raw or "").strip()[:400]
    s = _OVERRIDE_REASON_INVISIBLE_CHARS_RE.sub("", s)
    return s.strip()[:400]

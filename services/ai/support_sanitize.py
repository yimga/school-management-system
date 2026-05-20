"""
FERPA/COPPA-oriented preprocessing for support assistant queries and history.
"""

from __future__ import annotations

import re

from services.ai_center.redaction import redact_sensitive_text

_GRADE_RE = re.compile(
    r"\b(grade|gpa|score|mark)\s*[:=]?\s*\d{1,3}(?:\.\d+)?\b",
    re.IGNORECASE,
)
_STUDENT_ID_RE = re.compile(
    r"\b(student\s*id|learner\s*id|pupil\s*id)\s*[:=]?\s*[A-Za-z0-9\-]{4,}\b",
    re.IGNORECASE,
)
_DOB_RE = re.compile(
    r"\b(dob|date\s*of\s*birth|birth\s*date)\s*[:=]?\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b",
    re.IGNORECASE,
)


def sanitize_support_query(text: str, *, max_len: int = 8000) -> str:
    """
    Strip PII/secrets before RAG retrieval and Ollama prompts.
    Composes AI Center redaction with education-specific markers.
    """
    raw = (text or "").strip()[:max_len]
    if not raw:
        return ""
    out = redact_sensitive_text(raw)
    try:
        from services.ai_helpers import looks_like_pii, redact_pii

        if looks_like_pii(out):
            out = redact_pii(out)
    except ImportError:
        pass
    out = _GRADE_RE.sub("[REDACTED_GRADE]", out)
    out = _STUDENT_ID_RE.sub("[REDACTED_STUDENT_ID]", out)
    out = _DOB_RE.sub("[REDACTED_DOB]", out)
    return out.strip()

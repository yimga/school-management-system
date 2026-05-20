"""PII/secret redaction for AI Center prompts and answers."""

from __future__ import annotations

import re

from services.ai_center.constants import SECRET_SUBSTRINGS

_API_KEY_RE = re.compile(
    r"\b(sk_live|sk_test|pk_live|pk_test|rk_live|whsec_|Bearer\s+)[A-Za-z0-9_\-]{8,}\b",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")


def redact_sensitive_text(text: str) -> str:
    """Strip likely secrets and emails from user-supplied text."""
    if not text:
        return ""
    out = text
    out = _API_KEY_RE.sub("[REDACTED]", out)
    out = _EMAIL_RE.sub("[REDACTED_EMAIL]", out)
    low = out.lower()
    for marker in SECRET_SUBSTRINGS:
        if marker in low and "=" in out:
            out = re.sub(
                rf"({marker}\s*[=:]\s*)(\S+)",
                r"\1[REDACTED]",
                out,
                flags=re.IGNORECASE,
            )
    return out

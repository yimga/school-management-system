"""Server-side PII masking for the operator review surfaces.

Staged migration data can carry national-id / SSN / date-of-birth / phone /
email / financial / medical values. The conflict-review screen renders whole
existing-vs-incoming record dicts, so those values must not reach a reviewer who
lacks an explicit reveal right — the raw value never leaves the server for an
unprivileged viewer. This is display-only masking; nothing here is persisted.

The detector mirrors ``profiler._looks_pii`` (name hints + SSN/email shapes) and
adds long-digit-run (id / account / card) and generic contact/financial/medical
key hints, biased toward over-masking a value we're unsure about.
"""

from __future__ import annotations

import re
from typing import Any

_PII_KEY_HINTS = (
    "ssn", "social", "national_id", "nationalid", "nid", "dob", "birth",
    "passport", "phone", "mobile", "tel", "email", "e_mail", "contact",
    "account", "iban", "card", "medical", "health", "diagnosis", "allerg",
    "salary", "income", "guardian_phone", "emergency",
)
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_LONG_DIGITS_RE = re.compile(r"\d{6,}")
_MASK = "•••• hidden"


def _looks_pii_key(key: Any) -> bool:
    k = str(key).lower()
    return any(h in k for h in _PII_KEY_HINTS)


def mask_value(key: Any, value: Any) -> Any:
    """Return the value, or a mask token if the key or value looks like PII."""
    if value is None or isinstance(value, bool):
        return value
    if _looks_pii_key(key):
        return _MASK
    s = str(value)
    if _EMAIL_RE.search(s) or _SSN_RE.search(s) or _LONG_DIGITS_RE.search(s):
        return _MASK
    return value


def mask_dict(data: Any) -> Any:
    """Mask every PII-looking entry of a flat record dict. Non-dicts pass through."""
    if not isinstance(data, dict):
        return data
    return {k: mask_value(k, v) for k, v in data.items()}

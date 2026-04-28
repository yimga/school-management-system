"""
Reliability helpers for idempotency and bounded retries.
"""

from __future__ import annotations

import hashlib
from typing import Any


def build_idempotency_key(*parts: Any) -> str:
    raw = "|".join(str(p or "") for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return digest[:48]


def should_retry_failure(*, attempt: int, max_attempts: int, error_code: str) -> bool:
    """
    Retry only transient classes and only within max_attempts.
    """
    if attempt >= max_attempts:
        return False
    return str(error_code).lower() in {
        "timeout",
        "temporarily_unavailable",
        "rate_limited",
        "db_locked",
    }


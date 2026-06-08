"""Session-scoped offline queue encryption key (batch 1651)."""

from __future__ import annotations

import base64
import hashlib
import hmac

from django.conf import settings


def derive_offline_queue_key(*, user_id: int | str, session_key: str) -> bytes:
    """Derive a 32-byte AES key for the current browser session (never logged)."""
    secret = (getattr(settings, "SECRET_KEY", "") or "dev-insecure").encode("utf-8")
    msg = f"rmc-offline-queue-v1:{user_id}:{session_key}".encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).digest()


def offline_queue_key_b64(*, user_id: int | str, session_key: str) -> str:
    return base64.b64encode(derive_offline_queue_key(user_id=user_id, session_key=session_key)).decode(
        "ascii"
    )

"""v4.00.95 Wave E5 — 24h short-link helpers for the share chip."""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


SHORT_LINK_TOKEN_BYTES = 16          # 22 base64-urlsafe chars
SHORT_LINK_DEFAULT_TTL_HOURS = 24
SHORT_LINK_MAX_TTL_HOURS = 168       # 7 days hard cap
SHORT_LINK_MAX_URL_LEN = 2048
SHORT_LINK_TOKEN_MAX_LEN = 32


def make_token() -> str:
    """Return a urlsafe random token of ``SHORT_LINK_TOKEN_BYTES`` bytes."""
    return secrets.token_urlsafe(SHORT_LINK_TOKEN_BYTES)[:SHORT_LINK_TOKEN_MAX_LEN]


def is_safe_target(url: str) -> bool:
    """Reject absolute URLs that leave the platform's own scheme/host.

    Allowed: site-relative paths (``/foo/``), or absolute URLs whose
    netloc matches one of the host suffixes the deployment trusts.
    """
    if not url:
        return False
    if url.startswith("/") and not url.startswith("//"):
        return True
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    try:
        from django.conf import settings

        allowed_hosts = getattr(settings, "ALLOWED_HOSTS", []) or []
    except (ImportError, RuntimeError):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    for entry in allowed_hosts:
        entry = (entry or "").lower().lstrip(".")
        if entry in ("", "*"):
            return True
        if host == entry or host.endswith("." + entry):
            return True
    return False


def mint_short_link(*, target_url: str, created_by, ttl_hours: int = SHORT_LINK_DEFAULT_TTL_HOURS):
    """Create a fresh AssistDockShortLink row + return the model instance.

    Returns ``(short_link, error_code)``. On rejection, ``short_link`` is
    None and ``error_code`` is a small machine-readable string.
    """
    try:
        from django.utils import timezone

        from .models import AssistDockShortLink
    except (ImportError, RuntimeError):
        return None, "models_unavailable"
    if created_by is None or not getattr(created_by, "pk", None):
        return None, "anonymous"
    if not target_url:
        return None, "target_required"
    if len(target_url) > SHORT_LINK_MAX_URL_LEN:
        return None, "target_too_long"
    if not is_safe_target(target_url):
        return None, "target_not_allowed"
    ttl = max(1, min(int(ttl_hours or SHORT_LINK_DEFAULT_TTL_HOURS), SHORT_LINK_MAX_TTL_HOURS))
    expires_at = timezone.now() + timedelta(hours=ttl)
    # Retry token allocation a couple of times in case of UNIQUE clash.
    for _ in range(3):
        token = make_token()
        try:
            # tenant-isolation-allow: assist-dock-short-link-mint-user-pk-public-schema-shared
            link = AssistDockShortLink.objects.create(
                token=token,
                target_url=target_url,
                created_by=created_by,
                expires_at=expires_at,
            )
            return link, ""
        except Exception as exc:  # noqa: BLE001 — token clash or backend down
            logger.debug("short link mint attempt failed: %s", exc)
            continue
    return None, "mint_failed"


def resolve_short_link(token: str):
    """Return the AssistDockShortLink row if valid + non-expired."""
    if not token:
        return None
    try:
        from django.utils import timezone

        from .models import AssistDockShortLink
    except (ImportError, RuntimeError):
        return None
    try:
        # tenant-isolation-allow: assist-dock-short-link-resolve-token-public-schema-shared
        link = AssistDockShortLink.objects.filter(token=token[:SHORT_LINK_TOKEN_MAX_LEN]).first()
    except Exception as exc:  # noqa: BLE001
        logger.debug("short link resolve failed: %s", exc)
        return None
    if link is None:
        return None
    if link.expires_at and link.expires_at < timezone.now():
        return None
    return link


def record_short_link_hit(link) -> None:
    """Increment hit counter — best-effort, never raises."""
    if link is None:
        return
    try:
        from django.db.models import F

        type(link).objects.filter(pk=link.pk).update(hits=F("hits") + 1)
    except Exception as exc:  # noqa: BLE001
        logger.debug("short link hit increment failed: %s", exc)


__all__ = [
    "SHORT_LINK_TOKEN_BYTES",
    "SHORT_LINK_DEFAULT_TTL_HOURS",
    "SHORT_LINK_MAX_TTL_HOURS",
    "SHORT_LINK_MAX_URL_LEN",
    "make_token",
    "is_safe_target",
    "mint_short_link",
    "resolve_short_link",
    "record_short_link_hit",
]

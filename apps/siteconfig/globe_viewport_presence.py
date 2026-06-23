"""Globe viewport presence — operators viewing the same map region (W17).

Uses Django cache (Redis when configured) keyed by ``operator:globe:viewport:{region_hash}``.
No raw slugs or emails in keys or payloads — user ids are hashed.
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)

GLOBE_PRESENCE_TTL = 90  # magic-number-allow: globe-viewport-presence-ttl-seconds
GLOBE_PRESENCE_HEARTBEAT = 30  # magic-number-allow: globe-viewport-presence-heartbeat-seconds
_CACHE_PREFIX = "rmc:globe:presence:v1:"


def compute_region_hash(
    *,
    region: str = "",
    lat: float | None = None,
    lng: float | None = None,
    altitude: float | None = None,
) -> str:
    """Stable viewport bucket for presence (region-first, else coarse lat/lng grid)."""
    region_norm = (region or "").strip().lower()
    if region_norm:
        raw = f"region:{region_norm}"
    elif lat is not None and lng is not None:
        # ~110km grid at equator — enough to group "same view" without GPS precision.
        grid_lat = round(float(lat) * 2) / 2
        grid_lng = round(float(lng) * 2) / 2
        alt = round(float(altitude or 1.02), 2)
        raw = f"grid:{grid_lat:.1f}:{grid_lng:.1f}:{alt}"
    else:
        raw = "global"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _user_token(user_id: int) -> str:
    return hashlib.sha256(f"globe-presence:{user_id}".encode()).hexdigest()[:16]


def _cache_key(region_hash: str) -> str:
    return f"{_CACHE_PREFIX}{region_hash}"


def _load_bucket(region_hash: str) -> dict[str, float]:
    try:
        raw = cache.get(_cache_key(region_hash))
        if isinstance(raw, dict):
            return {str(k): float(v) for k, v in raw.items()}
    except Exception:
        logger.debug("globe_presence: cache read failed", exc_info=True)
    return {}


def _save_bucket(region_hash: str, bucket: dict[str, float]) -> None:
    try:
        cache.set(_cache_key(region_hash), bucket, timeout=GLOBE_PRESENCE_TTL)
    except Exception:
        logger.debug("globe_presence: cache write failed", exc_info=True)


def _prune(bucket: dict[str, float], now: float) -> dict[str, float]:
    cutoff = now - GLOBE_PRESENCE_TTL
    return {token: ts for token, ts in bucket.items() if ts >= cutoff}


def heartbeat_globe_viewport(
    *,
    user_id: int,
    region_hash: str,
) -> dict[str, Any]:
    """Record operator heartbeat; return viewer count for the region bucket."""
    if not user_id or not region_hash:
        return {"region_hash": region_hash or "", "viewers": 0, "heartbeat_seconds": GLOBE_PRESENCE_HEARTBEAT}
    now = time.time()
    bucket = _prune(_load_bucket(region_hash), now)
    bucket[_user_token(user_id)] = now
    _save_bucket(region_hash, bucket)
    return {
        "region_hash": region_hash,
        "viewers": len(bucket),
        "heartbeat_seconds": GLOBE_PRESENCE_HEARTBEAT,
    }


def count_globe_viewport_viewers(
    *,
    region_hash: str,
    exclude_user_id: int | None = None,
) -> int:
    """Count active viewers in a viewport bucket (optionally excluding self)."""
    if not region_hash:
        return 0
    now = time.time()
    bucket = _prune(_load_bucket(region_hash), now)
    if not exclude_user_id:
        return len(bucket)
    self_token = _user_token(exclude_user_id)
    return sum(1 for token in bucket if token != self_token)

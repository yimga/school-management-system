"""Edge cache integration (v4.00.0).

Two responsibilities:

  1. ``surrogate_key_for(view_name, **kwargs)`` — canonical builder used by
     runtime endpoints to stamp ``Surrogate-Key`` headers on responses. The
     edge Worker (edge/src/worker.js) buckets its KV by this key.
  2. ``purge_surrogate_keys(keys)`` — signed HMAC POST to the Worker's
     ``/edge/_purge`` endpoint. Fires from RuntimeDefaults / SiteSettings
     post-save signals so the edge invalidates within one RTT.

Settings consumed (all env-overridable, all optional):
  * ``RMC_EDGE_PURGE_URL``       — Worker purge endpoint, e.g. https://edge.runmycampus.com/edge/_purge
  * ``RMC_EDGE_PURGE_HMAC_KEY``  — shared secret matching ``EDGE_HMAC_SIGNING_KEY`` in wrangler.
  * ``RMC_EDGE_PURGE_TIMEOUT``   — float seconds, default 2.0.

The purge call is best-effort: if the edge is unreachable, the SWR fallback
on the Worker will revalidate within ``SWR_STALE_SECONDS`` anyway. Failures
log a WARNING but never propagate.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
from typing import Iterable

from django.conf import settings

logger = logging.getLogger(__name__)

CANONICAL_RUNTIME_PATHS: dict[str, str] = {
    "school_calendar": "/api/v1/runtime/calendar",
    "grading_matrix": "/api/v1/runtime/grading-matrix",
    "runtime_defaults": "/api/v1/runtime/defaults",
    "site_settings_snapshot": "/api/v1/runtime/site-settings",
    "feature_flags": "/api/v1/runtime/feature-flags",
}


def surrogate_key_for(*, tenant: str, view: str, viewport: str = "A") -> str:
    """Build the canonical Surrogate-Key for a runtime endpoint response.

    Must match exactly the key shape the Worker computes in buildSurrogateKey.
    """
    if not tenant:
        tenant = "_"
    path = CANONICAL_RUNTIME_PATHS.get(view, f"/api/v1/runtime/{view}")
    return f"{tenant}::{path}::v={viewport}"


def stamp_response(response, *, tenant: str, view: str, viewport: str = "A") -> None:
    """Attach ``Surrogate-Key`` + edge-friendly Cache-Control to a Django response.

    Idempotent. Safe to call from view code or from a middleware.
    """
    key = surrogate_key_for(tenant=tenant, view=view, viewport=viewport)
    existing = response.get("Surrogate-Key", "")
    response["Surrogate-Key"] = f"{existing} {key}".strip() if existing else key
    # Long edge TTL + short browser TTL — the Worker owns freshness.
    if "Cache-Control" not in response:
        response["Cache-Control"] = "public, max-age=15, s-maxage=900, stale-while-revalidate=300"


def purge_surrogate_keys(keys: Iterable[str]) -> bool:
    """Fire a signed purge POST to the edge Worker. Returns True on 2xx."""
    keys_list = sorted({k for k in keys if k})
    if not keys_list:
        return True
    purge_url = getattr(settings, "RMC_EDGE_PURGE_URL", "") or ""
    hmac_key = getattr(settings, "RMC_EDGE_PURGE_HMAC_KEY", "") or ""
    if not purge_url or not hmac_key:
        logger.debug("edge_cache.purge_skipped: RMC_EDGE_PURGE_URL or HMAC key unset")
        return False
    body = json.dumps({"surrogate_keys": keys_list}, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(hmac_key.encode("utf-8"), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        purge_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-RMC-Edge-Purge-Signature": sig,
        },
        method="POST",
    )
    timeout = float(getattr(settings, "RMC_EDGE_PURGE_TIMEOUT", 2.0))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        logger.warning("edge_cache.purge_failed: %s", exc)
        return False


def purge_tenant_runtime(tenant: str, views: Iterable[str] | None = None) -> bool:
    """Convenience: purge every runtime view for a tenant across all viewports."""
    target_views = list(views) if views else list(CANONICAL_RUNTIME_PATHS.keys())
    keys = [
        surrogate_key_for(tenant=tenant, view=v, viewport=vp)
        for v in target_views
        for vp in ("A", "B", "C")
    ]
    return purge_surrogate_keys(keys)

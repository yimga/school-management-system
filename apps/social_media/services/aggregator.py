"""Asynchronous feed aggregation with per-tenant cache isolation."""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from apps.social_media.models import SocialMediaIntegration
from apps.social_media.scope import integration_scope_key
from apps.social_media.services import providers, throttle

logger = logging.getLogger(__name__)


def _merge_feed(cache: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not fresh:
        return list(cache or [])
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for item in fresh + list(cache or []):
        key = str(item.get("id") or item.get("url") or item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged[:100]


def sync_integration_feed(integration: SocialMediaIntegration) -> dict[str, Any]:
    """
    Poll one integration and persist into ``feed_cache_json``.

    On 429 / throttle: returns cached feed without raising.
    On token failure: marks integration ``needs_reauth`` for that tenant only.
    """
    scope = integration_scope_key(integration)
    if not throttle.try_consume(scope, integration.provider):
        logger.warning(
            "social_feed_throttled_local",
            extra={"scope": scope, "provider": integration.provider},
        )
        return {
            "ok": True,
            "source": "cache",
            "items": list(integration.feed_cache_json or []),
            "throttled": True,
        }

    try:
        fresh = providers.fetch_feed_items(integration)
        merged = _merge_feed(integration.feed_cache_json or [], fresh)
        integration.feed_cache_json = merged
        integration.feed_cached_at = timezone.now()
        integration.needs_reauth = False
        integration.save(
            update_fields=["feed_cache_json", "feed_cached_at", "needs_reauth", "updated_at"]
        )
        return {"ok": True, "source": "live", "items": merged, "throttled": False}
    except providers.ProviderRateLimitError:
        logger.warning(
            "social_feed_provider_rate_limit",
            extra={"scope": scope, "provider": integration.provider},
        )
        return {
            "ok": True,
            "source": "cache",
            "items": list(integration.feed_cache_json or []),
            "throttled": True,
        }
    except providers.ProviderTokenExpiredError:
        integration.needs_reauth = True
        integration.save(update_fields=["needs_reauth", "updated_at"])
        return {
            "ok": False,
            "source": "cache",
            "items": list(integration.feed_cache_json or []),
            "needs_reauth": True,
        }
    except providers.ProviderNotConfiguredError:
        return {
            "ok": True,
            "source": "cache",
            "items": list(integration.feed_cache_json or []),
            "configured": False,
        }


def aggregate_scope_feeds(
    *,
    school_id=None,
    platform_scope: bool = False,
) -> list[dict[str, Any]]:
    """Merge all active integrations for a scope into a single timeline."""
    qs = SocialMediaIntegration.objects.filter(is_active=True)
    if platform_scope:
        qs = qs.filter(school__isnull=True)
    elif school_id:
        qs = qs.filter(school_id=school_id)
    else:
        return []

    timeline: list[dict[str, Any]] = []
    for integration in qs:
        result = sync_integration_feed(integration)
        for item in result.get("items") or []:
            enriched = dict(item)
            enriched.setdefault("provider", integration.provider)
            enriched.setdefault("handle", integration.handle)
            timeline.append(enriched)
    timeline.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return timeline[:50]


def read_cached_feed(
    *,
    school_id=None,
    platform_scope: bool = False,
) -> list[dict[str, Any]]:
    """Read-only path for UI — never calls external APIs."""
    qs = SocialMediaIntegration.objects.filter(is_active=True)
    if platform_scope:
        qs = qs.filter(school__isnull=True)
    elif school_id:
        qs = qs.filter(school_id=school_id)
    else:
        return []

    items: list[dict[str, Any]] = []
    for integration in qs:
        for item in integration.feed_cache_json or []:
            enriched = dict(item)
            enriched.setdefault("provider", integration.provider)
            items.append(enriched)
    items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return items[:50]

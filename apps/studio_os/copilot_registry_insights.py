"""Co-pilot ↔ governance-registry bridge (prototype, 2026-06-07).

Surfaces *operator-facing* governance state — the **Feature Gap Register**
(`apps.schools.feature_gap_register`) and the **Backlog Unlock Registry**
(`apps.platform_runtime.backlog_unlock_engine`) — as co-pilot rail items, so the
assistant can guide an operator through "what is shipped / broken" and "what is
ready / blocked next" instead of those registries living only on separate
dashboards. This is the first wire between the three previously-independent
surfaces (feature-gap, backlog, copilot).

Cheap + safe by construction:

  * **Feature-gap:** counts ``FeatureRow.status`` only — no per-row proof
    resolution (no ``reverse()`` / ``get_model()`` per row in a request).
  * **Backlog:** reads the CACHED evaluation snapshot only — it NEVER runs the
    gate scripts/pytest in a request (those run in the operator-triggered
    evaluation beat). No cache → no backlog item, rather than a slow eval.
  * **Operator-only:** returns ``[]`` unless ``request.user.is_staff``. These
    are platform-engineering governance surfaces, not tenant-facing data; the
    registries are platform-level (no per-tenant rows), so nothing
    tenant-specific is exposed.
  * **Never raises:** every failure logs at debug and yields ``[]`` so the rail
    payload is unaffected.

Toggle with ``settings.COPILOT_REGISTRY_INSIGHTS`` (default on).
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# Fallback snapshot cache key written by the backlog evaluation beat /
# `evaluate_backlog_unlocks` command (mirrors apps.schools.super_views_config).
_BACKLOG_SNAPSHOT_CACHE_KEY = "backlog_unlock:evaluation_snapshot:v1"


def _enabled() -> bool:
    return bool(getattr(settings, "COPILOT_REGISTRY_INSIGHTS", True))


def _safe_reverse(name: str) -> str:
    """reverse() that returns '' instead of raising on a host urlconf miss."""
    try:
        from django.urls import reverse

        return reverse(name)
    except Exception:  # noqa: BLE001 — cross-host urlconf may not expose the name
        return ""


def _feature_gap_item() -> dict[str, Any] | None:
    try:
        from apps.schools.feature_gap_register import iter_features

        rows = iter_features()
    except Exception:  # noqa: BLE001
        logger.debug("copilot_registry: feature-gap read failed", exc_info=True)
        return None
    counts = {"shipped": 0, "in_progress": 0, "planned": 0}
    total = 0
    for row in rows:
        total += 1
        status = str(getattr(row, "status", "shipped") or "shipped")
        counts[status] = counts.get(status, 0) + 1
    if not total:
        return None
    body = (
        f"{counts['shipped']} shipped · {counts['in_progress']} in progress · "
        f"{counts['planned']} planned."
    )
    return {
        "id": "registry-feature-gap",
        "title": "Capability register",
        "body": body,
        "source": "registry",
        "registry": "feature_gap",
        "url": _safe_reverse("manager_feature_gap_register"),
        "priority": 80,
    }


def _backlog_item() -> dict[str, Any] | None:
    try:
        from django.core.cache import cache

        snapshot = cache.get(_BACKLOG_SNAPSHOT_CACHE_KEY)
    except Exception:  # noqa: BLE001
        logger.debug("copilot_registry: backlog cache read failed", exc_info=True)
        return None
    # Deliberately do NOT evaluate here — the gate scripts are expensive and
    # operator-triggered. No cached snapshot means simply "nothing to show yet".
    if not isinstance(snapshot, dict):
        return None
    summary = snapshot.get("summary") or {}

    def _n(key: str) -> int:
        try:
            return int(summary.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0

    ready = _n("ready")
    attention = _n("ready_attention")
    waiting = _n("waiting")
    blocked = _n("blocked_external")
    body = (
        f"{ready} ready · {attention} need review · {waiting} waiting · "
        f"{blocked} blocked."
    )
    return {
        "id": "registry-backlog",
        "title": "Backlog unlocks",
        "body": body,
        "source": "registry",
        "registry": "backlog",
        "url": _safe_reverse("super:backlog_unlock_center"),
        "priority": 78,
    }


def build_registry_insights(request: Any) -> list[dict[str, Any]]:
    """Operator-facing governance items for the co-pilot rail.

    Returns ``[]`` for anonymous / non-staff users, when disabled, or when the
    registries cannot be read — never raises.
    """
    if not _enabled() or request is None:
        return []
    user = getattr(request, "user", None)
    if not getattr(user, "is_staff", False):
        return []  # platform governance is operator/super-only
    out: list[dict[str, Any]] = []
    for builder in (_feature_gap_item, _backlog_item):
        try:
            item = builder()
        except Exception:  # noqa: BLE001
            logger.debug("copilot_registry: builder failed", exc_info=True)
            item = None
        if item:
            out.append(item)
    return out


__all__ = ("build_registry_insights",)

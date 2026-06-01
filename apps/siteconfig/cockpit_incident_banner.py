"""Tier-3 incident banner resolution — PlatformIncident API first, ticker feed fallback."""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

_BANNER_SEVERITIES = frozenset({"danger", "warn", "warning"})


def _map_platform_incident_severity(raw: str) -> str | None:
    """Map PlatformIncident.Severity to Tier-3 banner severity (None = no banner)."""
    value = (raw or "").strip().lower()
    if value in {"critical", "high"}:
        return "danger"
    if value in {"medium", "warn", "warning"}:
        return "warn"
    return None


def _pick_activity_incident_banner(ticker_section: dict[str, Any]) -> dict[str, Any] | None:
    """First warn/danger card from a ticker section."""
    section = ticker_section or {}
    if not section.get("enabled", True):
        return None
    cards = section.get("cards") or []
    if not isinstance(cards, list):
        return None
    for card in cards:
        if not isinstance(card, dict):
            continue
        severity = str(card.get("severity") or "info").lower()
        if severity in _BANNER_SEVERITIES:
            out = dict(card)
            out["source"] = "activity_ticker"
            return out
    return None


def _incident_from_platform_strip(strip: dict[str, Any]) -> dict[str, Any] | None:
    tenant_items = strip.get("tenant_items") or []
    if tenant_items:
        row = tenant_items[0] if isinstance(tenant_items[0], dict) else {}
        banner_severity = _map_platform_incident_severity(str(row.get("severity") or ""))
        text = str(row.get("title") or "").strip()
        if banner_severity and text:
            return {
                "text": text,
                "severity": banner_severity,
                "timestamp": str(row.get("status") or ""),
                "source": "platform_incident",
            }
    if strip.get("fleet_generic"):
        return {
            "text": _(
                "Some services may be slower or unavailable. We are working on it."
            ),
            "severity": "warn",
            "timestamp": "",
            "source": "platform_incident_fleet",
        }
    return None


def _platform_incident_strip_for_request(request: HttpRequest) -> dict[str, Any]:
    school = getattr(request, "school", None)
    school_id = getattr(school, "pk", None) if school is not None else None
    from apps.observability.tenant_public_status import compute_platform_status_strip_bundle

    return compute_platform_status_strip_bundle(school_id)


def resolve_tenant_incident_banner(
    request: HttpRequest,
    tenant_cockpit: dict[str, Any],
) -> dict[str, Any] | None:
    """Tenant Tier-3 banner: PlatformIncident rows first, ticker warn/danger fallback."""
    try:
        strip = _platform_incident_strip_for_request(request)
        banner = _incident_from_platform_strip(strip)
        if banner:
            return banner
    except Exception:
        logger.debug("tenant incident banner: platform incident lookup failed", exc_info=True)
    return _pick_activity_incident_banner(tenant_cockpit.get("tenant_activity_ticker") or {})


def resolve_operator_incident_banner(
    request: HttpRequest,
    manager_cockpit: dict[str, Any],
) -> dict[str, Any] | None:
    """Operator Tier-3 banner: fleet PlatformIncident first, ticker fallback."""
    try:
        strip = _platform_incident_strip_for_request(request)
        banner = _incident_from_platform_strip(strip)
        if banner:
            return banner
    except Exception:
        logger.debug("operator incident banner: platform incident lookup failed", exc_info=True)
    ticker = manager_cockpit.get("activity_ticker") or {}
    banner = _pick_activity_incident_banner(ticker)
    if banner:
        return banner
    feed = manager_cockpit.get("activity_feed") or {}
    if feed.get("enabled") and feed.get("events"):
        for event in feed.get("events") or []:
            if not isinstance(event, dict):
                continue
            severity = str(event.get("severity") or "info").lower()
            if severity in _BANNER_SEVERITIES:
                return {
                    "text": str(event.get("text") or event.get("label") or ""),
                    "severity": severity,
                    "timestamp": str(event.get("time_label") or ""),
                    "source": "activity_feed",
                }
    return None

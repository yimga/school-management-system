"""Live Banner Studio — source registry, announcements, and card composition."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

_KIND_SEVERITY = {
    "info": "info",
    "alert": "warn",
    "emergency": "danger",
}

_AUDIENCE_ROLE_MAP = {
    "all": None,
    "parent": "PARENT",
    "teacher": "TEACHER",
    "student": "STUDENT",
    "staff": "ADMIN",
    "admin": "ADMIN",
}


def _registry_entry(
    source_id: str,
    label: str,
    host: str,
    *,
    default_enabled: bool = True,
) -> dict[str, Any]:
    return {
        "id": source_id,
        "label": label,
        "host": host,
        "default_enabled": default_enabled,
    }


LIVE_BANNER_SOURCE_REGISTRY: tuple[dict[str, Any], ...] = (
    _registry_entry("migration_audit", _("Migration audit events"), "manager"),
    _registry_entry("offboarding", _("Offboarding lifecycle events"), "manager"),
    _registry_entry("provisioning", _("New school provisioning"), "manager"),
    _registry_entry("pending_approval", _("Schools pending approval"), "manager"),
    _registry_entry("subscriptions", _("New tenant subscriptions"), "manager"),
    _registry_entry("webhook_failures", _("Webhook delivery failures"), "manager"),
    _registry_entry("migration_failures", _("Failed migration runs"), "manager"),
    _registry_entry("attendance", _("Attendance milestones"), "tenant"),
    _registry_entry("fees", _("Fee payments received"), "tenant"),
    _registry_entry("enrollments", _("New enrollments"), "tenant"),
    _registry_entry("communications", _("Messages sent"), "tenant"),
    _registry_entry("email_delivery", _("Emails delivered"), "tenant"),
)


def registry_entries_for_host(host: str) -> list[dict[str, Any]]:
    return [entry for entry in LIVE_BANNER_SOURCE_REGISTRY if entry["host"] == host]


def manager_source_choices() -> list[tuple[str, str]]:
    return [(entry["id"], str(entry["label"])) for entry in registry_entries_for_host("manager")]


def tenant_source_choices() -> list[tuple[str, str]]:
    return [(entry["id"], str(entry["label"])) for entry in registry_entries_for_host("tenant")]


def default_sources_enabled(host: str) -> frozenset[str]:
    return frozenset(
        entry["id"]
        for entry in registry_entries_for_host(host)
        if entry.get("default_enabled", True)
    )


def resolve_sources_enabled(raw: Any, host: str) -> frozenset[str]:
    """Resolve enabled source ids for a host.

    Missing/empty payload key → all defaults enabled.
    Explicit empty list → none enabled.
    """
    allowed = {entry["id"] for entry in registry_entries_for_host(host)}
    if raw is None:
        return default_sources_enabled(host)
    if isinstance(raw, dict):
        raw = raw.get(host)
    if raw is None:
        return default_sources_enabled(host)
    if not isinstance(raw, (list, tuple, set)):
        return default_sources_enabled(host)
    if len(raw) == 0:
        return frozenset()
    return frozenset(str(item) for item in raw if str(item) in allowed)


def sources_enabled_from_payload(payload: dict[str, Any] | None, host: str) -> frozenset[str]:
    payload = payload or {}
    activity = payload.get("activity_ticker") or {}
    tenant = payload.get("tenant_activity_ticker") or {}
    nested = activity.get("sources_enabled")
    if host == "tenant":
        tenant_raw = tenant.get("sources_enabled")
        if tenant_raw is not None:
            return resolve_sources_enabled(tenant_raw, host)
        if isinstance(nested, dict):
            return resolve_sources_enabled(nested.get("tenant"), host)
        return resolve_sources_enabled(None, host)
    if isinstance(nested, dict):
        return resolve_sources_enabled(nested.get("manager"), host)
    return resolve_sources_enabled(nested, host)


def sources_cache_suffix(enabled: frozenset[str]) -> str:
    if not enabled:
        return "none"
    digest = hashlib.sha256(",".join(sorted(enabled)).encode("utf-8")).hexdigest()
    return digest[:10]


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        if isinstance(value, datetime):
            dt = value
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.get_current_timezone())
        return dt
    except Exception:
        return None


def _request_role_code(request: Any) -> str:
    user = getattr(request, "user", None)
    role = getattr(user, "role", None)
    if role is None:
        return ""
    code = getattr(role, "value", None) or str(role)
    return str(code or "").upper()


def _announcement_visible_for_request(announcement: dict[str, Any], request: Any) -> bool:
    audiences = announcement.get("audiences") or ["all"]
    if not isinstance(audiences, (list, tuple)):
        audiences = [audiences]
    normalized = {str(item or "").strip().lower() for item in audiences if str(item or "").strip()}
    if not normalized or "all" in normalized:
        return True
    role_code = _request_role_code(request)
    if not role_code:
        return True
    for audience in normalized:
        mapped = _AUDIENCE_ROLE_MAP.get(audience)
        if mapped is None:
            return True
        if mapped == role_code:
            return True
    return False


def resolve_active_announcements(
    announcements: list[dict[str, Any]] | None,
    request: Any,
) -> list[dict[str, Any]]:
    """Filter announcements by schedule + audience; sort pinned emergencies first."""
    if not announcements:
        return []
    now = timezone.now()
    active: list[dict[str, Any]] = []
    for item in announcements:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        starts = _parse_iso(item.get("starts_at"))
        ends = _parse_iso(item.get("ends_at"))
        if starts and now < starts:
            continue
        if ends and now > ends:
            continue
        if not _announcement_visible_for_request(item, request):
            continue
        active.append(dict(item))
    active.sort(
        key=lambda row: (
            0 if row.get("pin") and row.get("kind") == "emergency" else 1,
            0 if row.get("pin") else 1,
            0 if row.get("kind") == "emergency" else 1,
            str(row.get("starts_at") or ""),
        )
    )
    return active


def announcements_to_cards(announcements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for ann in announcements:
        kind = str(ann.get("kind") or "info").lower()
        if kind not in _KIND_SEVERITY:
            kind = "info"
        severity = str(ann.get("severity") or _KIND_SEVERITY[kind]).lower()
        icon = str(ann.get("icon") or "").strip()
        if not icon:
            icon = "🚨" if kind == "emergency" else "📢"
        card = {
            "text": str(ann.get("text") or "").strip(),
            "timestamp": str(ann.get("timestamp") or ""),
            "icon": icon,
            "severity": severity,
            "source": "announcement",
            "kind": kind,
            "pin": bool(ann.get("pin")),
        }
        if kind == "emergency":
            card["aria_live"] = "assertive"
        cards.append(card)
    return cards


def compose_live_banner_cards(
    section: dict[str, Any],
    request: Any,
) -> list[dict[str, Any]]:
    """Merge order: pinned announcements → existing cards (realdata + manual)."""
    from .cockpit_activity_ticker_realdata import merge_activity_ticker_card_lists

    announcements = resolve_active_announcements(section.get("announcements"), request)
    ann_cards = announcements_to_cards(announcements)
    base_cards = section.get("cards") or []
    if not isinstance(base_cards, list):
        base_cards = []
    return merge_activity_ticker_card_lists(ann_cards, base_cards)


def finalize_live_banner_section(
    section: dict[str, Any],
    request: Any,
) -> dict[str, Any]:
    finalized = dict(section or {})
    finalized["cards"] = compose_live_banner_cards(finalized, request)
    return finalized


def build_live_banner_preview(section: dict[str, Any], request: Any) -> dict[str, Any]:
    cards = compose_live_banner_cards(section, request)
    enabled_sources = section.get("sources_enabled")
    if isinstance(enabled_sources, list):
        source_ids = enabled_sources
    elif isinstance(enabled_sources, dict):
        host = "manager" if getattr(request, "public_host_kind", None) == "manager" else "tenant"
        source_ids = list(enabled_sources.get(host) or [])
    else:
        source_ids = []
    return {
        "cards": cards[:8],
        "card_count": len(cards),
        "announcement_count": len(section.get("announcements") or []),
        "sources_enabled": source_ids,
        "enabled": section.get("enabled", True),
        "live_badge_label": section.get("live_badge_label") or _("LIVE"),
        "scroll_seconds": section.get("scroll_seconds") or 40,
    }


def suggest_live_banner_program(request: Any) -> dict[str, Any]:
    """Rules-first program suggestion (AI may enrich upstream)."""
    host = getattr(request, "public_host_kind", None)
    if host == "manager":
        return {
            "sources_enabled": {
                "manager": sorted(default_sources_enabled("manager")),
                "tenant": sorted(default_sources_enabled("tenant")),
            },
            "announcements": [],
            "scroll_seconds": 40,
            "live_badge_label": str(_("LIVE")),
        }
    return {
        "sources_enabled": {
            "manager": sorted(default_sources_enabled("manager")),
            "tenant": ["attendance", "communications", "fees"],
        },
        "announcements": [
            {
                "id": str(uuid.uuid4()),
                "kind": "info",
                "text": str(_("Welcome back — check today's priorities in your dashboard.")),
                "severity": "info",
                "pin": False,
                "audiences": ["all"],
            }
        ],
        "scroll_seconds": 40,
        "live_badge_label": str(_("LIVE")),
    }


def draft_emergency_announcement(request: Any, *, topic: str = "") -> dict[str, Any]:
    topic_text = (topic or "").strip() or str(_("Campus safety update"))
    return {
        "id": str(uuid.uuid4()),
        "kind": "emergency",
        "text": str(
            _("%(topic)s — follow instructions from school leadership immediately.")
            % {"topic": topic_text}
        ),
        "severity": "danger",
        "pin": True,
        "audiences": ["all"],
        "icon": "🚨",
    }


def validate_live_banner_program_payload(payload: dict[str, Any]) -> list[str]:
    """Return validation errors for a suggested program payload."""
    errors: list[str] = []
    sources = payload.get("sources_enabled")
    if sources is not None and not isinstance(sources, dict):
        errors.append("sources_enabled must be an object")
    if isinstance(sources, dict):
        for host in ("manager", "tenant"):
            values = sources.get(host)
            if values is None:
                continue
            if not isinstance(values, list):
                errors.append(f"sources_enabled.{host} must be a list")
                continue
            allowed = {entry["id"] for entry in registry_entries_for_host(host)}
            unknown = [value for value in values if value not in allowed]
            if unknown:
                errors.append(f"unknown {host} sources: {', '.join(unknown)}")
    announcements = payload.get("announcements")
    if announcements is not None:
        if not isinstance(announcements, list):
            errors.append("announcements must be a list")
        else:
            for index, item in enumerate(announcements):
                if not isinstance(item, dict):
                    errors.append(f"announcements[{index}] must be an object")
                    continue
                if not str(item.get("text") or "").strip():
                    errors.append(f"announcements[{index}].text is required")
                kind = str(item.get("kind") or "info").lower()
                if kind not in _KIND_SEVERITY:
                    errors.append(f"announcements[{index}].kind invalid")
    return errors


__all__ = [
    "LIVE_BANNER_SOURCE_REGISTRY",
    "announcements_to_cards",
    "build_live_banner_preview",
    "compose_live_banner_cards",
    "default_sources_enabled",
    "draft_emergency_announcement",
    "finalize_live_banner_section",
    "manager_source_choices",
    "registry_entries_for_host",
    "resolve_active_announcements",
    "resolve_sources_enabled",
    "sources_cache_suffix",
    "sources_enabled_from_payload",
    "suggest_live_banner_program",
    "tenant_source_choices",
    "validate_live_banner_program_payload",
]

"""Operational time wrappers per campus (Phase 4E)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.schools.models import School

OPERATIONAL_TIME_SETTINGS_KEY = "operational_time"


@dataclass(frozen=True)
class OperationalTimeProfile:
    timezone: str
    prayer_offset_minutes: int = 0
    swahili_clock: bool = False
    utc_storage: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "timezone": self.timezone,
            "prayer_offset_minutes": self.prayer_offset_minutes,
            "swahili_clock": self.swahili_clock,
            "utc_storage": self.utc_storage,
        }


def resolve_operational_time(school: "School | None") -> OperationalTimeProfile:
    """
    Resolve campus operational time profile from ``school.settings``.

    Falls back to Django settings timezone with UTC storage semantics.
    """
    from django.conf import settings as django_settings

    default_tz = str(getattr(django_settings, "TIME_ZONE", "UTC") or "UTC")
    if school is None:
        return OperationalTimeProfile(timezone=default_tz)

    settings_blob = getattr(school, "settings", None) or {}
    raw = settings_blob.get(OPERATIONAL_TIME_SETTINGS_KEY) if isinstance(settings_blob, dict) else None
    if not isinstance(raw, dict):
        return OperationalTimeProfile(timezone=default_tz)

    return OperationalTimeProfile(
        timezone=str(raw.get("timezone") or default_tz),
        prayer_offset_minutes=int(raw.get("prayer_offset_minutes") or 0),
        swahili_clock=bool(raw.get("swahili_clock")),
        utc_storage=bool(raw.get("utc_storage", True)),
    )

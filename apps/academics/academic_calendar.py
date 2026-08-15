"""Academic-calendar provenance + confirmation state (increment r).

The country term-date calendars shipped in ``country_term_calendars`` are
*representative* public-calendar approximations — a school's REAL term dates are
set annually and locally, so a seeded calendar is a sensible default, never
ministry-official truth. This module records, per school, WHICH cascade layer a
seeded calendar came from and lets an admin confirm it, so the product can be
honest: a representative default is surfaced as *"confirm or adjust these dates"*
before go-live, while a real admin/operator-supplied calendar (or a confirmed
one) is left alone.

State lives in ``School.settings['academic_calendar']`` (no migration — the same
JSON home ``term_windows`` overrides already use)::

    {
      "source": "curated" | "even_split" | "school" | "profile",
      "representative": bool,     # True → a shipped default, awaiting confirmation
      "confirmed_at": iso8601 | None,
      "confirmed_by": str | None,
    }

A school with NO such key (seeded before this shipped) reports
``representative=False`` / ``needs_confirmation=False`` — the nudge applies to new
seeds going forward and never retroactively nags a live tenant.
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "academic_calendar"

# Sources that represent a shipped DEFAULT (not real admin/operator-supplied data)
# and therefore warrant a "confirm your real dates" nudge.
_REPRESENTATIVE_SOURCES = frozenset({"curated", "even_split"})
_KNOWN_SOURCES = _REPRESENTATIVE_SOURCES | {"school", "profile"}


def _settings_dict(school) -> dict:
    raw = getattr(school, "settings", None)
    return raw if isinstance(raw, dict) else {}


def _persist(school, settings_map: dict, *, save: bool) -> None:
    """Assign ``settings`` back on the school and (optionally) save just that column.

    Only saves a persisted school — an unsaved instance is mutated in memory only,
    so callers in pure-resolution / test contexts never trigger an INSERT."""
    school.settings = settings_map
    if not save:
        return
    if getattr(getattr(school, "_state", None), "adding", True):
        return
    try:
        school.save(update_fields=["settings"])
    except Exception:  # noqa: BLE001 — a settings-save failure must never abort seeding
        logger.debug("academic_calendar: settings save failed", exc_info=True)


def record_calendar_provenance(school, source: str | None, *, save: bool = True) -> dict[str, Any]:
    """Record which cascade layer a school's seeded term calendar came from.

    ``source`` is the value from
    :func:`apps.academics.country_term_calendars.term_windows_source` (``None`` →
    the even split). Sets ``representative`` from the source and PRESERVES any
    existing ``confirmed_at`` / ``confirmed_by`` (re-seeding must not silently
    un-confirm a calendar an admin already signed off). Returns the stored entry."""
    if school is None:
        return {}
    normalized = (source or "").strip().lower() or "even_split"
    if normalized not in _KNOWN_SOURCES:
        normalized = "even_split"
    settings_map = dict(_settings_dict(school))
    prior = settings_map.get(_SETTINGS_KEY)
    prior = prior if isinstance(prior, dict) else {}
    entry = {
        "source": normalized,
        "representative": normalized in _REPRESENTATIVE_SOURCES,
        "confirmed_at": prior.get("confirmed_at"),
        "confirmed_by": prior.get("confirmed_by"),
    }
    settings_map[_SETTINGS_KEY] = entry
    _persist(school, settings_map, save=save)
    return entry


def calendar_confirmation_state(school) -> dict[str, Any]:
    """Return the school's academic-calendar confirmation state.

    Always returns a well-formed dict. A school with no recorded provenance reads
    as a non-representative, unconfirmed calendar (``needs_confirmation=False``) so
    existing tenants are never retroactively flagged."""
    entry = _settings_dict(school).get(_SETTINGS_KEY)
    entry = entry if isinstance(entry, dict) else {}
    representative = bool(entry.get("representative"))
    confirmed_at = entry.get("confirmed_at")
    confirmed = bool(confirmed_at)
    return {
        "source": entry.get("source"),
        "representative": representative,
        "confirmed": confirmed,
        "confirmed_at": confirmed_at,
        "confirmed_by": entry.get("confirmed_by"),
        "needs_confirmation": representative and not confirmed,
    }


def needs_calendar_confirmation(school) -> bool:
    """True when the school's calendar is a representative default not yet confirmed."""
    if school is None:
        return False
    return calendar_confirmation_state(school)["needs_confirmation"]


def confirm_calendar(school, user=None, *, save: bool = True) -> dict[str, Any]:
    """Mark the school's academic calendar as confirmed by an admin.

    Idempotent — re-confirming refreshes the timestamp. Keeps ``source`` /
    ``representative`` intact (the calendar is still a representative default; the
    school has simply attested that the dates are correct for them). Returns the
    updated state."""
    if school is None:
        return calendar_confirmation_state(school)
    settings_map = dict(_settings_dict(school))
    entry = settings_map.get(_SETTINGS_KEY)
    entry = dict(entry) if isinstance(entry, dict) else {}
    entry.setdefault("source", "curated")
    entry.setdefault("representative", True)
    entry["confirmed_at"] = timezone.now().isoformat()
    confirmed_by = None
    if user is not None:
        confirmed_by = str(getattr(user, "username", None) or getattr(user, "pk", None) or "") or None
    entry["confirmed_by"] = confirmed_by
    settings_map[_SETTINGS_KEY] = entry
    _persist(school, settings_map, save=save)
    return calendar_confirmation_state(school)

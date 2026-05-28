"""
Wind-down mode — reversible pre-purge state for tenant + operator surfaces.

When active:
- School remains addressable for export/download
- New enrollments / billing charges should be blocked (call sites check is_wind_down_mode)
- Banner shown on tenant shells
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def is_wind_down_mode(school) -> bool:
    if school is None:
        return False
    off = (getattr(school, "settings", None) or {}).get("offboarding") or {}
    if not isinstance(off, dict):
        return False
    if off.get("wind_down_mode"):
        return True
    status = str(off.get("self_service_status") or "").strip()
    return status in ("closure_requested", "scheduled", "wind_down")


def apply_wind_down_mode(school, *, actor=None, note: str = "") -> dict[str, Any]:
    """
    Enter wind-down: flag settings, deactivate via offboarding service, record spine.
    """
    from apps.lifecycle.unified_lifecycle import record_unified_transition, STATE_WIND_DOWN
    from apps.schools.tenant_offboarding import run_wind_down_deactivate

    raw = getattr(school, "settings", None) or {}
    if not isinstance(raw, dict):
        raw = {}
    off = dict(raw.get("offboarding") or {})
    off["wind_down_mode"] = True
    off["wind_down_at"] = datetime.now(tz=timezone.utc).isoformat()
    if note:
        off["wind_down_note"] = note[:200]
    raw["offboarding"] = off
    school.settings = raw
    school.save(update_fields=["settings", "updated_at"])

    outcome = run_wind_down_deactivate(school, actor=actor)
    try:
        record_unified_transition(
            school,
            STATE_WIND_DOWN,
            actor=actor,
            note=note or "wind_down_mode",
            payload={"source": "lifecycle.wind_down"},
        )
    except (ValueError, TypeError) as exc:
        logger.warning("wind_down.record_stage_failed err=%s", type(exc).__name__)

    return {"ok": True, "wind_down_mode": True, "deactivate": outcome}


def clear_wind_down_mode(school, *, actor=None) -> dict[str, Any]:
    """Exit wind-down when closure is cancelled (does not re-activate alone)."""
    raw = getattr(school, "settings", None) or {}
    if not isinstance(raw, dict):
        return {"ok": True, "cleared": False}
    off = dict(raw.get("offboarding") or {})
    if not off.get("wind_down_mode"):
        return {"ok": True, "cleared": False}
    off.pop("wind_down_mode", None)
    off.pop("wind_down_at", None)
    raw["offboarding"] = off
    school.settings = raw
    school.save(update_fields=["settings", "updated_at"])
    return {"ok": True, "cleared": True}


def wind_down_blocks_new_commerce(school) -> bool:
    """True when new invoices, fee generation, payments, or enrollments must be blocked."""
    if school is None:
        return False
    if is_wind_down_mode(school):
        return True
    off = (getattr(school, "settings", None) or {}).get("offboarding") or {}
    if isinstance(off, dict) and off.get("self_service_status") in (
        "closure_requested",
        "scheduled",
        "wind_down",
    ):
        return True
    return False

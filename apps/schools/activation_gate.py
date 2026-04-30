"""
Post-signup activation gate: school.settings['rmc_activation_gate']['pending'] forces
tenant ADMIN users through /activation/first-action/ until dismissed or first_action fires.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone


RMC_ACTIVATION_GATE_KEY = "rmc_activation_gate"


def school_activation_gate_pending(school) -> bool:
    if not school:
        return False
    st: dict[str, Any] = getattr(school, "settings", None) or {}
    ag = st.get(RMC_ACTIVATION_GATE_KEY) or {}
    return bool(ag.get("pending"))


def set_activation_gate_pending(school) -> None:
    """Call after self-service email verification + provisioning (new tenant admin path)."""
    if not school:
        return
    school.refresh_from_db(fields=["settings"])
    st = dict(school.settings or {})
    ag = dict(st.get(RMC_ACTIVATION_GATE_KEY) or {})
    ag["pending"] = True
    ag["set_at"] = timezone.now().isoformat()
    st[RMC_ACTIVATION_GATE_KEY] = ag
    school.settings = st
    school.save(update_fields=["settings", "updated_at"])


def clear_activation_gate(school) -> None:
    if not school:
        return
    school.refresh_from_db(fields=["settings"])
    st = dict(school.settings or {})
    ag = dict(st.get(RMC_ACTIVATION_GATE_KEY) or {})
    ag["pending"] = False
    ag["cleared_at"] = timezone.now().isoformat()
    st[RMC_ACTIVATION_GATE_KEY] = ag
    school.settings = st
    school.save(update_fields=["settings", "updated_at"])

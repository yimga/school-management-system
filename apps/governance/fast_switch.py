"""Shared-terminal fast profile switch (Phase 4E).

Optimized path for kiosk / shared devices: switches active context profile
without a full re-login when the operator pre-authenticated the session.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from apps.governance.context_profiles import (
    ACTIVE_PROFILE_SESSION_KEY,
    set_active_profile_session,
)

if TYPE_CHECKING:
    from django.http import HttpRequest

FAST_SWITCH_BUDGET_MS = 100


def fast_switch_profile(request: "HttpRequest", profile_id: int):
    """
    Switch active context profile with a sub-100ms local session write.

    Returns the activated ``SchoolContextProfile`` after ownership verification.
    """
    started = time.perf_counter()
    profile = set_active_profile_session(request, profile_id)
    elapsed_ms = (time.perf_counter() - started) * 1000
    request.session["rmc_fast_switch_last_ms"] = round(elapsed_ms, 2)
    if elapsed_ms > FAST_SWITCH_BUDGET_MS:
        # Honest telemetry — do not fail the switch for slow CI hosts.
        request.session["rmc_fast_switch_over_budget"] = True
    return profile


def list_fast_switch_candidates(request: "HttpRequest"):
    """Profiles available on this shared terminal for the signed-in user."""
    from apps.governance.context_profiles import list_profiles

    school = getattr(request, "school", None)
    qs = list_profiles(getattr(request, "user", None))
    if school is not None and getattr(school, "pk", None):
        qs = qs.filter(school=school)
    return qs.order_by("-is_default", "label")


def clear_fast_switch_session(request: "HttpRequest") -> None:
    request.session.pop(ACTIVE_PROFILE_SESSION_KEY, None)
    request.session.pop("rmc_fast_switch_last_ms", None)
    request.session.pop("rmc_fast_switch_over_budget", None)

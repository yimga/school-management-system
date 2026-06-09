"""
Unified tenant lifecycle — single resolver for operator + self-serve paths.

Canonical phases (public contract):
  draft → provisioning → activating → live → wind_down → closed → purged

Maps existing signals (School flags, provisioning events, lifecycle spine,
offboarding JSON) without replacing them — this module is the read/write
facade other surfaces call.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.lifecycle.models import SchoolLifecycleStage, TERMINAL_STAGES
from apps.lifecycle.services import current_stage, record_stage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical unified states
# ---------------------------------------------------------------------------
STATE_DRAFT = "draft"
STATE_PROVISIONING = "provisioning"
STATE_ACTIVATING = "activating"
STATE_LIVE = "live"
STATE_WIND_DOWN = "wind_down"
STATE_CLOSED = "closed"
STATE_PURGED = "purged"

ALL_UNIFIED_STATES: tuple[str, ...] = (
    STATE_DRAFT,
    STATE_PROVISIONING,
    STATE_ACTIVATING,
    STATE_LIVE,
    STATE_WIND_DOWN,
    STATE_CLOSED,
    STATE_PURGED,
)

CREATION_PATH_SELF_SERVE = "self_serve"
CREATION_PATH_OPERATOR = "operator"

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    STATE_DRAFT: frozenset({STATE_PROVISIONING, STATE_CLOSED}),
    STATE_PROVISIONING: frozenset({STATE_ACTIVATING, STATE_LIVE, STATE_CLOSED, STATE_DRAFT}),
    STATE_ACTIVATING: frozenset({STATE_LIVE, STATE_WIND_DOWN, STATE_CLOSED}),
    STATE_LIVE: frozenset({STATE_WIND_DOWN, STATE_CLOSED}),
    STATE_WIND_DOWN: frozenset({STATE_CLOSED, STATE_LIVE}),
    STATE_CLOSED: frozenset({STATE_PURGED, STATE_LIVE}),
    STATE_PURGED: frozenset(),
}


def _lifecycle_settings(school) -> dict:
    raw = getattr(school, "settings", None) or {}
    if not isinstance(raw, dict):
        return {}
    block = raw.get("lifecycle")
    return block if isinstance(block, dict) else {}


def get_creation_path(school) -> str:
    """How the tenant was created: self_serve (signup) or operator (rapid/super)."""
    path = (_lifecycle_settings(school).get("creation_path") or "").strip().lower()
    if path in (CREATION_PATH_SELF_SERVE, CREATION_PATH_OPERATOR):
        return path
    off = (getattr(school, "settings", None) or {}).get("rmc_public_onboarding")
    if isinstance(off, dict) and off:
        return CREATION_PATH_SELF_SERVE
    return CREATION_PATH_OPERATOR


def set_creation_path(school, path: str, *, save: bool = True) -> None:
    path = (path or "").strip().lower()
    if path not in (CREATION_PATH_SELF_SERVE, CREATION_PATH_OPERATOR):
        raise ValueError(f"invalid creation_path: {path!r}")
    raw = getattr(school, "settings", None) or {}
    if not isinstance(raw, dict):
        raw = {}
    block = dict(raw.get("lifecycle") or {})
    block["creation_path"] = path
    block.setdefault("creation_path_set_at", timezone.now().isoformat())
    raw["lifecycle"] = block
    school.settings = raw
    if save:
        school.save(update_fields=["settings", "updated_at"])


def _return_unified(school, payload: dict[str, Any]) -> dict[str, Any]:
    """Attach provisioning progress signals for Tenant 360 and owner surfaces."""
    if school is None:
        return payload
    try:
        from apps.schools.provisioning_progress import (
            _blocking_error,
            _latest_workflow_run,
            resolve_phase_flags,
        )

        payload.update(resolve_phase_flags(school))
        payload["blocking_error"] = _blocking_error(school, _latest_workflow_run(school))
    except ImportError:
        payload.setdefault("portal_ready", bool(getattr(school, "is_active", False)))
        payload.setdefault("phase_a_complete", bool(getattr(school, "is_active", False)))
        payload.setdefault("phase_b_step", None)
        payload.setdefault("phase_b_complete", False)
        payload.setdefault("blocking_error", None)
    return payload


def resolve_unified_lifecycle(school) -> dict[str, Any]:
    """
    Return unified state + reasons + hints for UI and automation.

    Keys: state, label, reasons, creation_path, provisioning_in_flight,
    wind_down_active, offboarding_status, spine_stage, can_launch, can_close,
    portal_ready, phase_a_complete, phase_b_step, blocking_error.
    """
    empty = {
        "state": STATE_DRAFT,
        "label": str(_("Draft")),
        "reasons": ["no_school"],
        "creation_path": CREATION_PATH_OPERATOR,
        "provisioning_in_flight": False,
        "wind_down_active": False,
        "offboarding_status": "",
        "spine_stage": None,
        "can_launch": False,
        "can_close": False,
    }
    if school is None:
        return empty

    reasons: list[str] = []
    spine = current_stage(school)
    creation_path = get_creation_path(school)

    from apps.schools.tenant_offboarding import (
        get_offboarding_snapshot,
        provisioning_in_flight,
    )

    try:
        off_snap = get_offboarding_snapshot(school)
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        off_snap = {}

    off_settings = (getattr(school, "settings", None) or {}).get("offboarding") or {}
    if not isinstance(off_settings, dict):
        off_settings = {}
    self_status = str(off_settings.get("self_service_status") or "").strip()
    wind_down_active = bool(
        off_settings.get("wind_down_mode")
        or off_snap.get("wind_down_mode")
        or self_status in ("closure_requested", "scheduled")
    )
    in_flight = provisioning_in_flight(school)

    if spine == SchoolLifecycleStage.Stage.OFFBOARDING_PURGED:
        return _return_unified(
            school,
            {
                "state": STATE_PURGED,
                "label": str(_("Purged")),
                "reasons": ["spine_purged"],
                "creation_path": creation_path,
                "provisioning_in_flight": False,
                "wind_down_active": False,
                "offboarding_status": self_status,
                "spine_stage": spine,
                "can_launch": False,
                "can_close": False,
            },
        )

    if getattr(school, "deleted_at", None):
        reasons.append("school_soft_deleted")
        return _return_unified(
            school,
            {
                "state": STATE_CLOSED,
                "label": str(_("Closed")),
                "reasons": reasons,
                "creation_path": creation_path,
                "provisioning_in_flight": in_flight,
                "wind_down_active": wind_down_active,
                "offboarding_status": self_status,
                "spine_stage": spine,
                "can_launch": False,
                "can_close": False,
            },
        )

    if not getattr(school, "is_active", True):
        if wind_down_active:
            reasons.append("school_inactive_wind_down")
            return _return_unified(
                school,
                {
                    "state": STATE_WIND_DOWN,
                    "label": str(_("Wind-down")),
                    "reasons": reasons,
                    "creation_path": creation_path,
                    "provisioning_in_flight": in_flight,
                    "wind_down_active": True,
                    "offboarding_status": self_status,
                    "spine_stage": spine,
                    "can_launch": False,
                    "can_close": True,
                },
            )
        if self_status:
            reasons.append("school_inactive_offboarding")
            return _return_unified(
                school,
                {
                    "state": STATE_CLOSED,
                    "label": str(_("Closed")),
                    "reasons": reasons,
                    "creation_path": creation_path,
                    "provisioning_in_flight": in_flight,
                    "wind_down_active": wind_down_active,
                    "offboarding_status": self_status,
                    "spine_stage": spine,
                    "can_launch": False,
                    "can_close": False,
                },
            )
        reasons.append("signup_or_trial_draft")
        return _return_unified(
            school,
            {
                "state": STATE_DRAFT,
                "label": str(_("Draft")),
                "reasons": reasons,
                "creation_path": creation_path,
                "provisioning_in_flight": in_flight,
                "wind_down_active": False,
                "offboarding_status": self_status,
                "spine_stage": spine,
                "can_launch": False,
                "can_close": False,
            },
        )

    if wind_down_active or spine in (
        SchoolLifecycleStage.Stage.OFFBOARDING_REQUESTED,
        SchoolLifecycleStage.Stage.OFFBOARDING_EXPORTED,
        SchoolLifecycleStage.Stage.OFFBOARDING_GRACE,
    ):
        reasons.append("wind_down_or_offboarding")
        return _return_unified(
            school,
            {
                "state": STATE_WIND_DOWN,
                "label": str(_("Wind-down")),
                "reasons": reasons,
                "creation_path": creation_path,
                "provisioning_in_flight": in_flight,
                "wind_down_active": True,
                "offboarding_status": self_status,
                "spine_stage": spine,
                "can_launch": False,
                "can_close": True,
            },
        )

    try:
        from apps.schools.provisioning_progress import resolve_portal_ready

        portal_ready = resolve_portal_ready(school)
    except ImportError:
        portal_ready = bool(getattr(school, "is_active", False))

    if in_flight or (
        not SchoolProvisioningEvent_completed(school)
        and not _is_live_spine(spine)
        and not portal_ready
    ):
        if not getattr(school, "is_active", True):
            reasons.append("inactive_while_provisioning")
        else:
            reasons.append("provisioning_in_flight")
        return _return_unified(
            school,
            {
                "state": STATE_PROVISIONING,
                "label": str(_("Provisioning")),
                "reasons": reasons,
                "creation_path": creation_path,
                "provisioning_in_flight": True,
                "wind_down_active": False,
                "offboarding_status": self_status,
                "spine_stage": spine,
                "can_launch": False,
                "can_close": False,
            },
        )

    if _is_live_spine(spine) or _is_live_by_signals(school):
        from apps.lifecycle.readiness import compute_unified_score

        readiness = compute_unified_score(school)
        can_launch = bool(readiness.launch_ready)
        return _return_unified(
            school,
            {
                "state": STATE_LIVE,
                "label": str(_("Live")),
                "reasons": reasons or ["operating"],
                "creation_path": creation_path,
                "provisioning_in_flight": False,
                "wind_down_active": False,
                "offboarding_status": self_status,
                "spine_stage": spine,
                "can_launch": can_launch,
                "can_close": True,
                "unified_score": readiness.unified_score,
            },
        )

    reasons.append("activating")
    from apps.lifecycle.readiness import compute_unified_score

    readiness = compute_unified_score(school)
    return _return_unified(
        school,
        {
            "state": STATE_ACTIVATING,
            "label": str(_("Activating")),
            "reasons": reasons,
            "creation_path": creation_path,
            "provisioning_in_flight": False,
            "wind_down_active": False,
            "offboarding_status": self_status,
            "spine_stage": spine,
            "can_launch": bool(readiness.launch_ready),
            "can_close": True,
            "unified_score": readiness.unified_score,
        },
    )


def _is_live_spine(spine: str | None) -> bool:
    if not spine:
        return False
    from apps.lifecycle.models import LIVE_STAGES

    return spine in LIVE_STAGES


def _is_live_by_signals(school) -> bool:
    from apps.schools.models import MarketingFunnelEvent

    sid = getattr(school, "pk", None)
    if not sid:
        return False
    if MarketingFunnelEvent.objects.filter(
        school_id=sid, event_type="first_result"
    ).exists():
        return True
    if MarketingFunnelEvent.objects.filter(
        school_id=sid, event_type="signup_completed"
    ).exists():
        from apps.platform_runtime.onboarding import get_school_onboarding_progress

        pct = int(get_school_onboarding_progress(school).get("percent") or 0)
        return pct >= 85
    return False


def SchoolProvisioningEvent_completed(school) -> bool:
    from apps.schools.models import SchoolProvisioningEvent

    return SchoolProvisioningEvent.objects.filter(
        school=school,
        event_type=SchoolProvisioningEvent.EventType.COMPLETED,
    ).exists()


def validate_unified_transition(from_state: str, to_state: str) -> bool:
    a = (from_state or "").strip().lower()
    b = (to_state or "").strip().lower()
    if a == b:
        return True
    if a not in ALL_UNIFIED_STATES or b not in ALL_UNIFIED_STATES:
        return False
    return b in _ALLOWED_TRANSITIONS.get(a, frozenset())


def record_unified_transition(
    school,
    to_state: str,
    *,
    actor=None,
    note: str = "",
    payload: Optional[dict] = None,
) -> None:
    """Best-effort spine write when unified state advances."""
    stage_map = {
        STATE_PROVISIONING: SchoolLifecycleStage.Stage.PROVISIONED,
        STATE_ACTIVATING: SchoolLifecycleStage.Stage.ONBOARDING_STARTED,
        STATE_LIVE: SchoolLifecycleStage.Stage.OPERATING,
        STATE_WIND_DOWN: SchoolLifecycleStage.Stage.OFFBOARDING_REQUESTED,
        STATE_CLOSED: SchoolLifecycleStage.Stage.OFFBOARDING_GRACE,
        STATE_PURGED: SchoolLifecycleStage.Stage.OFFBOARDING_PURGED,
    }
    stage = stage_map.get(to_state)
    if not stage:
        return
    if current_stage(school) in TERMINAL_STAGES and to_state != STATE_PURGED:
        return
    # Enforce the unified FSM before writing the spine. The validator
    # previously existed but was never wired into any write path (dead
    # code), so a buggy signal could record an illegal jump (e.g.
    # draft→purged). Resolve the current unified state and refuse the
    # write on an illegal transition — best-effort (log + skip), never
    # raise, to preserve this function's "best-effort spine write"
    # contract for its signal-layer callers.
    try:
        current_state = resolve_unified_lifecycle(school).get("state", STATE_DRAFT)
    except (RuntimeError, ValueError, TypeError, AttributeError):
        current_state = STATE_DRAFT
    if not validate_unified_transition(current_state, to_state):
        logger.warning(
            "unified lifecycle: refused illegal transition %s -> %s for school=%s",
            current_state,
            to_state,
            getattr(school, "pk", None),
        )
        return
    merged = dict(payload or {})
    merged["unified_state"] = to_state
    record_stage(school, stage, actor=actor, note=note or to_state, payload=merged)


def _billing_checklist_cleared(school, snap: dict) -> bool:
    from apps.lifecycle.billing_gate import check_billing_clearance

    clearance = check_billing_clearance(school)
    if clearance.state == "cleared":
        return True
    if clearance.state == "outstanding":
        return False
    off = snap.get("offboarding") if isinstance(snap.get("offboarding"), dict) else {}
    return bool(off.get("dual_approved") or snap.get("dual_approved"))


def _billing_checklist_detail(school) -> str:
    from apps.lifecycle.billing_gate import check_billing_clearance

    clearance = check_billing_clearance(school)
    if clearance.state == "cleared":
        return str(_("No outstanding balance."))
    if clearance.state == "outstanding":
        return clearance.reason
    return str(
        _(
            "Billing state unavailable — record dual approval or confirm zero balance."
        )
    )


def build_offboarding_checklist(school) -> list[dict[str, Any]]:
    """Operator checklist mirroring onboarding rail — used on Tenant 360."""
    from apps.schools.tenant_offboarding import get_offboarding_snapshot

    snap = get_offboarding_snapshot(school)
    off = (getattr(school, "settings", None) or {}).get("offboarding") or {}
    if not isinstance(off, dict):
        off = {}

    export_path = (off.get("last_export_zip_path") or "").strip()
    scheduled = (off.get("scheduled_purge_at") or "").strip()
    hold_until = (off.get("legal_hold_until") or "").strip()
    dual_ok = bool(off.get("dual_approved") or off.get("dual_approval_primary_by"))
    deactivated = not getattr(school, "is_active", True) or bool(
        off.get("wind_down_mode")
    )

    def _step(key: str, label: str, done: bool, detail: str = "") -> dict:
        return {
            "key": key,
            "label": label,
            "done": done,
            "detail": detail,
        }

    steps = [
        _step(
            "restrict",
            str(_("Restrict access (wind-down)")),
            deactivated,
            str(_("Tenant logins limited to export-only when wind-down is active.")),
        ),
        _step(
            "export",
            str(_("Export portability pack")),
            bool(export_path),
            export_path or str(_("No export on file yet.")),
        ),
        _step(
            "billing",
            str(_("Billing clearance")),
            _billing_checklist_cleared(school, snap),
            _billing_checklist_detail(school),
        ),
        _step(
            "hold",
            str(_("Legal hold cleared")),
            not bool(snap.get("legal_hold_active")),
            hold_until or str(_("No hold")),
        ),
        _step(
            "schedule",
            str(_("Purge scheduled or approved")),
            bool(scheduled) or dual_ok,
            scheduled or str(_("Optional — set purge date or dual approval.")),
        ),
        _step(
            "purge",
            str(_("Permanent delete executed")),
            current_stage(school) == SchoolLifecycleStage.Stage.OFFBOARDING_PURGED,
            "",
        ),
    ]
    done_count = sum(1 for s in steps if s["done"])
    for s in steps:
        s["progress_pct"] = int(100 * done_count / max(len(steps), 1))
    return steps

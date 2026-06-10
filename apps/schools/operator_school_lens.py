"""Operator Context Lens — lightweight health + provisioning snapshot for control plane."""

from __future__ import annotations

import logging
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.schools.control_plane_lifecycle import get_lifecycle_snapshot
from apps.schools.models import School

logger = logging.getLogger(__name__)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _chip(key: str, label: str, value: str, tone: str) -> dict[str, str]:
    return {"key": key, "label": _text(label), "value": _text(value), "tone": tone}


def can_operator_requeue_provisioning(school: School) -> bool:
    """True when an operator requeue is safe and useful."""
    from apps.schools.provisioning_progress import (
        resolve_portal_ready,
        resolve_provisioning_progress,
    )
    from apps.schools.tenant_offboarding import provisioning_in_flight

    if school is None or resolve_portal_ready(school):
        return False

    progress = resolve_provisioning_progress(school)
    status = (progress.get("status") or "").strip().lower()
    if status == "failed" or progress.get("blocking_error") or progress.get("last_error"):
        return True
    if provisioning_in_flight(school) and status == "running":
        return False
    return not bool(getattr(school, "is_active", False))


def operator_requeue_provisioning(school: School, *, actor=None) -> dict[str, Any]:
    """
    Queue + sync provisioning for an inactive / stuck school (operator path).

    Skips anonymous session cooldown used on pending tenant polls.
    """
    from apps.schools.pending_tenant_discovery import _primary_owner_user
    from apps.schools.provisioning_progress import resolve_portal_ready
    from apps.schools.tasks import kick_complete_provisioning_background

    if school is None:
        raise ValueError("School not found.")
    if resolve_portal_ready(school):
        raise ValueError("Portal is already ready; requeue is not needed.")
    if not can_operator_requeue_provisioning(school):
        raise ValueError("Provisioning is already running; wait or inspect Tenant 360.")

    owner = _primary_owner_user(school)
    contact_email = (getattr(owner, "email", "") or "").strip()
    kick_complete_provisioning_background(str(school.pk), contact_email=contact_email)
    logger.info(
        "operator_requeue_provisioning school_id=%s actor_id=%s",
        school.pk,
        getattr(actor, "pk", None),
    )
    return {
        "ok": True,
        "school_id": str(school.pk),
        "message": str(_("Provisioning requeued. Refresh the lens in a few seconds.")),
        "contact_email_present": bool(contact_email),
    }


def build_operator_team_lens_snapshot(user) -> dict[str, Any]:
    """Compact JSON for operator roster Lens (identity + MFA; no provisioning train)."""
    from apps.platform_runtime.operator_identity import (
        operator_mfa_enrolled,
        tier_display,
        user_effective_platform_scopes,
    )

    profile = getattr(user, "platform_operator_profile", None)
    tier = getattr(profile, "tier", "") or "—"
    status = getattr(profile, "status", "legacy") or "legacy"
    mfa_ok = operator_mfa_enrolled(user)
    scopes = sorted(user_effective_platform_scopes(user) or [])

    chips: list[dict[str, str]] = [
        _chip(
            "tier",
            _("Tier"),
            tier_display(tier) if tier != "—" else "—",
            "success" if tier in {"break_glass", "security"} else "muted",
        ),
        _chip(
            "status",
            _("Status"),
            str(status).replace("_", " ").title(),
            "success" if status == "active" else "warning" if status == "pending" else "danger",
        ),
        _chip(
            "mfa",
            _("MFA"),
            _("Enrolled") if mfa_ok else _("Required"),
            "success" if mfa_ok else "warning",
        ),
        _chip("scopes", _("Scopes"), str(len(scopes)), "muted"),
    ]

    return {
        "ok": True,
        "operator_id": str(user.pk),
        "username": _text(getattr(user, "username", "")),
        "health_chips": chips,
        "operator": {
            "tier": _text(tier),
            "tier_label": tier_display(tier) if tier != "—" else "—",
            "status": _text(status),
            "mfa_enrolled": mfa_ok,
            "scope_count": len(scopes),
            "scopes_preview": scopes[:8],
        },
    }


def build_operator_lens_snapshot(school: School) -> dict[str, Any]:
    """Compact JSON for copilot Lens polling (health chips + provisioning mini-train)."""
    from apps.lifecycle.unified_lifecycle import resolve_unified_lifecycle
    from apps.schools.provisioning_progress import resolve_provisioning_progress

    lifecycle = get_lifecycle_snapshot(school)
    unified = resolve_unified_lifecycle(school)
    progress = resolve_provisioning_progress(school)

    chips: list[dict[str, str]] = []
    chips.append(
        _chip(
            "active",
            _("Active"),
            _("Yes") if getattr(school, "is_active", False) else _("No"),
            "success" if getattr(school, "is_active", False) else "secondary",
        )
    )
    if getattr(school, "is_frozen", False):
        chips.append(_chip("frozen", _("Frozen"), _("Yes"), "danger"))

    lifecycle_label = _text(lifecycle.get("state_label") or lifecycle.get("state") or "—")
    chips.append(
        _chip(
            "lifecycle",
            _("Lifecycle"),
            lifecycle_label,
            _text(lifecycle.get("tone") or "muted"),
        )
    )

    prov_status = (progress.get("status") or "").strip().lower()
    if prov_status and not progress.get("portal_ready"):
        prov_tone = (
            "success"
            if prov_status == "succeeded"
            else "danger"
            if prov_status == "failed"
            else "warning"
        )
        chips.append(
            _chip(
                "provision",
                _("Provision"),
                f"{int(progress.get('progress_percent') or 0)}%",
                prov_tone,
            )
        )
        # Surface a stalled provision to operators (heartbeat went silent) so it's
        # visible at a glance instead of hiding behind a frozen percentage.
        if progress.get("stuck"):
            chips.append(_chip("stuck", _("Provision"), _("Delayed"), "danger"))

    unified_state = _text(unified.get("label") or unified.get("state") or "")
    if unified_state and unified.get("provisioning_in_flight"):
        chips.append(_chip("unified", _("Status"), unified_state, "warning"))

    extended = progress.get("extended_steps") or []
    train = [
        {
            "key": _text(step.get("key")),
            "label": _text(step.get("label")),
            "state": _text(step.get("state") or "pending"),
        }
        for step in extended
        if isinstance(step, dict)
    ]

    return {
        "ok": True,
        "school_id": str(school.pk),
        "school_name": _text(getattr(school, "name", "")),
        "slug": _text(getattr(school, "slug", "")),
        "health_chips": chips,
        "provisioning": {
            "status": prov_status or "unknown",
            "progress_percent": int(progress.get("progress_percent") or 0),
            "current_step_key": progress.get("current_step_key"),
            "current_step_label": _text(progress.get("current_step_label") or ""),
            "portal_ready": bool(progress.get("portal_ready")),
            "is_active": bool(progress.get("is_active")),
            "workflow_run_id": progress.get("workflow_run_id"),
            "eta_seconds": progress.get("eta_seconds"),
            "elapsed_seconds": progress.get("elapsed_seconds"),
            "stuck": bool(progress.get("stuck")),
            "current_phase": progress.get("current_phase"),
            "phase_message": _text(progress.get("phase_message") or ""),
            "completion_summary": progress.get("completion_summary") or {},
            "completed_at": progress.get("completed_at"),
            "last_error": progress.get("last_error") or progress.get("blocking_error"),
            "extended_steps": train,
            "can_requeue": can_operator_requeue_provisioning(school),
        },
    }

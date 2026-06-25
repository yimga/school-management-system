"""
Unified school readiness payload — single customer-facing meter for
provisioning → setup → migration → launch (batch 1731).
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def build_school_readiness(school, *, user: Any = None) -> dict[str, Any]:
    """Aggregate provision, checklist, Setup Studio, and lifecycle into one dict."""
    if school is None:
        return {"ok": False, "reason": "no_school"}

    provision: dict[str, Any] = {}
    try:
        from apps.schools.provisioning_progress import resolve_provisioning_progress

        provision = resolve_provisioning_progress(school) or {}
    except Exception:  # noqa: BLE001 — readiness must degrade gracefully
        provision = {"status": "unknown"}

    onboarding: dict[str, Any] = {}
    try:
        from apps.platform_runtime.onboarding import get_school_onboarding_progress

        onboarding = get_school_onboarding_progress(school, user=user) or {}
    except Exception:  # noqa: BLE001
        onboarding = {"percent": 0, "steps": []}

    studio: dict[str, Any] = {}
    try:
        from apps.setup_studio.services import get_setup_studio_payload

        studio = get_setup_studio_payload(school) or {}
    except Exception:  # noqa: BLE001
        studio = {"launch_ready": False, "launch_blockers": []}

    lifecycle: dict[str, Any] = {}
    try:
        from apps.platform_runtime.tenant_operational_lifecycle import (
            resolve_operational_lifecycle_state,
        )

        lifecycle = resolve_operational_lifecycle_state(school) or {}
    except Exception:  # noqa: BLE001
        lifecycle = {"state": "unknown"}

    launch_ready = bool(studio.get("launch_ready"))
    checklist_pct = int(onboarding.get("percent") or 0)
    provision_status = str(provision.get("status") or "unknown")
    blockers = list(studio.get("launch_blockers") or [])
    needs_resume = bool(provision.get("needs_resume"))
    phase_b_failed_steps = list(provision.get("phase_b_failed_steps") or [])

    provision_done = provision_status in {"completed", "portal_ready", "COMPLETED", "succeeded"}
    if needs_resume:
        provision_done = False

    phases = [
        {
            "key": "provision",
            "label": str(_("Provisioned")),
            "done": provision_done,
            "detail": str(
                _("Finishing campus setup ({n} step(s) pending)").format(
                    n=len(phase_b_failed_steps)
                )
                if needs_resume and phase_b_failed_steps
                else provision.get("phase_message") or provision_status
            ),
        },
        {
            "key": "configure",
            "label": str(_("Configured")),
            "done": checklist_pct >= 70,
            "detail": str(_("{pct}% activation checklist").format(pct=checklist_pct)),
        },
        {
            "key": "launch",
            "label": str(_("Launch ready")),
            "done": launch_ready,
            "detail": str(
                _("{n} blocker(s)").format(n=len(blockers))
                if blockers
                else _("All launch blockers cleared")
            ),
        },
        {
            "key": "operate",
            "label": str(_("Daily operations")),
            "done": lifecycle.get("state") == "daily_operations",
            "detail": str(lifecycle.get("state") or "unknown"),
        },
    ]
    phase_done = sum(1 for p in phases if p["done"])
    meter_pct = round(100 * phase_done / len(phases)) if phases else 0

    migration_intent = False
    migration_status = "not_started"
    has_launched = False
    try:
        settings_blob = getattr(school, "settings", None) or {}
        onboarding_blob = settings_blob.get("rmc_public_onboarding") or {}
        migration_blob = onboarding_blob.get("migration") or {}
        migration_intent = bool(migration_blob.get("vendor_slug"))
        migration_status = str(migration_blob.get("status") or "not_started")
    except (AttributeError, TypeError, ValueError):
        migration_intent = False
        migration_status = "not_started"
    try:
        from apps.setup_studio.models import SetupProgress

        progress = SetupProgress.objects.filter(school=school).first()
        has_launched = bool(progress and progress.launched_at)
    except Exception:  # noqa: BLE001
        has_launched = False

    if has_launched:
        for phase in phases:
            if phase["key"] == "operate":
                phase["done"] = True
                phase["detail"] = str(_("Daily operations"))

    if migration_intent and not has_launched:
        migration_done = migration_status in {"completed", "verified", "imported", "succeeded"}
        migration_detail = {
            "not_started": str(_("Choose vendor & export")),
            "in_progress": str(_("Companion ingest in progress")),
            "pending_review": str(_("Review imported rows")),
            "completed": str(_("Migration verified")),
            "verified": str(_("Migration verified")),
            "imported": str(_("Data imported")),
            "succeeded": str(_("Migration complete")),
        }.get(migration_status, migration_status.replace("_", " "))
        phases.insert(
            3,
            {
                "key": "migrate",
                "label": str(_("Data migrated")),
                "done": migration_done,
                "detail": migration_detail,
            },
        )
        phase_done = sum(1 for p in phases if p["done"])
        meter_pct = round(100 * phase_done / len(phases)) if phases else 0

    cached_at = timezone.now().isoformat()

    return {
        "ok": True,
        "meter_percent": meter_pct,
        "phases": phases,
        "has_launched": has_launched,
        "cached_at": cached_at,
        "offline_hint": str(
            _("Readiness cached locally when offline — syncs when connected")
        ),
        "provision": {
            "status": provision_status,
            "current_phase": provision.get("current_phase"),
            "portal_ready": bool(provision.get("portal_ready")),
            "needs_resume": needs_resume,
            "phase_b_failed_steps": phase_b_failed_steps,
        },
        "onboarding": {
            "percent": checklist_pct,
            "next_action": onboarding.get("next_action"),
        },
        "setup_studio": {
            "launch_ready": launch_ready,
            "launch_blockers": blockers,
            "recommended_next": studio.get("recommended_next"),
            "health_score": studio.get("health_score"),
        },
        "lifecycle": lifecycle,
        "migration_branch": migration_intent,
        "migration": {
            "intent": migration_intent,
            "status": migration_status,
            "local_first": True,
        },
        "provisioning_slo": _provisioning_slo(provision, needs_resume=needs_resume),
    }


def _provisioning_slo(provision: dict[str, Any], *, needs_resume: bool = False) -> dict[str, Any]:
    """Customer-visible provisioning SLO snapshot (targets only — honest status)."""
    status = str(provision.get("status") or "unknown")
    stuck = bool(provision.get("stuck"))
    if needs_resume:
        tone, label = "warn", str(_("Setup incomplete"))
    elif status in {"completed", "portal_ready", "COMPLETED", "succeeded"}:
        tone, label = "ready", str(_("Within target"))
    elif stuck:
        tone, label = "warn", str(_("Needs attention"))
    elif status in {"provisioning", "seeding", "in_progress"}:
        tone, label = "progress", str(_("In progress"))
    else:
        tone, label = "unknown", str(_("Status pending"))
    return {
        "tone": tone,
        "label": label,
        "target_minutes": 15,
        "stuck": stuck,
    }

"""
First-7-days post-launch playbook (batch 1735).

Checklist tasks surface on admin backend after ``launched_at`` is set.
Acknowledgments may queue offline via field_capture.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def build_launch_playbook(school, *, user: Any = None) -> dict[str, Any]:
    """Return playbook tasks + completion state for post-launch admin surfaces."""
    if school is None:
        return {"ok": False, "reason": "no_school"}

    has_launched = False
    launched_at_iso = ""
    try:
        from apps.setup_studio.models import SetupProgress

        progress = SetupProgress.objects.filter(school=school).first()
        if progress and progress.launched_at:
            has_launched = True
            launched_at_iso = progress.launched_at.isoformat()
    except Exception:  # noqa: BLE001
        has_launched = False

    if not has_launched:
        return {"ok": True, "visible": False, "tasks": [], "completed_count": 0}

    settings_blob = getattr(school, "settings", None) or {}
    if not isinstance(settings_blob, dict):
        settings_blob = {}
    acks = settings_blob.get("rmc_launch_playbook_acks") or {}
    if not isinstance(acks, dict):
        acks = {}

    tasks = [
        {
            "key": "invite_teachers",
            "label": str(_("Invite teachers")),
            "detail": str(_("Send role invites or share self-onboarding link")),
            "done": bool(acks.get("invite_teachers")),
        },
        {
            "key": "invite_parents",
            "label": str(_("Invite parents")),
            "detail": str(_("Publish parent portal access instructions")),
            "done": bool(acks.get("invite_parents")),
        },
        {
            "key": "verify_attendance",
            "label": str(_("Run first attendance")),
            "detail": str(_("Confirm roll-call works offline on a pilot class")),
            "done": bool(acks.get("verify_attendance")),
        },
        {
            "key": "verify_finance",
            "label": str(_("Publish fee schedule")),
            "detail": str(_("Ensure invoices or fee notices are visible")),
            "done": bool(acks.get("verify_finance")),
        },
        {
            "key": "cs_checkin",
            "label": str(_("Day-7 check-in")),
            "detail": str(_("Mark playbook complete or request CS help")),
            "done": bool(acks.get("cs_checkin")),
        },
    ]
    completed = sum(1 for t in tasks if t["done"])

    return {
        "ok": True,
        "visible": True,
        "launched_at": launched_at_iso,
        "tasks": tasks,
        "completed_count": completed,
        "total_count": len(tasks),
        "offline_action_type": "launch_playbook_ack",
        "generated_at": timezone.now().isoformat(),
    }

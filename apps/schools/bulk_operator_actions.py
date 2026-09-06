"""Bulk control-plane mutations for operator list surfaces (schools fleet)."""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction

from apps.schools.control_plane_lifecycle import apply_school_lifecycle_action
from apps.schools.models import School
from apps.schools.tenant_offboarding import (
    dry_run_purge,
    legal_hold_active,
    operator_schedule_purge,
    provisioning_in_flight,
    record_dual_approval,
    record_primary_dual_approval,
    run_wind_down_deactivate,
    run_wind_down_export,
)
from apps.schools.tenant_offboarding_policy import default_scheduled_purge_date

MAX_BULK_IDS = 200

# Permanent purge (apply_purge) is intentionally excluded: irreversible delete stays on
# Tenant 360 with per-school slug confirmation — never multi-select bulk bar.
ALLOWED_SCHOOL_ACTIONS = frozenset(
    {
        "freeze",
        "unfreeze",
        "activate",
        "deactivate",
        "begin_offboarding",
        "export",
        "purge_dry_run",
        "dual_approve_primary",
        "dual_approve_second",
    }
)

ACTION_CONFIRM_PHRASES = {
    "begin_offboarding": "BEGIN OFFBOARDING",
    "export": "EXPORT TENANTS",
    "purge_dry_run": "DRY RUN PURGE",
    "dual_approve_primary": "RECORD PRIMARY APPROVAL",
    "dual_approve_second": "RECORD SECOND APPROVAL",
}

DESTRUCTIVE_CONFIRM_PHRASE = ACTION_CONFIRM_PHRASES["begin_offboarding"]


def parse_school_id_list(raw_ids: Any) -> list[uuid.UUID]:
    if not raw_ids:
        return []
    if not isinstance(raw_ids, (list, tuple)):
        return []
    out: list[uuid.UUID] = []
    for item in raw_ids:
        if isinstance(item, uuid.UUID):
            out.append(item)
        else:
            text = str(item or "").strip()
            if not text:
                continue
            out.append(uuid.UUID(text))
    if len(out) > MAX_BULK_IDS:
        # Refuse rather than trim. This list drives a bulk WRITE, and trimming it
        # applied the change to the first MAX_BULK_IDS rows while reporting
        # success -- the remainder kept its old value with nothing in the
        # response naming what had been left behind. Same defect, and the same
        # cure, as apps/people/bulk_staff_actions.py (2026-09-06).
        raise ValueError(
            "Select %d or fewer at once (you selected %d). Nothing was changed."
            % (MAX_BULK_IDS, len(out))
        )
    return out


def _apply_one_school_action(
    school: School,
    *,
    action: str,
    reason: str,
    actor,
) -> dict[str, Any]:
    if action == "begin_offboarding":
        if provisioning_in_flight(school):
            raise ValueError("Provisioning is in flight; wait before offboarding.")
        hold_active, hold_msg = legal_hold_active(school)
        if hold_active:
            raise ValueError(hold_msg or "Legal hold is active.")
        outcome = run_wind_down_deactivate(school, actor=actor)
        purge_at = default_scheduled_purge_date().isoformat()
        schedule = operator_schedule_purge(school, purge_at=purge_at, actor=actor)
        return {
            "message": outcome.get("message", "Wind-down started."),
            "scheduled_purge_at": schedule.get("scheduled_purge_at"),
        }
    if action == "export":
        result = run_wind_down_export(school, full=True, actor=actor)
        return {
            "message": "Portability export completed.",
            "export_zip_path": result.export_zip_path,
            "student_export_count": result.student_export_count,
        }
    if action == "purge_dry_run":
        preview = dry_run_purge(
            school,
            confirm_slug=school.slug,
            force_provisioning=False,
            dual_approved=False,
        )
        blockers = preview.purge_blocked_reasons or []
        return {
            "message": "Purge dry-run complete.",
            "row_total": preview.row_total,
            "purge_blocked_reasons": blockers,
            "blocked": bool(blockers),
        }
    if action == "dual_approve_primary":
        outcome = record_primary_dual_approval(school, actor=actor)
        return {"message": "Primary dual approval recorded.", **outcome}
    if action == "dual_approve_second":
        outcome = record_dual_approval(school, actor=actor)
        return {"message": "Second dual approval recorded.", **outcome}

    lifecycle_reason = reason
    if action == "freeze" and not lifecycle_reason:
        lifecycle_reason = "STORAGE"
    outcome = apply_school_lifecycle_action(
        school,
        action=action,
        reason=lifecycle_reason,
    )
    return {"message": outcome.get("message", "Updated.")}


def bulk_apply_school_actions(
    *,
    school_ids: list[uuid.UUID],
    action: str,
    reason: str = "",
    actor=None,
    confirm_phrase: str = "",
) -> dict[str, Any]:
    action = str(action or "").strip().lower().replace("-", "_")
    if action not in ALLOWED_SCHOOL_ACTIONS:
        raise ValueError(f"Unsupported bulk action: {action}")
    required_phrase = ACTION_CONFIRM_PHRASES.get(action)
    if required_phrase and str(confirm_phrase or "").strip() != required_phrase:
        raise ValueError(f'Type "{required_phrase}" to confirm.')
    if not school_ids:
        raise ValueError("Select at least one school.")

    schools = list(School.objects.filter(pk__in=school_ids).order_by("name"))
    found_ids = {school.pk for school in schools}
    missing = [str(sid) for sid in school_ids if sid not in found_ids]

    results: list[dict[str, Any]] = []
    for school in schools:
        try:
            with transaction.atomic():
                payload = _apply_one_school_action(
                    school,
                    action=action,
                    reason=reason,
                    actor=actor,
                )
            results.append(
                {
                    "id": str(school.id),
                    "slug": school.slug,
                    "ok": True,
                    "message": payload.get("message", ""),
                    "scheduled_purge_at": payload.get("scheduled_purge_at"),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "id": str(school.id),
                    "slug": getattr(school, "slug", ""),
                    "ok": False,
                    "error": str(exc),
                }
            )

    for mid in missing:
        results.append({"id": mid, "ok": False, "error": "School not found."})

    succeeded = sum(1 for row in results if row.get("ok"))
    return {
        "ok": succeeded > 0,
        "action": action,
        "processed": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
        "results": results,
    }

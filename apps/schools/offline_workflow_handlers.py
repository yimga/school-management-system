"""Offline tenant-journey workflows (batches 1732–1742, Pillar E)."""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

TENANT_JOURNEY_WORKFLOWS: frozenset[str] = frozenset(
    {
        "discipline_refer",
        "launch_playbook_ack",
        "year_close_ack",
    }
)


def _client_key(payload: dict[str, Any]) -> str:
    return str(
        payload.get("client_offline_id") or payload.get("idempotency_key") or "",
    )[:128]


def apply_tenant_journey_workflow(
    school_id: int,
    user_id: int,
    workflow: str,
    fields: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if workflow not in TENANT_JOURNEY_WORKFLOWS:
        return None
    if workflow == "discipline_refer":
        return _apply_discipline_refer(school_id, user_id, fields, payload)
    if workflow == "launch_playbook_ack":
        return _apply_launch_playbook_ack(school_id, user_id, fields, payload)
    if workflow == "year_close_ack":
        return _apply_year_close_ack(school_id, user_id, fields, payload)
    return None


def _apply_discipline_refer(
    school_id: int,
    user_id: int,
    fields: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    from apps.academics.views_discipline_api import create_incident_from_fields

    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.filter(pk=user_id).first()  # tenant-isolation-allow: offline-author-resolved-by-pk-then-service-checks-role
    if user is None:
        return {"ok": False, "error": "unknown_user"}

    client_key = _client_key(payload)
    if client_key:
        from apps.academics.models import Incident

        existing = (
            Incident.objects.filter(
                school_id=school_id,
                description__contains=f"[offline:{client_key}]",
            )
            .order_by("-pk")
            .first()
        )
        if existing:
            return {
                "ok": True,
                "incident_id": existing.pk,
                "idempotent_replay": True,
            }

    result = create_incident_from_fields(
        school_id=school_id,
        user=user,
        fields=fields,
        offline_marker=client_key or None,
    )
    if not result.get("ok"):
        return result
    return {**result, "workflow": "discipline_refer"}


def _merge_school_settings_ack(
    school_id: int,
    *,
    settings_key: str,
    item_key: str,
) -> dict[str, Any]:
    from apps.schools.models import School

    if not item_key:
        return {"ok": False, "error": "item_key_required"}

    with transaction.atomic():
        school = School.objects.select_for_update().filter(pk=school_id).first()
        if school is None:
            return {"ok": False, "error": "school_not_found"}

        settings_blob = dict(getattr(school, "settings", None) or {})
        acks = dict(settings_blob.get(settings_key) or {})
        acks[item_key] = timezone.now().isoformat()
        settings_blob[settings_key] = acks
        school.settings = settings_blob
        school.save(update_fields=["settings", "updated_at"])

    return {"ok": True, "item_key": item_key, "acknowledged_at": acks[item_key]}


def _admin_may_ack_journey(user) -> bool:
    from apps.accounts.models import User

    role = (getattr(user, "role", "") or "").upper()
    return bool(
        getattr(user, "is_staff", False)
        or role in {User.Role.ADMIN, User.Role.IT_ADMIN, User.Role.LEADERSHIP}
    )


def _apply_launch_playbook_ack(
    school_id: int,
    user_id: int,
    fields: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.filter(pk=user_id).first()  # tenant-isolation-allow: offline-author-resolved-by-pk-then-permission-checked
    if user is None:
        return {"ok": False, "error": "unknown_user"}
    if not _admin_may_ack_journey(user):
        return {"ok": False, "error": "not_authorized"}

    task_key = str(fields.get("task_key") or "").strip()
    result = _merge_school_settings_ack(
        school_id,
        settings_key="rmc_launch_playbook_acks",
        item_key=task_key,
    )
    if result.get("ok"):
        result["workflow"] = "launch_playbook_ack"
    return result


def _apply_year_close_ack(
    school_id: int,
    user_id: int,
    fields: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.filter(pk=user_id).first()  # tenant-isolation-allow: offline-author-resolved-by-pk-then-permission-checked
    if user is None:
        return {"ok": False, "error": "unknown_user"}
    if not _admin_may_ack_journey(user):
        return {"ok": False, "error": "not_authorized"}

    item_key = str(fields.get("item_key") or "").strip()
    result = _merge_school_settings_ack(
        school_id,
        settings_key="rmc_year_close_acks",
        item_key=item_key,
    )
    if result.get("ok"):
        result["workflow"] = "year_close_ack"
    return result

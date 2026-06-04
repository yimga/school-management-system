"""Offline schoolops workflows (front-desk / ops module).

Scope note (deliberate): of the ops surfaces in the audit's
"discipline/health/library/transport" list, only an append-only EVENT log is a
safe offline-write target. So this module covers visitor check-in and nothing
else:

* clinic (HealthRecord) — the ops_clinic page is GET-only; there is no create
  form to queue offline.
* library loan / transport assignment — these mutate a SHARED, limited resource
  (a copy of a book; a seat). Creating them offline would let two disconnected
  devices issue the same book or assign the same seat, then both "win" on drain —
  i.e. it would CREATE the conflict we are trying to avoid. These stay
  online-only writes by design (read works offline via the cache).
* discipline — no first-class model exists to write to.

Visitor check-in is a pure append (no shared-resource contention, no FK to
validate), so it is the one surface wired here. Same discipline as the people
handlers: authorization is RE-DERIVED server-side and the write is idempotent.
"""
from __future__ import annotations

import logging
from typing import Any

from django.db import DatabaseError, IntegrityError, transaction

logger = logging.getLogger(__name__)

SCHOOLOPS_WORKFLOWS: frozenset[str] = frozenset({"visitor_check_in"})


def _client_key(payload: dict[str, Any]) -> str:
    return str(
        payload.get("client_offline_id") or payload.get("idempotency_key") or "",
    )[:128]


def _resolve_actor(user_id):
    """Return ``(user, allowed)``; authorization re-derived, never client-trusted."""
    from django.contrib.auth import get_user_model

    from apps.accounts.permissions import user_can_access_ops_extended_modules

    User = get_user_model()
    user = User.objects.filter(pk=user_id).first()  # tenant-isolation-allow: offline-author-resolved-by-pk-then-permission-checked
    if user is None:
        return None, False
    return user, bool(user_can_access_ops_extended_modules(user))


def apply_schoolops_workflow(
    school_id: int,
    user_id: int,
    workflow: str,
    fields: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if workflow not in SCHOOLOPS_WORKFLOWS:
        return None
    if workflow == "visitor_check_in":
        return _apply_visitor_check_in(school_id, user_id, fields, payload)
    return None


def _apply_visitor_check_in(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    from apps.schoolops.models import VisitorCheckIn

    actor, allowed = _resolve_actor(user_id)
    if actor is None:
        return {"ok": False, "error": "unknown_user"}
    if not allowed:
        return {"ok": False, "error": "not_authorized_visitor_log"}

    name = (fields.get("visitor_name") or "").strip()
    if not name:
        return {"ok": False, "error": "visitor_name_required"}

    client_key = _client_key(payload)
    if client_key:
        existing = VisitorCheckIn.objects.filter(  # tenant-isolation-allow: explicit-school-scoped-offline-idempotency-lookup
            school_id=school_id, client_offline_id=client_key
        ).first()
        if existing:
            return {
                "ok": True,
                "dedup": True,
                "visit_id": existing.pk,
                "schoolops_capture": True,
            }

    try:
        with transaction.atomic():
            row = VisitorCheckIn.objects.create(
                school_id=school_id,
                visitor_name=name[:255],
                host_contact=(fields.get("host_contact") or "").strip()[:255],
                purpose=(fields.get("purpose") or "").strip()[:255],
                badge_number=(fields.get("badge_number") or "").strip()[:64],
                recorded_by_id=user_id,
                client_offline_id=client_key,
            )
    except (DatabaseError, IntegrityError, ValueError) as exc:
        logger.warning(
            "schoolops.offline_visitor_check_in failed school=%s err=%s", school_id, exc
        )
        return {"ok": False, "error": "create_failed:%s" % type(exc).__name__}

    return {"ok": True, "visit_id": row.pk, "schoolops_capture": True}

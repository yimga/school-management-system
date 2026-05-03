"""
Offline queue utilities:

1. **sync_engine / mobile API facade** — pending counts, client batch validation, conflict UI merge helpers.
2. **OfflineAction** — durable server queue with explicit apply paths for attendance, grading, payment receipt capture.

Browser clients may continue using Dexie/SW + ``OfflineSyncQueue``; ``OfflineAction`` stores submitted work at the
tenant boundary with queued/syncing/synced/failed/conflict lifecycle.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# --- Existing facade (sync_engine / mobile queue) ---------------------------------

# Exponential-ish backoff (seconds) after each failed sync attempt (0 = first retry delay).
DEFAULT_RETRY_BACKOFF_SECONDS: tuple[int, ...] = (5, 15, 60, 300, 900, 1800)


def next_retry_delay_seconds(attempt_index: int) -> int:
    """Return delay before the next retry; caps at the last bucket."""
    if attempt_index < 0:
        attempt_index = 0
    if attempt_index >= len(DEFAULT_RETRY_BACKOFF_SECONDS):
        return DEFAULT_RETRY_BACKOFF_SECONDS[-1]
    return DEFAULT_RETRY_BACKOFF_SECONDS[attempt_index]


def get_pending_actions(
    school_id: int | None,
    user_id: int,
    *,
    device_id: str | None = None,
) -> list[dict[str, Any]]:
    """Pending / failed rows for the authenticated user's devices (server truth)."""
    from apps.sync_engine.services import get_pending_changes

    return get_pending_changes(school_id, user_id, device_id=device_id)


def get_sync_state_summary(user_id: int) -> dict[str, Any]:
    """Counts by queue status for status bars and conflict badges."""
    from apps.sync_engine.services import get_visible_sync_state

    return get_visible_sync_state(user_id)


def get_merged_sync_bar_state(
    user_id: int,
    school_id: int | None,
) -> dict[str, Any]:
    """
    Merge mobile/sync_engine queue counts with durable ``OfflineAction`` rows (tenant-scoped).
    """
    base = get_sync_state_summary(user_id)
    if school_id is None:
        return base

    from apps.platform_runtime.models import OfflineAction

    qs = OfflineAction.objects.filter(school_id=school_id, user_id=user_id)
    o_pending = qs.filter(
        status__in=(
            OfflineAction.Status.QUEUED,
            OfflineAction.Status.SYNCING,
        )
    ).count()
    o_failed = qs.filter(status=OfflineAction.Status.FAILED).count()
    o_conflict = qs.filter(status=OfflineAction.Status.CONFLICT).count()

    return {
        "pending": int(base.get("pending") or 0) + o_pending,
        "failed": int(base.get("failed") or 0) + o_failed,
        "conflicts": int(base.get("conflicts") or 0) + o_conflict,
        "completed": int(base.get("completed") or 0),
        "by_status": base.get("by_status") or {},
        "offline_action_pending": o_pending,
        "offline_action_failed": o_failed,
        "offline_action_conflicts": o_conflict,
    }


def apply_client_batch(
    school_id: int,
    user_id: int,
    changes: list[dict[str, Any]],
    *,
    device_id: str | None = None,
) -> dict[str, Any]:
    """
    Validate a batch from the client; returns applied count + structural conflicts.

    Domain-specific merge (marks, attendance, payments) is handled in mobile replay;
    this layer detects duplicate entity operations in a single batch.
    """
    from apps.sync_engine.services import apply_remote

    return apply_remote(school_id, user_id, changes, device_id=device_id)


def retry_failed_server_rows(
    user_id: int,
    *,
    max_retries: int = 5,
) -> dict[str, int]:
    """Reset FAILED rows to PENDING so the client can POST replay again."""
    from apps.sync_engine.services import retry_failed_sync_items

    return retry_failed_sync_items(user_id, max_retries=max_retries)


def merge_conflict_records(
    records: list[dict[str, Any]],
    *,
    strategy: str = "last_write_wins",
) -> list[dict[str, Any]]:
    """
    Collapse duplicate (entity, id) rows for UI display.

    ``strategy`` is descriptive for the conflict drawer; authoritative resolution
    happens in entity handlers during replay.
    """
    if strategy not in {"last_write_wins", "show_both"}:
        strategy = "last_write_wins"
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in records:
        ent = str(row.get("entity") or row.get("entity_type") or "")
        eid = str(row.get("id") or row.get("entity_id") or "")
        key = (ent, eid)
        if not ent or not eid:
            continue
        if key not in by_key:
            by_key[key] = dict(row)
            continue
        if strategy == "last_write_wins":
            cur = by_key[key]
            cur_rev = float(cur.get("revision") or cur.get("client_revision") or 0)
            new_rev = float(row.get("revision") or row.get("client_revision") or 0)
            if new_rev >= cur_rev:
                by_key[key] = dict(row)
        else:
            by_key[key]["_alternate_versions"] = by_key[key].get("_alternate_versions", [])
            by_key[key]["_alternate_versions"].append(row)
    return list(by_key.values())


# --- Durable OfflineAction queue --------------------------------------------------

_OFFLINE_SOFT_ERRORS = (
    AttributeError,
    LookupError,
    RuntimeError,
    TypeError,
    ValueError,
)


def _emit_offline_lifecycle_event(
    event_name: str,
    action_row: Any,
    *,
    extra: Optional[dict[str, Any]] = None,
    idempotency_key: str | None = None,
) -> None:
    """Thin wrapper for offline queue observability (best-effort)."""
    try:
        from apps.platform_runtime.event_bus import publish_event

        sid = getattr(action_row, "school_id", None)
        tid = str(sid) if sid is not None else ""
        payload = {
            "offline_action_id": action_row.pk,
            "action_type": str(getattr(action_row, "action_type", "") or ""),
            "user_id": getattr(action_row, "user_id", None),
            "school_id": tid,
            "source": "offline_queue",
        }
        if extra:
            payload.update(extra)
        key = idempotency_key or f"{event_name}:{action_row.pk}"
        publish_event(
            event_name,
            payload,
            tenant_id=tid or None,
            school_id=sid,
            idempotency_key=str(key)[:128],
        )
    except Exception:
        logger.debug("%s publish skipped", event_name, exc_info=True)


def _emit_offline_action_synced(action_row: Any, sync_metadata: Optional[dict] = None) -> None:
    """Emit platform event when an OfflineAction reaches SYNCED (idempotent key per row)."""
    _emit_offline_lifecycle_event(
        "offline_action_synced",
        action_row,
        extra={"sync_metadata": sync_metadata or {}},
        idempotency_key=f"offline_action_synced:{action_row.pk}",
    )


def enqueue_offline_action(
    *,
    user_id: int,
    school_id,
    action_type: str,
    payload: dict[str, Any],
    idempotency_key: str = "",
):
    """
    Persist one offline unit of work. Idempotent when ``idempotency_key`` is non-empty (per school+user+key).
    """
    from apps.platform_runtime.models import OfflineAction

    key = (idempotency_key or "").strip()[:128]
    if key:
        existing = OfflineAction.objects.filter(
            school_id=school_id,
            user_id=user_id,
            idempotency_key=key,
        ).first()
        if existing:
            return existing

    row = OfflineAction.objects.create(
        user_id=user_id,
        school_id=school_id,
        action_type=action_type,
        payload=payload or {},
        idempotency_key=key,
        status=OfflineAction.Status.QUEUED,
    )
    _emit_offline_lifecycle_event(
        "offline_action_queued",
        row,
        extra={"idempotency_key": key or ""},
        idempotency_key=f"offline_action_queued:{row.pk}",
    )
    return row


def mark_synced(action_id: int, *, school_id, metadata: Optional[dict] = None) -> None:
    """Terminal success — caller must enforce tenant scope."""
    from apps.platform_runtime.models import OfflineAction

    OfflineAction.objects.filter(pk=action_id, school_id=school_id).update(
        status=OfflineAction.Status.SYNCED,
        conflict_reason="",
        last_attempt_at=timezone.now(),
        sync_metadata=(metadata or {}),
    )
    row = OfflineAction.objects.filter(pk=action_id, school_id=school_id).first()
    if row:
        _emit_offline_action_synced(row, metadata or {})


def mark_conflict(
    action_id: int,
    *,
    school_id,
    reason: str,
    details: Optional[dict] = None,
) -> None:
    """Mark conflict — requires explicit user resolution (no silent overwrite)."""
    from apps.platform_runtime.models import OfflineAction

    OfflineAction.objects.filter(pk=action_id, school_id=school_id).update(
        status=OfflineAction.Status.CONFLICT,
        conflict_reason=(reason or "")[:2000],
        conflict_details=details or {},
        resolution_choice="",
        last_attempt_at=timezone.now(),
    )
    crow = OfflineAction.objects.filter(pk=action_id, school_id=school_id).first()
    if crow:
        _emit_offline_lifecycle_event(
            "offline_action_conflict",
            crow,
            extra={
                "reason": (reason or "")[:500],
                "conflict_details": details or {},
            },
            idempotency_key=f"offline_action_conflict:{crow.pk}",
        )


def retry_failed_actions(
    *,
    school_id,
    user_id: Optional[int] = None,
    max_retries: int = 5,
    limit: int = 100,
) -> int:
    """Reset FAILED rows to QUEUED when under retry cap."""
    from apps.platform_runtime.models import OfflineAction

    qs = OfflineAction.objects.filter(
        school_id=school_id,
        status=OfflineAction.Status.FAILED,
        retry_count__lt=max_retries,
    )
    if user_id is not None:
        qs = qs.filter(user_id=user_id)
    n = 0
    for row in qs.order_by("created_at")[:limit]:
        row.status = OfflineAction.Status.QUEUED
        row.retry_count += 1
        row.save(update_fields=["status", "retry_count", "updated_at"])
        n += 1
    return n


def _apply_teacher_attendance(
    school_id,
    user_id: int,
    payload: dict[str, Any],
    *,
    force_local: bool = False,
) -> dict[str, Any]:
    """Teacher roll call (distinct from student ``Attendance`` rows)."""
    from datetime import date as date_cls

    from apps.people.models import TeacherAttendance, TeacherProfile

    tp_id = payload.get("teacher_profile_id") or payload.get("teacher_id")
    raw_date = payload.get("date")
    status_val = payload.get("status")
    remarks = str(payload.get("remarks", "") or "")[:255]
    if not all([tp_id, raw_date, status_val]):
        return {"ok": False, "error": "Missing teacher attendance fields."}
    allowed = {c[0] for c in TeacherAttendance.Status.choices}
    if status_val not in allowed:
        return {"ok": False, "error": "Invalid teacher attendance status."}
    try:
        if hasattr(raw_date, "isoformat"):
            date_obj = raw_date
        else:
            date_obj = date_cls.fromisoformat(str(raw_date)[:10])
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid date."}

    tp = TeacherProfile.objects.filter(pk=tp_id).first()
    if not tp:
        return {"ok": False, "error": "Teacher profile not found."}
    if tp.school_id and tp.school_id != school_id:
        return {"ok": False, "error": "Tenant mismatch for teacher."}

    existing = TeacherAttendance.objects.filter(
        teacher_id=tp_id,
        date=date_obj,
    ).first()
    if existing:
        if existing.status != status_val and not force_local:
            return {
                "ok": False,
                "conflict": True,
                "reason": "Teacher attendance already recorded with a different status on the server.",
                "details": {
                    "server_status": existing.status,
                    "client_status": status_val,
                    "server_remarks": getattr(existing, "remarks", "") or "",
                    "teacher_attendance_id": existing.id,
                },
            }
        if existing.status != status_val and force_local:
            existing.status = status_val
            existing.remarks = remarks
            existing.save(update_fields=["status", "remarks"])
            return {"ok": True, "teacher_attendance_id": existing.id, "forced_local": True}
        return {"ok": True, "teacher_attendance_id": existing.id, "dedup": True}

    row = TeacherAttendance.objects.create(
        teacher_id=tp_id,
        date=date_obj,
        status=status_val,
        remarks=remarks,
    )
    return {"ok": True, "teacher_attendance_id": row.id}


def _apply_attendance(
    school_id,
    user_id: int,
    payload: dict[str, Any],
    *,
    force_local: bool = False,
) -> dict[str, Any]:
    if str(payload.get("scope") or "").lower() in (
        "teacher",
        "teacher_attendance",
    ):
        return _apply_teacher_attendance(
            school_id, user_id, payload, force_local=force_local
        )

    from datetime import date as date_cls

    from apps.academics.models import Attendance, Classroom
    from apps.people.models import StudentProfile

    student_id = payload.get("student_id") or payload.get("student")
    classroom_id = payload.get("classroom_id") or payload.get("classroom")
    raw_date = payload.get("date")
    status_val = payload.get("status")
    remarks = str(payload.get("remarks", "") or "")[:255]
    if not all([student_id, classroom_id, raw_date, status_val]):
        return {"ok": False, "error": "Missing attendance fields."}
    allowed = {c[0] for c in Attendance.Status.choices}
    if status_val not in allowed:
        return {"ok": False, "error": "Invalid status."}
    try:
        if hasattr(raw_date, "isoformat"):
            date_obj = raw_date
        else:
            date_obj = date_cls.fromisoformat(str(raw_date)[:10])
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid date."}

    classroom = Classroom.objects.filter(pk=classroom_id).first()
    if not classroom:
        return {"ok": False, "error": "Classroom not found."}
    if classroom.school_id and classroom.school_id != school_id:
        return {"ok": False, "error": "Tenant mismatch for classroom."}

    student = StudentProfile.objects.filter(pk=student_id).first()
    if not student:
        return {"ok": False, "error": "Student not found."}
    if student.classroom_id != classroom_id:
        return {"ok": False, "error": "Student is not in this classroom."}
    if (
        student.classroom
        and student.classroom.school_id
        and student.classroom.school_id != school_id
    ):
        return {"ok": False, "error": "Tenant mismatch for student."}

    existing = Attendance.objects.filter(
        student_id=student_id,
        classroom_id=classroom_id,
        date=date_obj,
    ).first()
    if existing:
        if existing.status != status_val and not force_local:
            return {
                "ok": False,
                "conflict": True,
                "reason": "Attendance already recorded with a different status on the server.",
                "details": {
                    "server_status": existing.status,
                    "client_status": status_val,
                    "server_remarks": getattr(existing, "remarks", "") or "",
                    "attendance_id": existing.id,
                },
            }
        if existing.status != status_val and force_local:
            existing.status = status_val
            existing.remarks = remarks
            existing.save(update_fields=["status", "remarks", "updated_at"])
            return {"ok": True, "attendance_id": existing.id, "forced_local": True}
        return {"ok": True, "attendance_id": existing.id, "dedup": True}

    attendance = Attendance.objects.create(
        school_id=school_id,
        student_id=student_id,
        classroom_id=classroom_id,
        date=date_obj,
        status=status_val,
        remarks=remarks,
    )
    return {"ok": True, "attendance_id": attendance.id}


def _apply_payment_receipt(school_id, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    from decimal import Decimal, InvalidOperation

    from django.contrib.auth import get_user_model

    from apps.finance.models import Invoice, OfflinePaymentIntent, PaymentMethodCode

    User = get_user_model()
    invoice_id = payload.get("invoice_id")
    amount_raw = payload.get("amount")
    method = (payload.get("payment_method") or "OTHER").upper()
    if not invoice_id or amount_raw is None:
        return {"ok": False, "error": "invoice_id and amount required."}
    valid = {c[0] for c in PaymentMethodCode.choices}
    if method not in valid:
        return {"ok": False, "error": "Invalid payment_method."}
    try:
        amount = Decimal(str(amount_raw))
    except (InvalidOperation, TypeError, ValueError):
        return {"ok": False, "error": "Invalid amount."}
    try:
        inv = Invoice.objects.get(pk=invoice_id)
    except Invoice.DoesNotExist:
        return {"ok": False, "error": "Invoice not found."}
    if inv.school_id and inv.school_id != school_id:
        return {"ok": False, "error": "Tenant mismatch."}
    client_key = str(payload.get("client_offline_id") or payload.get("idempotency_key") or "")[:64]
    if client_key:
        dup = OfflinePaymentIntent.objects.filter(
            invoice_id=invoice_id,
            client_offline_id=client_key,
        ).first()
        if dup:
            return {"ok": True, "intent_id": dup.id, "dedup": True}
    user = User.objects.filter(pk=user_id).first()
    intent = OfflinePaymentIntent.objects.create(
        invoice_id=invoice_id,
        recorded_by=user,
        amount=amount,
        payment_method=method,
        transaction_reference=str(payload.get("transaction_reference", ""))[:100],
        notes=str(payload.get("notes", ""))[:4000],
        client_offline_id=client_key,
    )
    return {"ok": True, "intent_id": intent.id}


def _apply_notes_report(school_id, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist narrative captured offline (body stored in queue payload; sync_metadata echoes summary)."""
    from apps.people.models import StudentProfile

    body = str(payload.get("body") or "").strip()
    if len(body) < 1:
        return {"ok": False, "error": "body required"}
    if len(body) > 50000:
        return {"ok": False, "error": "body too large"}
    sid = payload.get("student_id")
    if sid is not None:
        sp = StudentProfile.objects.filter(pk=sid).first()
        if not sp:
            return {"ok": False, "error": "student not found"}
        if sp.school_id and sp.school_id != school_id:
            return {"ok": False, "error": "tenant mismatch for student"}
    kind = str(payload.get("kind") or payload.get("report_type") or "note")[:48]
    title = str(payload.get("title") or "")[:200]
    return {
        "ok": True,
        "capture_kind": kind,
        "title": title,
        "student_id": sid,
        "chars": len(body),
        "notes_report_capture": True,
    }


def _apply_grading(school_id, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    from django.utils import timezone

    from apps.academics.models import SubjectAssignment
    from apps.evals.models import OfflineMarkEntry
    from apps.people.models import TeacherProfile

    tp = TeacherProfile.objects.filter(user_id=user_id).first()
    if not tp:
        return {"ok": False, "error": "Teacher profile required for grading."}
    if tp.school_id and tp.school_id != school_id:
        return {"ok": False, "error": "Teacher tenant mismatch."}
    req = (
        "subject_assignment_id",
        "student_id",
        "academic_year_id",
        "term_id",
    )
    if any(payload.get(k) is None for k in req):
        return {"ok": False, "error": f"Missing one of: {req}"}
    sa = SubjectAssignment.objects.filter(pk=payload["subject_assignment_id"]).first()
    if not sa or (
        sa.classroom
        and sa.classroom.school_id
        and sa.classroom.school_id != school_id
    ):
        return {"ok": False, "error": "Subject assignment not in this school."}
    entry = OfflineMarkEntry.objects.create(
        teacher=tp,
        subject_assignment_id=payload["subject_assignment_id"],
        student_id=payload["student_id"],
        academic_year_id=payload["academic_year_id"],
        term_id=payload["term_id"],
        seq1_score=payload.get("seq1_score"),
        seq2_score=payload.get("seq2_score"),
        exam_score=payload.get("exam_score"),
        mock_score=payload.get("mock_score"),
        practical_score=payload.get("practical_score"),
        remarks=str(payload.get("remarks", "")),
        status="pending",
        created_offline_at=timezone.now(),
    )
    return {"ok": True, "offline_entry_id": entry.id}


def _apply_payload(action: Any, *, force_local: bool = False) -> dict[str, Any]:
    from apps.platform_runtime.models import OfflineAction

    at = action.action_type
    payload = action.payload or {}
    sid = action.school_id
    uid = action.user_id
    if at == OfflineAction.ActionType.ATTENDANCE:
        return _apply_attendance(sid, uid, payload, force_local=force_local)
    if at == OfflineAction.ActionType.GRADING:
        return _apply_grading(sid, uid, payload)
    if at == OfflineAction.ActionType.PAYMENT_RECEIPT:
        return _apply_payment_receipt(sid, uid, payload)
    if at == OfflineAction.ActionType.NOTES_REPORT:
        return _apply_notes_report(sid, uid, payload)
    return {"ok": False, "error": f"Unknown action_type: {at}"}


def process_offline_queue(
    *,
    school_id,
    user_id: Optional[int] = None,
    limit: int = 25,
) -> dict[str, Any]:
    """
    Process QUEUED actions for a tenant (optional user filter).
    Sets syncing → synced/failed/conflict per row. Does not silently merge conflicts.
    """
    from apps.platform_runtime.models import OfflineAction

    qs = OfflineAction.objects.filter(
        school_id=school_id,
        status=OfflineAction.Status.QUEUED,
    ).order_by("created_at")
    if user_id is not None:
        qs = qs.filter(user_id=user_id)

    processed = 0
    failed = 0
    conflicts = 0
    synced = 0

    for action in qs[:limit]:
        with transaction.atomic():
            row = (
                OfflineAction.objects.select_for_update()
                .filter(
                    pk=action.pk,
                    school_id=school_id,
                    status=OfflineAction.Status.QUEUED,
                )
                .first()
            )
            if row is None:
                continue
            row.status = OfflineAction.Status.SYNCING
            row.last_attempt_at = timezone.now()
            row.save(update_fields=["status", "last_attempt_at", "updated_at"])

        try:
            result = _apply_payload(row, force_local=False)
        except _OFFLINE_SOFT_ERRORS as exc:
            OfflineAction.objects.filter(pk=row.pk, school_id=school_id).update(
                status=OfflineAction.Status.FAILED,
                conflict_reason=str(exc)[:2000],
                last_attempt_at=timezone.now(),
            )
            failed_row = OfflineAction.objects.filter(pk=row.pk, school_id=school_id).first()
            if failed_row:
                _emit_offline_lifecycle_event(
                    "offline_action_failed",
                    failed_row,
                    extra={"error": str(exc)[:500]},
                    idempotency_key=f"offline_action_failed:{failed_row.pk}:{failed_row.retry_count}",
                )
            failed += 1
            processed += 1
            continue

        if result.get("conflict"):
            mark_conflict(
                row.pk,
                school_id=school_id,
                reason=str(result.get("reason") or "Conflict"),
                details=result.get("details") or {},
            )
            conflicts += 1
        elif result.get("ok"):
            OfflineAction.objects.filter(pk=row.pk, school_id=school_id).update(
                status=OfflineAction.Status.SYNCED,
                conflict_reason="",
                sync_metadata=result,
                last_attempt_at=timezone.now(),
            )
            synced_row = OfflineAction.objects.filter(pk=row.pk, school_id=school_id).first()
            if synced_row:
                _emit_offline_action_synced(synced_row, result)
            synced += 1
        else:
            OfflineAction.objects.filter(pk=row.pk, school_id=school_id).update(
                status=OfflineAction.Status.FAILED,
                conflict_reason=str(result.get("error") or "Apply failed")[:2000],
                last_attempt_at=timezone.now(),
            )
            failed_row = OfflineAction.objects.filter(pk=row.pk, school_id=school_id).first()
            if failed_row:
                _emit_offline_lifecycle_event(
                    "offline_action_failed",
                    failed_row,
                    extra={"error": str(result.get("error") or "Apply failed")[:500]},
                    idempotency_key=f"offline_action_failed:{failed_row.pk}:{failed_row.retry_count}",
                )
            failed += 1
        processed += 1

    return {
        "processed": processed,
        "synced": synced,
        "failed": failed,
        "conflicts": conflicts,
    }


def resolve_conflict_choice(
    *,
    action_id: int,
    school_id,
    user_id: int,
    choice: str,
    school_operator: bool = False,
) -> dict[str, Any]:
    """
    User-driven resolution only.

    - keep_mine: re-apply stored client payload (same as initial intent).
    - use_latest: mark synced without re-applying client payload (abandon local edit).
    - review_manual: leave as conflict; operator fixes on the canonical screen.

    ``school_operator``: tenant hub-eligible resolver may act on any user's queue row.
    """
    from apps.platform_runtime.models import OfflineAction

    choice = (choice or "").strip().lower()
    if choice not in (
        OfflineAction.Resolution.KEEP_MINE,
        OfflineAction.Resolution.USE_LATEST,
        OfflineAction.Resolution.REVIEW_MANUAL,
    ):
        return {"ok": False, "error": "invalid choice"}

    qs = OfflineAction.objects.filter(
        pk=action_id,
        school_id=school_id,
        status=OfflineAction.Status.CONFLICT,
    )
    if not school_operator:
        qs = qs.filter(user_id=user_id)
    row = qs.first()
    if row is None:
        return {"ok": False, "error": "Not found or not in conflict."}

    row.resolution_choice = choice
    audit_ts = timezone.now()
    audit_blob = {
        "resolved_at": audit_ts.isoformat(),
        "resolver_user_id": user_id,
        "original_submitter_user_id": row.user_id,
        "choice": choice,
        "school_operator": school_operator,
    }
    meta = dict(row.sync_metadata or {})
    hist = list(meta.get("resolution_audits") or [])
    hist.append(audit_blob)
    meta["resolution_audits"] = hist[-25:]
    meta["resolution_audit"] = audit_blob
    row.sync_metadata = meta
    row.save(update_fields=["resolution_choice", "sync_metadata", "updated_at"])

    _emit_offline_lifecycle_event(
        "offline_action_resolved",
        row,
        extra={"resolution_choice": choice, "terminal": False},
        idempotency_key=f"offline_action_resolved:{row.pk}:{audit_blob['resolved_at']}",
    )

    if choice == OfflineAction.Resolution.REVIEW_MANUAL:
        return {"ok": True, "status": "manual_review"}

    if choice == OfflineAction.Resolution.USE_LATEST:
        row.status = OfflineAction.Status.SYNCED
        row.conflict_reason = "Resolved: adopted server/latest state."
        row.sync_metadata = {
            **(row.sync_metadata or {}),
            "resolution_audit": audit_blob,
        }
        row.save(update_fields=["status", "conflict_reason", "sync_metadata", "updated_at"])
        row.refresh_from_db()
        _emit_offline_action_synced(row, {"resolution": "use_latest"})
        return {"ok": True, "status": "synced_abandon_local"}

    result = _apply_payload(row, force_local=True)
    if result.get("ok"):
        row.status = OfflineAction.Status.SYNCED
        row.conflict_reason = ""
        row.conflict_details = {}
        row.sync_metadata = {
            **result,
            **(row.sync_metadata or {}),
            "resolution_audit": audit_blob,
        }
        row.save(
            update_fields=[
                "status",
                "conflict_reason",
                "conflict_details",
                "sync_metadata",
                "updated_at",
            ]
        )
        row.refresh_from_db()
        _emit_offline_action_synced(row, result)
        return {"ok": True, "status": "synced_local_applied"}
    return {"ok": False, "error": result.get("error", "re-apply failed")}

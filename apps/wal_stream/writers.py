"""Per-domain WAL appliers (v4.00.0).

Each ``apply_<domain>(envelope)`` function MUST be:
  * idempotent (the txn_id dedupe protects but writers should still tolerate retries)
  * RLS-scoped (caller already entered rls_school context)
  * batched (one INSERT/UPDATE per envelope, never N+1)

The dispatcher is the only public symbol. New domains plug in here.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def dispatch(envelope: dict[str, Any]) -> None:
    domain = envelope.get("domain")
    fn = _REGISTRY.get(domain)
    if fn is None:
        raise ValueError(f"wal_stream.unknown_domain:{domain}")
    fn(envelope)


def _apply_attendance(envelope: dict[str, Any]) -> None:
    """Apply a batched attendance delta against ``apps.academics.Attendance``.

    Each action: ``{"student_id": int, "classroom_id": int, "date": iso,
    "status": "present|absent|late|excused", "remarks": str?, "session_id": str?}``

    ``session_id`` is optional and carries the WAL JS marker
    (``<classroom_id>::<date>``); when present the writer parses out the date +
    classroom so the JS doesn't have to send them as separate fields.

    Single-statement throughput via ``bulk_create(update_conflicts=True)``.
    The canonical model's ``(student, classroom, date)`` unique constraint
    enables idempotent overwrites on retry.
    """
    actions = envelope.get("actions") or []
    if not actions:
        return
    try:
        from apps.academics.models import Attendance  # type: ignore[attr-defined]
    except ImportError:
        logger.debug("wal_stream.attendance_model_unavailable")
        return
    records = []
    for a in actions:
        try:
            classroom_id, date = _resolve_attendance_session(a)
            if classroom_id is None or date is None:
                logger.warning("wal_stream.attendance_unresolved_session action=%s", a)
                continue
            records.append(Attendance(
                student_id=a["student_id"],
                classroom_id=classroom_id,
                date=date,
                status=a.get("status", "present"),
                remarks=a.get("remarks", ""),
            ))
        except KeyError as exc:
            logger.warning("wal_stream.attendance_bad_action missing=%s", exc)
            continue
    if not records:
        return
    Attendance.objects.bulk_create(
        records,
        update_conflicts=True,
        unique_fields=("student", "classroom", "date"),
        update_fields=("status", "remarks", "updated_at"),
    )


def _resolve_attendance_session(action: dict[str, Any]) -> tuple[Any, Any]:
    """Pull (classroom_id, date) out of either explicit fields or session_id marker.

    The WAL JS sends ``session_id="<classroom_id>::<date>"`` to keep the wire
    envelope compact; this helper unpacks it. Explicit fields win when both
    are present.
    """
    classroom_id = action.get("classroom_id")
    date = action.get("date")
    if classroom_id and date:
        return classroom_id, date
    marker = action.get("session_id") or ""
    if "::" in marker:
        c, _, d = marker.partition("::")
        return classroom_id or c, date or d
    return classroom_id, date


def _apply_teacher_attendance(envelope: dict[str, Any]) -> None:
    """Apply a batched teacher-attendance delta against ``apps.people.TeacherAttendance``.

    Each action: ``{"teacher_id": int, "date": iso, "status": "PRESENT|ABSENT|LATE|ON_LEAVE",
    "remarks": str?}``. The model's status enum is UPPERCASE; the writer
    normalizes whatever case the JS sent.

    Single-statement throughput via ``bulk_create(update_conflicts=True)``.
    The ``(teacher, date)`` unique constraint enables idempotent retry.
    """
    actions = envelope.get("actions") or []
    if not actions:
        return
    try:
        from apps.people.models import TeacherAttendance  # type: ignore[attr-defined]
    except ImportError:
        logger.debug("wal_stream.teacher_attendance_model_unavailable")
        return
    rows = []
    for a in actions:
        try:
            status = str(a.get("status", "PRESENT")).upper()
            if status not in {"PRESENT", "ABSENT", "LATE", "ON_LEAVE"}:
                status = "PRESENT"
            rows.append(TeacherAttendance(
                teacher_id=a["teacher_id"],
                date=a["date"],
                status=status,
                remarks=a.get("remarks", ""),
            ))
        except KeyError as exc:
            logger.warning("wal_stream.teacher_attendance_bad_action missing=%s", exc)
            continue
    if rows:
        TeacherAttendance.objects.bulk_create(
            rows,
            update_conflicts=True,
            unique_fields=("teacher", "date"),
            update_fields=("status", "remarks"),
        )


def _apply_grade(envelope: dict[str, Any]) -> None:
    """Apply a batched grade delta against ``apps.evals.OfflineMarkEntry``.

    Action shape (from the JS harvester):
      {"student_id": int, "subject_assignment_id": int,
       "academic_year_id": int, "term_id": int,
       "seq1_score"|"seq2_score"|"exam_score"|"mock_score"|"practical_score": float,
       "remarks": str}

    ``teacher_id`` is resolved server-side from the envelope's ``user_id``
    (the WS handshake captured ``self.user_id = str(user.pk)``). This keeps
    the wire envelope compact and prevents the client from forging a
    teacher attribution.
    """
    actions = envelope.get("actions") or []
    if not actions:
        return
    try:
        from apps.evals.models import OfflineMarkEntry  # type: ignore[attr-defined]
        from apps.people.models import TeacherProfile  # type: ignore[attr-defined]
    except ImportError:
        logger.debug("wal_stream.grade_model_unavailable")
        return
    teacher_id = _resolve_teacher_id_from_envelope(envelope, TeacherProfile)
    if teacher_id is None:
        logger.warning("wal_stream.grade_no_teacher user=%s", envelope.get("user_id"))
        return
    rows = []
    for a in actions:
        try:
            rows.append(OfflineMarkEntry(
                teacher_id=teacher_id,
                subject_assignment_id=a["subject_assignment_id"],
                student_id=a["student_id"],
                academic_year_id=a["academic_year_id"],
                term_id=a["term_id"],
                seq1_score=_safe_decimal(a.get("seq1_score")),
                seq2_score=_safe_decimal(a.get("seq2_score")),
                exam_score=_safe_decimal(a.get("exam_score")),
                mock_score=_safe_decimal(a.get("mock_score")),
                practical_score=_safe_decimal(a.get("practical_score")),
                remarks=a.get("remarks", "") or "",
            ))
        except KeyError as exc:
            logger.warning("wal_stream.grade_bad_action missing=%s", exc)
            continue
    if rows:
        OfflineMarkEntry.objects.bulk_create(rows, ignore_conflicts=True)


def _resolve_teacher_id_from_envelope(envelope: dict[str, Any], TeacherProfile) -> int | None:
    user_id = envelope.get("user_id")
    if not user_id:
        return None
    try:
        # tenant-isolation-allow: wal-drainer-runs-in-rls-bound-tenant-schema-context
        tp = TeacherProfile.objects.filter(user_id=user_id).only("id").first()
    except Exception as exc:  # noqa: BLE001 — DB errors must not break the drainer
        logger.debug("wal_stream.grade_teacher_lookup_failed: %s", exc)
        return None
    return getattr(tp, "id", None) if tp else None


def _safe_decimal(v) -> Any:
    """Convert JS number/string to Decimal-ready value. None passes through."""
    if v is None or v == "":
        return None
    from decimal import Decimal, InvalidOperation

    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _apply_billing_charge(envelope: dict[str, Any]) -> None:
    """Apply a batched billing-charge delta against ``apps.finance.Invoice``.

    Action shape: ``{"counterparty_id": int, "amount": str-decimal,
    "currency": str, "due_date": iso, "memo": str}``. Single-row creates only;
    we deliberately do NOT collapse invoice updates into bulk_create because
    Invoice numbering is a strict, gap-free sequence per tenant.
    """
    actions = envelope.get("actions") or []
    if not actions:
        return
    try:
        from decimal import Decimal

        from apps.finance.models import Invoice  # type: ignore[attr-defined]
    except ImportError:
        logger.debug("wal_stream.billing_model_unavailable")
        return
    for a in actions:
        try:
            Invoice.objects.create(
                counterparty_id=a["counterparty_id"],
                amount=Decimal(str(a["amount"])),
                currency=a.get("currency", "USD"),
                due_date=a.get("due_date"),
                memo=a.get("memo", ""),
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("wal_stream.billing_bad_action err=%s", exc)
            continue


def _apply_communication_send(envelope: dict[str, Any]) -> None:
    """Apply a batched communication-send delta against ``apps.communication.Message``.

    Action shape: ``{"sender_id": int, "recipient_id": int, "subject": str,
    "body": str, "school_id": str-uuid, "locale_target": str}``.

    The Message model handles its own delivery FSM (read/archived/parent) and
    triggers downstream signals; we just persist the row.
    """
    actions = envelope.get("actions") or []
    if not actions:
        return
    try:
        from apps.communication.models import Message  # type: ignore[attr-defined]
    except ImportError:
        logger.debug("wal_stream.communication_model_unavailable")
        return
    rows = []
    for a in actions:
        try:
            rows.append(Message(
                sender_id=a["sender_id"],
                recipient_id=a["recipient_id"],
                school_id=a.get("school_id"),
                subject=a["subject"][:255],
                body=a.get("body", ""),
                locale_target=a.get("locale_target", ""),
            ))
        except KeyError as exc:
            logger.warning("wal_stream.communication_bad_action missing=%s", exc)
            continue
    if rows:
        Message.objects.bulk_create(rows)


def _apply_audit_event(envelope: dict[str, Any]) -> None:
    """Append-only emit against ``MigrationCloudAuditEvent``.

    Action shape: ``{"event_type": str, "actor_id": str, "event_subject_hash": str,
    "payload_summary": dict}``. The model's ``record()`` manager method enforces
    the chain + integrity_hash + root signature; we route every action through it.
    """
    actions = envelope.get("actions") or []
    if not actions:
        return
    try:
        from apps.migration_cloud.models_audit import (  # type: ignore[attr-defined]
            MigrationCloudAuditEvent,
        )
    except ImportError:
        logger.debug("wal_stream.audit_model_unavailable")
        return
    tenant_hash = envelope.get("tenant_hash", "")
    manager = MigrationCloudAuditEvent.objects
    record = getattr(manager, "record", None)
    if not callable(record):
        logger.warning("wal_stream.audit_record_unavailable")
        return
    for a in actions:
        try:
            record(
                tenant_id_hash=tenant_hash,
                event_type=a["event_type"],
                actor_id=a.get("actor_id", ""),
                event_subject_hash=a.get("event_subject_hash", ""),
                payload_summary=a.get("payload_summary", {}),
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("wal_stream.audit_bad_action err=%s", exc)
            continue


_REGISTRY: dict[str, Callable[[dict[str, Any]], None]] = {
    "attendance": _apply_attendance,
    "teacher_attendance": _apply_teacher_attendance,
    "grade": _apply_grade,
    "billing_charge": _apply_billing_charge,
    "communication_send": _apply_communication_send,
    "audit_event": _apply_audit_event,
}

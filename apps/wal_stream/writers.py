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


class _AnnouncementRequestShim:
    """Request-like carrier so announcement feature-flag resolution works in the
    drainer, which has a bound school (from the envelope's tenant) but no HTTP
    request. Mirrors ``platform_runtime.helpers.get_effective_flags_for_school``'s
    shim so the teacher submit-for-approval flag resolves the same offline as it
    does online — only ``.school`` and ``.tenant_runtime`` are read downstream.
    """

    def __init__(self, school: Any):
        self.school = school
        self.tenant_runtime = None


def dispatch(envelope: dict[str, Any]) -> None:
    domain = envelope.get("domain")
    fn = _REGISTRY.get(domain)
    if fn is None:
        raise ValueError(f"wal_stream.unknown_domain:{domain}")
    fn(envelope)


def _ids_in_school(model, ids, school_id, *, id_field: str = "id", school_field: str = "school_id") -> set:
    """Return the subset of ``ids`` whose rows belong to ``school_id``.

    Defense-in-depth for the WAL drain: a disconnected client must not be able
    to attach another tenant's row by sending a foreign FK id in an action. The
    writer — not just RLS — enforces tenant ownership here, which matters under
    django-tenants schema mode (where ``rls_school()`` is a no-op) and for any
    referenced model that lacks its own row-level school policy.

    Fail-open on a missing ``school_id`` or a transient DB error (RLS context
    remains the backstop) so a hiccup never silently drops legitimate writes.
    """
    wanted = {i for i in ids if i is not None}
    if not wanted or not school_id:
        return wanted
    from django.db import DatabaseError

    try:
        return set(
            model.objects.filter(  # tenant-isolation-allow: explicit-school-filter-validates-client-supplied-fk-against-bound-tenant
                **{f"{id_field}__in": wanted, school_field: school_id}
            ).values_list(id_field, flat=True)
        )
    except DatabaseError as exc:
        logger.warning(
            "wal_stream.fk_validation_failed model=%s err=%s", getattr(model, "__name__", "?"), exc
        )
        return wanted


def _captured_dt(envelope: dict[str, Any]):
    """Return the offline-capture time as a tz-aware UTC datetime, or None.

    The consumer stores ``captured_at`` as epoch SECONDS. None means an older
    client that did not send a capture time — callers then fall back to plain
    last-write-wins (no conflict detection, no regression).
    """
    ts = envelope.get("captured_at")
    if not isinstance(ts, (int, float)) or isinstance(ts, bool) or ts <= 0:
        return None
    from datetime import datetime, timezone as _tz

    try:
        return datetime.fromtimestamp(float(ts), tz=_tz.utc)
    except (ValueError, OverflowError, OSError):
        return None


def _partition_stale_upserts(records, existing_ts_map, captured_dt, key_fn):
    """Split ``records`` into ``(winners, stale)`` by capture freshness.

    A record is STALE when an existing row for its key was last updated AFTER
    the offline write was captured — i.e. the online state is newer and must not
    be clobbered by a stale offline write (last-writer-wins by capture time).

    ``existing_ts_map`` maps ``key_fn(record) -> updated_at`` for rows already in
    the DB. No ``captured_dt`` (older client) or no existing row for a key means
    the record is a winner — this preserves the prior last-write-wins behavior
    exactly when capture metadata is absent.
    """
    if captured_dt is None:
        return list(records), []
    winners, stale = [], []
    for r in records:
        existing_ts = existing_ts_map.get(key_fn(r))
        if existing_ts is not None and existing_ts > captured_dt:
            stale.append(r)
        else:
            winners.append(r)
    return winners, stale


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
    # Refuse to write NULL-school rows: Attendance.school is nullable, and a row
    # with school=NULL escapes tenant-scoped reporting AND the offboarding purge
    # (orphan PII that survives a "permanent" delete). _apply_envelope always
    # stamps a resolved school_id, so a falsy value here is an anomaly — drop it.
    if not envelope.get("school_id"):
        logger.warning("wal_stream.attendance_no_school txn=%s", envelope.get("txn_id"))
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
                # bulk_create bypasses Attendance.save(); stamp the authoritative
                # server-resolved school so RLS/tenant-scoped reporting sees the row.
                school_id=envelope.get("school_id"),
            ))
        except KeyError as exc:
            logger.warning("wal_stream.attendance_bad_action missing=%s", exc)
            continue
    if not records:
        return
    # Drop any row whose client-supplied student/classroom does not belong to
    # the bound tenant (cross-tenant write defense; see _ids_in_school).
    school_id = envelope.get("school_id")
    if school_id:
        from apps.academics.models import Classroom  # type: ignore[attr-defined]
        from apps.people.models import StudentProfile  # type: ignore[attr-defined]

        valid_students = _ids_in_school(StudentProfile, [r.student_id for r in records], school_id)
        valid_classrooms = _ids_in_school(Classroom, [r.classroom_id for r in records], school_id)
        kept = [r for r in records if r.student_id in valid_students and r.classroom_id in valid_classrooms]
        if len(kept) != len(records):
            logger.warning(
                "wal_stream.attendance_cross_tenant_dropped dropped=%s", len(records) - len(kept)
            )
        records = kept
    if not records:
        return
    # Conflict resolution: never let a STALE offline write clobber newer online
    # state. If the existing row for (student, classroom, date) was updated after
    # this batch was captured offline, the online value wins and the offline one
    # is routed to the conflict stream for operator review (not silently lost).
    captured_dt = _captured_dt(envelope)
    if captured_dt is not None:
        from django.db import DatabaseError

        keys = {(r.student_id, r.classroom_id, r.date) for r in records}
        existing_ts_map: dict[tuple, Any] = {}
        try:
            rows_qs = Attendance.objects.filter(  # tenant-isolation-allow: drainer-runs-inside-rls_school-and-keys-are-this-tenants-validated-rows
                student_id__in={k[0] for k in keys},
                classroom_id__in={k[1] for k in keys},
                date__in={k[2] for k in keys},
            ).values_list("student_id", "classroom_id", "date", "updated_at")
            for s_id, c_id, d, upd in rows_qs:
                existing_ts_map[(s_id, c_id, d)] = upd
        except DatabaseError as exc:
            # Fail-open: a freshness read hiccup must not drop legitimate writes.
            logger.warning("wal_stream.attendance_freshness_read_failed err=%s", exc)
            existing_ts_map = {}
        winners, stale = _partition_stale_upserts(
            records,
            existing_ts_map,
            captured_dt,
            key_fn=lambda r: (r.student_id, r.classroom_id, r.date),
        )
        if stale:
            from apps.wal_stream.tasks import record_wal_conflicts

            record_wal_conflicts(
                envelope.get("tenant_hash", ""),
                "attendance",
                [
                    {
                        "student_id": r.student_id,
                        "classroom_id": r.classroom_id,
                        "date": str(r.date),
                        "status": r.status,
                        "txn_id": envelope.get("txn_id", ""),
                    }
                    for r in stale
                ],
            )
            logger.warning(
                "wal_stream.attendance_stale_skipped count=%s txn=%s",
                len(stale), envelope.get("txn_id"),
            )
        records = winners
    if not records:
        return
    # bulk_create's conflict-UPDATE branch does NOT run pre_save, so the auto_now
    # `updated_at` would otherwise carry the (unset) insert-time value — leaving
    # the freshness basis stale and letting a later offline write clobber a newer
    # online one. Stamp it explicitly so conflict detection stays sound.
    from django.utils import timezone as _tz

    _now = _tz.now()
    for r in records:
        r.updated_at = _now
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

    Conflict resolution mirrors ``_apply_attendance``: a stale offline write
    never clobbers a newer online correction. ``TeacherAttendance.updated_at``
    (added in people/0056) is the freshness basis; a NULL existing value (rows
    written before that migration) is treated as "no known time" → the offline
    write wins (safe last-writer-wins default).
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
                # NOTE: TeacherAttendance has no `school` column — tenant scope is
                # via teacher -> TeacherProfile.school under the drainer's RLS
                # context, so there is nothing to stamp here.
            ))
        except KeyError as exc:
            logger.warning("wal_stream.teacher_attendance_bad_action missing=%s", exc)
            continue
    if not rows:
        return
    # Cross-tenant write defense (parity with the other five writers): drop any
    # row whose client-supplied teacher_id does not belong to the bound tenant.
    # TeacherAttendance has no school column, so the FK ownership check on
    # TeacherProfile.school IS the isolation boundary here — the drainer's
    # rls_school() is a no-op under django-tenants schema mode.
    school_id = envelope.get("school_id")
    if school_id:
        from apps.people.models import TeacherProfile  # type: ignore[attr-defined]

        valid_teachers = _ids_in_school(
            TeacherProfile, [r.teacher_id for r in rows], school_id
        )
        kept = [r for r in rows if r.teacher_id in valid_teachers]
        if len(kept) != len(rows):
            logger.warning(
                "wal_stream.teacher_attendance_cross_tenant_dropped dropped=%s",
                len(rows) - len(kept),
            )
        rows = kept
    if not rows:
        return
    captured_dt = _captured_dt(envelope)
    if captured_dt is not None:
        from django.db import DatabaseError

        keys = {(r.teacher_id, r.date) for r in rows}
        existing_ts_map: dict[tuple, Any] = {}
        try:
            rows_qs = TeacherAttendance.objects.filter(  # tenant-isolation-allow: drainer-runs-inside-rls_school-scoped-via-teacher-profile-for-this-tenant
                teacher_id__in={k[0] for k in keys},
                date__in={k[1] for k in keys},
            ).values_list("teacher_id", "date", "updated_at")
            for t_id, d, upd in rows_qs:
                existing_ts_map[(t_id, d)] = upd
        except DatabaseError as exc:
            logger.warning("wal_stream.teacher_attendance_freshness_read_failed err=%s", exc)
            existing_ts_map = {}
        winners, stale = _partition_stale_upserts(
            rows,
            existing_ts_map,
            captured_dt,
            key_fn=lambda r: (r.teacher_id, r.date),
        )
        if stale:
            from apps.wal_stream.tasks import record_wal_conflicts

            record_wal_conflicts(
                envelope.get("tenant_hash", ""),
                "teacher_attendance",
                [
                    {
                        "teacher_id": r.teacher_id,
                        "date": str(r.date),
                        "status": r.status,
                        "txn_id": envelope.get("txn_id", ""),
                    }
                    for r in stale
                ],
            )
            logger.warning(
                "wal_stream.teacher_attendance_stale_skipped count=%s txn=%s",
                len(stale), envelope.get("txn_id"),
            )
        rows = winners
    if rows:
        from django.utils import timezone as _tz

        _now = _tz.now()
        for r in rows:
            r.updated_at = _now
        TeacherAttendance.objects.bulk_create(
            rows,
            update_conflicts=True,
            unique_fields=("teacher", "date"),
            update_fields=("status", "remarks", "updated_at"),
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
        from django.utils import timezone

        from apps.evals.models import OfflineMarkEntry  # type: ignore[attr-defined]
        from apps.people.models import TeacherProfile  # type: ignore[attr-defined]
    except ImportError:
        logger.debug("wal_stream.grade_model_unavailable")
        return
    teacher_id = _resolve_teacher_id_from_envelope(envelope, TeacherProfile)
    if teacher_id is None:
        logger.warning("wal_stream.grade_no_teacher user=%s", envelope.get("user_id"))
        return
    now = timezone.now()
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
                # created_offline_at is NOT NULL with no default; bulk_create
                # bypasses any model default so it MUST be set here or every
                # offline grade envelope raises IntegrityError and wedges the
                # tenant's drain (head-of-line poison pill).
                created_offline_at=now,
            ))
        except KeyError as exc:
            logger.warning("wal_stream.grade_bad_action missing=%s", exc)
            continue
    if not rows:
        return
    # Drop any mark whose client-supplied student does not belong to the bound
    # tenant (cross-tenant write defense).
    school_id = envelope.get("school_id")
    if school_id:
        from apps.people.models import StudentProfile  # type: ignore[attr-defined]

        valid_students = _ids_in_school(StudentProfile, [r.student_id for r in rows], school_id)
        kept = [r for r in rows if r.student_id in valid_students]
        if len(kept) != len(rows):
            logger.warning(
                "wal_stream.grade_cross_tenant_dropped dropped=%s", len(rows) - len(kept)
            )
        rows = kept
    if rows:
        _bulk_create_marks_idempotent(OfflineMarkEntry, rows)


def _grade_natural_key(row) -> tuple:
    """The natural key the SODP grade applier dedupes a pending mark on."""
    return (
        row.teacher_id,
        row.subject_assignment_id,
        row.student_id,
        row.academic_year_id,
        row.term_id,
    )


def _bulk_create_marks_idempotent(OfflineMarkEntry, rows: list) -> None:
    """Create offline marks idempotently — the guard the SODP grade path has.

    WAL delivery is at-least-once and ``OfflineMarkEntry`` carries no unique
    constraint, so ``bulk_create(..., ignore_conflicts=True)`` dedupes NOTHING:
    a re-applied envelope inserts duplicate rows. Mirror the SODP applier
    (``platform_runtime.offline_queue._apply_grading``): skip any (teacher,
    subject_assignment, student, academic_year, term) that already has a pending
    row, and collapse duplicates appearing twice within the same batch.
    """
    if not rows:
        return
    existing = set(
        OfflineMarkEntry.objects.filter(
            status="pending",
            teacher_id__in={r.teacher_id for r in rows},
            subject_assignment_id__in={r.subject_assignment_id for r in rows},
            student_id__in={r.student_id for r in rows},
            academic_year_id__in={r.academic_year_id for r in rows},
            term_id__in={r.term_id for r in rows},
        ).values_list(
            "teacher_id",
            "subject_assignment_id",
            "student_id",
            "academic_year_id",
            "term_id",
        )
    )
    seen: set = set()
    fresh = []
    for row in rows:
        key = _grade_natural_key(row)
        if key in existing or key in seen:
            continue
        seen.add(key)
        fresh.append(row)
    if fresh:
        OfflineMarkEntry.objects.bulk_create(fresh)


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


# NOTE: There is intentionally NO `billing_charge` WAL writer. The previous one
# built `Invoice(amount=, currency=, memo=)` — fields that do NOT exist on the
# model (real fields: total_amount/notes) and omitted the required PROTECT
# `profile` FK, so every offline charge raised TypeError, was swallowed, and the
# money write was silently lost AFTER the idempotency key was already burned. It
# also had no client producer. Offline finance is handled by the proven
# OfflineAction finance handlers (apps/finance/offline_workflow_handlers.py:
# payment_receipt / cash_closure / split_allocation). A real billing_charge WAL
# domain must be rebuilt against the actual Invoice contract WITH DB tests before
# being re-added to consumers._ALLOWED_DOMAINS and the registry below.


def _apply_communication_send(envelope: dict[str, Any]) -> None:
    """Apply a batched communication-send delta against ``apps.communication.Message``.

    Action shape: ``{"recipient_id": int, "subject": str, "body": str,
    "locale_target": str}``.

    The **sender is derived server-side from the authenticated socket's
    ``user_id``** (captured at the WS handshake), NOT from the client action —
    a disconnected client must never be able to forge a message attributed to
    another user (audit: offline messaging outbox hardening). ``school_id`` is
    likewise taken from the envelope's bound tenant, ignoring any client value.
    The Message model handles its own delivery FSM + downstream signals.
    """
    actions = envelope.get("actions") or []
    if not actions:
        return
    try:
        from apps.communication.models import Message  # type: ignore[attr-defined]
    except ImportError:
        logger.debug("wal_stream.communication_model_unavailable")
        return
    sender_id = envelope.get("user_id")
    if not sender_id:
        logger.warning("wal_stream.communication_no_sender")
        return
    envelope_school_id = envelope.get("school_id")
    rows = []
    for a in actions:
        try:
            rows.append(Message(
                sender_id=sender_id,
                recipient_id=a["recipient_id"],
                school_id=envelope_school_id or a.get("school_id"),
                subject=str(a.get("subject") or "")[:255] or "Message",
                body=a.get("body", ""),
                locale_target=a.get("locale_target", ""),
            ))
        except KeyError as exc:
            logger.warning("wal_stream.communication_bad_action missing=%s", exc)
            continue
    if not rows:
        return
    # Drop messages to recipients who are not members of the bound tenant — a
    # disconnected client must not be able to message a user in another school.
    if envelope_school_id:
        from apps.schools.models import SchoolMembership  # type: ignore[attr-defined]

        valid_recipients = _ids_in_school(
            SchoolMembership,
            [r.recipient_id for r in rows],
            envelope_school_id,
            id_field="user_id",
        )
        kept = [r for r in rows if r.recipient_id in valid_recipients]
        if len(kept) != len(rows):
            logger.warning(
                "wal_stream.communication_cross_tenant_dropped dropped=%s", len(rows) - len(kept)
            )
        rows = kept
    if rows:
        Message.objects.bulk_create(rows)


def _apply_thread_message_create(envelope: dict[str, Any]) -> None:
    """Apply offline-composed GROUP thread posts against ``ThreadMessage``.

    Action shape: ``{"thread_id": int, "content": str, "locale_target": str}``.

    The **author is derived server-side from the authenticated socket's
    ``user_id``** (never trusted from the client), and a post is DROPPED unless
    that author is a current member of the target thread AND the thread belongs
    to the bound tenant — a disconnected client must not be able to post into a
    thread it is not in, or into another school's thread. Unlike
    ``_apply_communication_send`` this uses ``.create()`` (not ``bulk_create``)
    so ``ThreadMessage.save()`` runs and the post_save fan-out (member
    notifications + mute handling) fires for each offline-delivered post.
    """
    actions = envelope.get("actions") or []
    if not actions:
        return
    try:
        from apps.communication.models import MessageThread, ThreadMessage
    except ImportError:
        logger.debug("wal_stream.thread_message_model_unavailable")
        return
    author_id = envelope.get("user_id")
    if not author_id:
        logger.warning("wal_stream.thread_message_no_author")
        return
    school_id = envelope.get("school_id")

    wanted_thread_ids = {a.get("thread_id") for a in actions if a.get("thread_id")}
    if not wanted_thread_ids:
        return
    # The author may only post to their own (non-archived) member threads, scoped
    # to the bound tenant. One membership query, then filter the actions.
    # tenant-isolation-allow: threads-scoped-to-author-membership-and-bound-school
    threads_qs = MessageThread.objects.filter(
        pk__in=wanted_thread_ids, members__id=author_id, is_archived=False
    )
    if school_id:
        threads_qs = threads_qs.filter(school_id=school_id)
    allowed_thread_ids = set(threads_qs.values_list("id", flat=True))

    dropped = 0
    for a in actions:
        tid = a.get("thread_id")
        content = (a.get("content") or "").strip()
        if not tid or tid not in allowed_thread_ids:
            if tid:
                dropped += 1
            continue
        if not content:
            continue
        try:
            ThreadMessage.objects.create(
                thread_id=tid,
                author_id=author_id,
                school_id=school_id,
                content=content,
                locale_target=str(a.get("locale_target") or "")[:10],
            )
        except (ValueError, TypeError) as exc:
            logger.warning(
                "wal_stream.thread_message_bad_action err=%s", type(exc).__name__
            )
    if dropped:
        logger.warning(
            "wal_stream.thread_message_unauthorized_dropped dropped=%s", dropped
        )


def _apply_announcement_create(envelope: dict[str, Any]) -> None:
    """Apply an offline-composed school-wide announcement.

    Action shape: ``{"title": str, "content": str, "announcement_type": str,
    "audience": str, "is_urgent": bool}``.

    The **author is the authenticated socket's** ``user_id`` and the
    publish/approval decision is re-derived **server-side** from that author's
    role — never trusted from the client. A teacher who can only submit for
    approval has their offline announcement land as ``PENDING_APPROVAL``; only a
    role that may publish school-wide gets ``PUBLISHED``. This mirrors the
    online ``announcement_create`` view's gate so the offline path can never be
    used to bypass approval and broadcast to the whole school.
    """
    actions = envelope.get("actions") or []
    if not actions:
        return
    try:
        from apps.communication.models import Announcement, log_announcement_audit
        from apps.communication.views_announcements import (
            _can_create_school_wide_announcement,
            _can_submit_for_approval,
        )
    except ImportError:
        logger.debug("wal_stream.announcement_model_unavailable")
        return
    sender_id = envelope.get("user_id")
    if not sender_id:
        logger.warning("wal_stream.announcement_no_sender")
        return
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        sender = User.objects.get(pk=sender_id)  # tenant-isolation-allow: wal-author-resolved-by-pk-from-authenticated-socket
    except User.DoesNotExist:
        logger.warning("wal_stream.announcement_unknown_sender")
        return

    school_id = envelope.get("school_id")
    # Resolve the bound school so the submit-for-approval feature flag resolves
    # the same offline as online (it is school-scoped). The drainer already
    # entered rls_school(school_id), so this read is correctly tenant-scoped.
    school_obj = None
    if school_id:
        from django.db import DatabaseError

        from apps.schools.models import School

        try:
            school_obj = School.objects.filter(pk=school_id).first()  # tenant-isolation-allow: drainer-runs-inside-rls_school-for-this-envelope-tenant
        except DatabaseError:
            school_obj = None

    can_publish = _can_create_school_wide_announcement(sender)
    can_submit = _can_submit_for_approval(sender, _AnnouncementRequestShim(school_obj))
    if not (can_publish or can_submit):
        # Mirrors the online view's 403: a user who could not have created this
        # announcement online cannot do so via the offline rail either. The
        # writer — not the client form — is the authorization boundary.
        logger.warning("wal_stream.announcement_forbidden author=%s", sender_id)
        return
    status = (
        Announcement.Status.PUBLISHED
        if can_publish
        else Announcement.Status.PENDING_APPROVAL
    )

    valid_types = set(Announcement.AnnouncementType.values)
    valid_audiences = set(Announcement.Audience.values)
    for a in actions:
        title = str(a.get("title") or "").strip()[:255]
        content = str(a.get("content") or "").strip()
        if not title or not content:
            logger.warning("wal_stream.announcement_bad_action empty_title_or_content")
            continue
        a_type = a.get("announcement_type")
        if a_type not in valid_types:
            a_type = Announcement.AnnouncementType.GENERAL
        audience = a.get("audience")
        if audience not in valid_audiences:
            audience = Announcement.Audience.ALL
        ann = Announcement(
            title=title,
            content=content,
            school_id=school_id,
            announcement_type=a_type,
            audience=audience,
            status=status,
            is_urgent=bool(a.get("is_urgent")),
            created_by_id=sender_id,
        )
        # save() (not bulk_create) so the school fallback fires and we can write
        # the audit row the online path also writes.
        ann.save()
        audit_action = (
            "submitted_for_approval"
            if status == Announcement.Status.PENDING_APPROVAL
            else "created"
        )
        log_announcement_audit(ann, sender, audit_action)


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
    "communication_send": _apply_communication_send,
    "thread_message_create": _apply_thread_message_create,
    "announcement_create": _apply_announcement_create,
    "audit_event": _apply_audit_event,
}

"""Wave R-A (v3.96.0 — 2026-05-26) — Bulk attendance convenience kernel.

The teacher's most common roll-call action is "mark every student in this class
present right now". The existing ``AttendanceBulkView`` accepts a payload of
per-student rows; this kernel adds the missing one-call convenience:

- ``mark_whole_class(classroom_id, date, default_status, exceptions=...)`` —
  fetch every active student in the classroom under tenant scope, build the
  bulk payload, return a typed result describing creates / updates / skips.
- ``parse_attendance_csv(text)`` — parse a CSV with header
  ``student_external_id,status[,remarks]`` and return a normalized record
  list. Pure-function; no DB writes. The caller then funnels through
  ``apply_attendance_rows(...)``.
- ``apply_attendance_rows(classroom_id, date, rows, ...)`` — single write
  path. Uses a **constant-query** bulk upsert (prefetch + ``bulk_create`` /
  ``bulk_update``) so re-runs and large classes do not O(n) round-trip.

No new model; the existing ``apps.academics.models.Attendance`` is the
storage. Tenant isolation is enforced because ``Classroom`` (and through it
``StudentProfile``) carries a ``school`` FK and every query in this module is
scoped on it.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Iterable, Mapping


_VALID_STATUS = {"present", "absent", "late", "excused"}


@dataclass(frozen=True)
class AttendanceRow:
    """One normalized attendance instruction."""

    student_id: int | None = None
    student_external_id: str = ""
    status: str = "present"
    remarks: str = ""


@dataclass
class BulkAttendanceResult:
    """What ``mark_whole_class`` / ``apply_attendance_rows`` produced."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[dict] = field(default_factory=list)
    student_count: int = 0

    def as_dict(self) -> dict:
        return {
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "errors": list(self.errors),
            "student_count": self.student_count,
        }


def normalize_status(raw: str) -> str:
    s = (raw or "present").strip().lower()
    if s not in _VALID_STATUS:
        raise ValueError(f"Unknown attendance status: {raw!r}")
    return s


def parse_attendance_csv(text: str) -> list[AttendanceRow]:
    """Parse a teacher-uploaded CSV.

    Required header columns: ``student_external_id``, ``status``.
    Optional column: ``remarks``.
    """
    rows: list[AttendanceRow] = []
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return rows
    fieldset = {f.strip().lower() for f in reader.fieldnames}
    if "student_external_id" not in fieldset or "status" not in fieldset:
        raise ValueError(
            "CSV must include columns 'student_external_id' and 'status'.",
        )
    for raw in reader:
        # Normalize header capitalisation so teachers can paste Excel exports.
        clean = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        ext_id = clean.get("student_external_id", "")
        if not ext_id:
            continue
        rows.append(
            AttendanceRow(
                student_external_id=ext_id,
                status=normalize_status(clean.get("status", "present")),
                remarks=clean.get("remarks", "")[:255],
            )
        )
    return rows


def mark_whole_class(
    *,
    classroom_id: int,
    date_value: date_type,
    default_status: str = "present",
    exceptions: Mapping[int, str] | None = None,
    school_id: int | None = None,
    actor_user_id: int | None = None,
    db_runner=None,
    emit_signals: bool = True,
) -> BulkAttendanceResult:
    """Mark every active student in ``classroom_id`` with ``default_status``.

    ``exceptions`` maps ``student_id`` → status override (e.g. mark whole class
    present except student 17 who is absent). ``school_id`` is the tenant
    scope and MUST be supplied by the caller (the view layer derives it from
    ``request.tenant`` / ``request.user.school``).

    ``db_runner`` is a thin seam so tests can inject a fake "fetch students +
    upsert rows" without spinning up the full ORM stack.
    ``emit_signals`` defaults True so guardian/platform post_save side effects
    still run; query-count proofs may pass False to isolate the upsert SQL.
    """
    status = normalize_status(default_status)
    exceptions_map = {int(k): normalize_status(v) for k, v in (exceptions or {}).items()}

    runner = db_runner or _default_db_runner
    return runner(
        classroom_id=classroom_id,
        date_value=date_value,
        default_status=status,
        exceptions=exceptions_map,
        school_id=school_id,
        actor_user_id=actor_user_id,
        emit_signals=emit_signals,
    )


def apply_attendance_rows(
    *,
    classroom_id: int,
    date_value: date_type,
    rows: Iterable[AttendanceRow],
    school_id: int | None = None,
    db_runner=None,
    emit_signals: bool = True,
) -> BulkAttendanceResult:
    """Apply an explicit list of rows (typically from CSV upload)."""
    runner = db_runner or _default_apply_runner
    return runner(
        classroom_id=classroom_id,
        date_value=date_value,
        rows=list(rows),
        school_id=school_id,
        emit_signals=emit_signals,
    )


def apply_student_status_map(
    *,
    classroom_id: int,
    date_value: date_type,
    school_id,
    statuses: Mapping[int, str],
    remarks: Mapping[int, str] | None = None,
    emit_signals: bool = True,
) -> BulkAttendanceResult:
    """Portal roll-call write path — constant-query upsert by student_id."""
    rows = [
        AttendanceRow(
            student_id=int(sid),
            status=normalize_status(status),
            remarks=(remarks or {}).get(int(sid), "")[:255],
        )
        for sid, status in (statuses or {}).items()
    ]
    return apply_attendance_rows(
        classroom_id=classroom_id,
        date_value=date_value,
        rows=rows,
        school_id=school_id,
        emit_signals=emit_signals,
    )


def _emit_attendance_saved(instances: list, *, created: bool) -> None:
    """bulk_create/bulk_update skip model signals — re-emit post_save for side effects."""
    if not instances:
        return
    from django.db.models.signals import post_save

    from apps.academics.models import Attendance  # type: ignore

    for instance in instances:
        post_save.send(
            sender=Attendance,
            instance=instance,
            created=created,
            raw=False,
            using=instance._state.db,
            update_fields=None,
        )


def _bulk_upsert_attendance(
    *,
    classroom,
    date_value: date_type,
    school_id,
    specs: list[tuple[object, str, str]],
    emit_signals: bool = True,
) -> BulkAttendanceResult:
    """Prefetch + bulk_create/bulk_update — query count independent of class size."""
    from django.utils import timezone

    from apps.academics.models import Attendance  # type: ignore

    result = BulkAttendanceResult(student_count=len(specs))
    if not specs:
        return result

    student_ids = [int(getattr(s, "pk")) for s, _st, _rm in specs]
    # tenant-isolation-allow: bulk-attendance-upsert-confined-to-classroom-school
    existing = {
        int(a.student_id): a
        for a in Attendance.objects.filter(
            classroom=classroom,
            date=date_value,
            student_id__in=student_ids,
        )
    }

    to_create: list = []
    to_update: list = []
    now = timezone.now()
    for student, status, remarks in specs:
        sid = int(student.pk)
        row = existing.get(sid)
        if row is None:
            to_create.append(
                Attendance(
                    student=student,
                    classroom=classroom,
                    date=date_value,
                    status=status,
                    remarks=remarks or "",
                    school_id=school_id,
                )
            )
            continue
        changed = False
        if row.status != status:
            row.status = status
            changed = True
        if (row.remarks or "") != (remarks or ""):
            row.remarks = remarks or ""
            changed = True
        if row.school_id is None and school_id is not None:
            row.school_id = school_id
            changed = True
        if changed:
            row.updated_at = now
            to_update.append(row)
        else:
            result.skipped += 1

    if to_create:
        Attendance.objects.bulk_create(to_create)
        result.created = len(to_create)
        if emit_signals:
            _emit_attendance_saved(to_create, created=True)
    if to_update:
        Attendance.objects.bulk_update(
            to_update,
            ["status", "remarks", "school_id", "updated_at"],
        )
        result.updated = len(to_update)
        if emit_signals:
            _emit_attendance_saved(to_update, created=False)
    return result


def _default_db_runner(
    *,
    classroom_id: int,
    date_value: date_type,
    default_status: str,
    exceptions: Mapping[int, str],
    school_id: int | None,
    actor_user_id: int | None,
    emit_signals: bool = True,
) -> BulkAttendanceResult:
    """Real Django runner — kept thin so the kernel stays test-friendly."""
    # Lazy imports so SimpleTestCase tests that inject a fake runner don't
    # need to bring up the Django ORM.
    from apps.academics.models import Classroom  # type: ignore
    from apps.people.models import StudentProfile  # type: ignore

    if school_id is None:
        raise ValueError("school_id is required for tenant-scoped bulk mark")

    # tenant-isolation-allow: bulk-attendance-classroom-confined-to-school-tenant
    classroom = Classroom.objects.filter(
        id=classroom_id, school_id=school_id,
    ).first()
    if classroom is None:
        return BulkAttendanceResult(errors=[{"classroom_id": classroom_id, "reason": "not_found"}])

    # tenant-isolation-allow: bulk-attendance-students-confined-to-classroom-school
    students = list(
        StudentProfile.objects.filter(
            classroom=classroom, school_id=school_id,
        ).only("id", "school_id"),
    )
    specs = [
        (student, exceptions.get(student.id, default_status), "")
        for student in students
    ]
    return _bulk_upsert_attendance(
        classroom=classroom,
        date_value=date_value,
        school_id=school_id,
        specs=specs,
        emit_signals=emit_signals,
    )


def _default_apply_runner(
    *,
    classroom_id: int,
    date_value: date_type,
    rows: list[AttendanceRow],
    school_id: int | None,
    emit_signals: bool = True,
) -> BulkAttendanceResult:
    from apps.academics.models import Classroom  # type: ignore
    from apps.people.models import StudentProfile  # type: ignore

    if school_id is None:
        raise ValueError("school_id is required for tenant-scoped bulk apply")

    # tenant-isolation-allow: bulk-attendance-csv-classroom-confined-to-school-tenant
    classroom = Classroom.objects.filter(
        id=classroom_id, school_id=school_id,
    ).first()
    if classroom is None:
        return BulkAttendanceResult(errors=[{"classroom_id": classroom_id, "reason": "not_found"}])

    result = BulkAttendanceResult()
    # Match the CSV "student_external_id" against ANY identifier the school might have
    # keyed their roster by (student_code / admission_number / exam_candidate_number),
    # so the upload tolerates whichever external id they exported. The prior code read
    # a non-existent ``external_id`` field and raised FieldError (500) on every apply.
    id_fields = ("student_code", "admission_number", "exam_candidate_number")
    # tenant-isolation-allow: bulk-attendance-student-lookup-confined-to-classroom-school
    students_by_ext: dict[str, object] = {}
    students_by_id: dict[int, object] = {}
    for s in StudentProfile.objects.filter(
        classroom=classroom, school_id=school_id,
    ).only("id", "school_id", *id_fields):
        students_by_id[int(s.pk)] = s
        for fld in id_fields:
            val = getattr(s, fld, None)
            if val:
                students_by_ext[str(val)] = s
    result.student_count = len(students_by_id)

    specs: list[tuple[object, str, str]] = []
    for row in rows:
        student = None
        if row.student_id is not None:
            student = students_by_id.get(int(row.student_id))
        if student is None and row.student_external_id:
            student = students_by_ext.get(row.student_external_id)
        if student is None:
            result.skipped += 1
            result.errors.append(
                {
                    "student_id": row.student_id,
                    "student_external_id": row.student_external_id,
                    "reason": "not_in_classroom",
                },
            )
            continue
        specs.append((student, row.status, row.remarks or ""))

    upsert = _bulk_upsert_attendance(
        classroom=classroom,
        date_value=date_value,
        school_id=school_id,
        specs=specs,
        emit_signals=emit_signals,
    )
    result.created = upsert.created
    result.updated = upsert.updated
    result.skipped += upsert.skipped
    return result

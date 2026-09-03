"""Materialize preserved schedule DFV rows into first-class ``ScheduleEntry`` rows.

Schedule imports land as ``DynamicFieldValue`` (``entity_type=schedule``) because
raw SIS exports lack the solved timetable graph. After teaching-grid closure
(classrooms, subjects, teacher assignments exist), this pass converts each
preserved row when every reference resolves unambiguously.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, time, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DAY_ALIASES: dict[str, int] = {
    "monday": 0,
    "mon": 0,
    "1": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "2": 1,
    "wednesday": 2,
    "wed": 2,
    "3": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "4": 3,
    "friday": 4,
    "fri": 4,
    "5": 4,
    "saturday": 5,
    "sat": 5,
    "6": 5,
    "sunday": 6,
    "sun": 6,
    "7": 6,
}

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def _parse_day(raw: str) -> Optional[int]:
    key = (raw or "").strip().lower()
    if not key:
        return None
    if key.isdigit():
        iso = int(key)
        if 1 <= iso <= 7:
            return iso - 1
    return _DAY_ALIASES.get(key)


def _parse_time(raw: str) -> Optional[time]:
    text = (raw or "").strip()
    if not text:
        return None
    match = _TIME_RE.match(text)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    second = int(match.group(3) or 0)
    if hour > 23 or minute > 59 or second > 59:
        return None
    return time(hour, minute, second)


def _dominant_specialty_id(school, classroom_id) -> Optional[int]:
    from apps.people.models import StudentProfile

    spec_ids = list(
        StudentProfile.objects.filter(
            school=school, classroom_id=classroom_id, is_active=True
        )
        .exclude(specialty__isnull=True)
        .values_list("specialty_id", flat=True)
    )
    if not spec_ids:
        return None
    counts = Counter(spec_ids)
    top_id, top_n = counts.most_common(1)[0]
    if len(counts) == 1:
        return top_id
    second_n = counts.most_common(2)[1][1] if len(counts) > 1 else 0
    if top_n >= second_n * 2:
        return top_id
    return None


def _record_payload(dfv_row) -> dict[str, str]:
    payload = (dfv_row.value_json or {}).get("v")
    if isinstance(payload, dict):
        return {str(k): str(v) for k, v in payload.items() if v not in (None, "")}
    return {}


def _resolve_classroom(school, section_ref: str):
    from apps.academics.models import Classroom

    ref = (section_ref or "").strip()
    if not ref:
        return None
    return (
        Classroom.objects.filter(school=school, name__iexact=ref).first()
        or Classroom.objects.filter(school=school, code__iexact=ref).first()
    )


def _resolve_subject(school, record: dict[str, str]):
    from apps.academics.models import Subject

    for key in (
        "subject",
        "subject_name",
        "course",
        "course_name",
        "subject_code",
    ):
        name = (record.get(key) or "").strip()
        if not name:
            continue
        subject = (
            Subject.objects.filter(school=school, name__iexact=name).first()
            or Subject.objects.filter(school=school, code__iexact=name).first()
        )
        if subject is not None:
            return subject
    return None


def _resolve_teacher_user(school, record: dict[str, str], *, assignment):
    from apps.evals.models import TeacherAssignment
    from apps.people.models import TeacherProfile

    for key in ("teacher_username", "teacher_external_id", "staff_id", "teacher"):
        token = (record.get(key) or "").strip()
        if not token:
            continue
        profile = (
            TeacherProfile.objects.filter(school=school, staff_id__iexact=token)
            .select_related("user")
            .first()
        )
        if profile is None and "@" not in token:
            profile = (
                TeacherProfile.objects.filter(
                    school=school, user__username__iexact=token
                )
                .select_related("user")
                .first()
            )
        if profile is not None and getattr(profile, "user_id", None):
            return profile.user

    if assignment is not None:
        link = (
            TeacherAssignment.objects.filter(
                school=school,
                subject_assignment=assignment,
                is_active=True,
            )
            .select_related("teacher__user")
            .first()
        )
        if link is not None and getattr(link.teacher, "user_id", None):
            return link.teacher.user
    return None


def _ensure_time_slot(school, day: int, start: time, end: time):
    from apps.academics.scheduling import TimeSlot

    slot, created = TimeSlot.objects.get_or_create(
        school=school,
        day_of_week=day,
        start_time=start,
        end_time=end,
        defaults={
            "slot_name": start.strftime("%H:%M"),
            "is_active": True,
        },
    )
    if not slot.is_active:
        slot.is_active = True
        slot.save(update_fields=["is_active"])
    return slot, created


def _ensure_room(school, label: str):
    from apps.academics.scheduling import Room

    name = (label or "Imported room").strip()[:100]
    room, _created = Room.objects.get_or_create(
        school=school,
        name=name,
        defaults={
            "room_type": "CLASSROOM",
            "capacity": 30,
            "is_available": True,
        },
    )
    return room


def _import_schedule_owner(school):
    from django.contrib.auth import get_user_model

    from apps.people.models import TeacherProfile

    profile = (
        TeacherProfile.objects.filter(
            school=school, is_active=True, user__isnull=False
        )
        .select_related("user")
        .order_by("pk")
        .first()
    )
    if profile is not None:
        return profile.user
    User = get_user_model()
    return User.objects.filter(is_superuser=True).order_by("pk").first()


def _ensure_import_schedule(school, *, year, term, created_by):
    from apps.academics.scheduling import Schedule

    name = "Migration Cloud import"
    schedule = (
        Schedule.objects.filter(
            academic_year=year,
            term=term,
            name=name,
            status="DRAFT",
        )
        .order_by("-pk")
        .first()
    )
    if schedule is not None:
        return schedule
    return Schedule.objects.create(
        name=name,
        academic_year=year,
        term=term,
        status="DRAFT",
        created_by=created_by,
        notes="Auto-materialized from preserved schedule import rows.",
    )


def _resolve_subject_assignment(school, *, year, classroom, subject, specialty_id):
    from apps.academics.models import SubjectAssignment

    qs = SubjectAssignment.objects.filter(
        school=school,
        academic_year=year,
        classroom=classroom,
        subject=subject,
    )
    if specialty_id is not None:
        qs = qs.filter(specialty_id=specialty_id)
    assignments = list(qs[:2])
    if len(assignments) == 1:
        return assignments[0]
    return None


def materialize_schedule_from_import_dfv(
    school, *, dry_run: bool = False
) -> dict[str, Any]:
    """Convert preserved schedule DFV rows into ``ScheduleEntry`` when possible."""
    from apps.academics.models import AcademicYear, Term
    from apps.metadata.models import DynamicFieldValue

    if school is None:
        return {"skipped": True, "reason": "no_school"}

    dfv_rows = DynamicFieldValue.objects.filter(
        school=school,
        entity_type="schedule",
        field_key="record",
    )
    total = dfv_rows.count()
    if total == 0:
        return {"skipped": True, "reason": "no_schedule_dfv", "dfv_rows": 0}

    year = (
        AcademicYear.objects.filter(school=school, is_active=True).first()
        or AcademicYear.objects.filter(school=school).order_by("-start_date").first()
    )
    if year is None:
        return {"skipped": True, "reason": "no_academic_year", "dfv_rows": total}

    term = (
        Term.objects.filter(school=school, academic_year=year, is_active=True)
        .order_by("position", "start_date")
        .first()
        or Term.objects.filter(school=school, academic_year=year)
        .order_by("position", "start_date")
        .first()
    )
    if term is None:
        return {"skipped": True, "reason": "no_term", "dfv_rows": total}

    created = 0
    skipped_missing_refs = 0
    skipped_ambiguous = 0
    skipped_existing = 0
    skipped_unparseable = 0

    owner = None if dry_run else _import_schedule_owner(school)
    schedule = None

    for dfv in dfv_rows.iterator():
        record = _record_payload(dfv)
        section = (
            record.get("section_external_id")
            or record.get("section_id")
            or record.get("class_id")
            or ""
        ).strip()
        day_raw = record.get("day_of_week") or record.get("day") or ""
        start_raw = record.get("start_time") or record.get("begin_time") or ""
        end_raw = record.get("end_time") or record.get("finish_time") or ""

        day = _parse_day(day_raw)
        start = _parse_time(start_raw)
        if day is None or start is None:
            skipped_unparseable += 1
            continue

        end = _parse_time(end_raw)
        if end is None:
            end = (datetime.combine(datetime.today(), start) + timedelta(hours=1)).time()

        classroom = _resolve_classroom(school, section)
        if classroom is None:
            skipped_missing_refs += 1
            continue

        subject = _resolve_subject(school, record)
        if subject is None:
            skipped_missing_refs += 1
            continue

        specialty_id = _dominant_specialty_id(school, classroom.pk)
        assignment = _resolve_subject_assignment(
            school,
            year=year,
            classroom=classroom,
            subject=subject,
            specialty_id=specialty_id,
        )
        if assignment is None:
            skipped_ambiguous += 1
            continue

        teacher_user = _resolve_teacher_user(
            school, record, assignment=assignment
        )
        if teacher_user is None:
            skipped_missing_refs += 1
            continue

        if dry_run:
            created += 1
            continue

        if schedule is None:
            schedule = _ensure_import_schedule(
                school, year=year, term=term, created_by=owner
            )

        time_slot, _ = _ensure_time_slot(school, day, start, end)
        room = _ensure_room(school, record.get("room") or record.get("location") or "")

        from apps.academics.scheduling import ScheduleEntry

        exists = ScheduleEntry.objects.filter(
            schedule=schedule,
            classroom=classroom,
            subject=subject,
            teacher=teacher_user,
            room=room,
            time_slot=time_slot,
            is_cancelled=False,
        ).exists()
        if exists:
            skipped_existing += 1
            continue

        try:
            ScheduleEntry.objects.create(
                schedule=schedule,
                classroom=classroom,
                subject=subject,
                teacher=teacher_user,
                room=room,
                time_slot=time_slot,
                notes="Materialized from Migration Cloud schedule import.",
            )
            created += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "schedule_materializer: entry failed school=%s dfv=%s: %s",
                getattr(school, "pk", "?"),
                dfv.pk,
                exc,
            )
            skipped_ambiguous += 1

    return {
        "dfv_rows": total,
        "schedule_entries_created": created,
        "skipped_missing_refs": skipped_missing_refs,
        "skipped_ambiguous": skipped_ambiguous,
        "skipped_existing": skipped_existing,
        "skipped_unparseable": skipped_unparseable,
        "schedule_id": getattr(schedule, "pk", None),
    }

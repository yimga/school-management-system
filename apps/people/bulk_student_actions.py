"""Bulk student roster mutations for backend operator lists."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.people.models import StudentProfile

MAX_BULK_IDS = 200

ALLOWED_STATUSES = frozenset(choice[0] for choice in StudentProfile.Status.choices)


def parse_student_id_list(raw_ids: Any) -> list[int]:
    if not raw_ids:
        return []
    if not isinstance(raw_ids, (list, tuple)):
        return []
    out: list[int] = []
    for item in raw_ids:
        if isinstance(item, int) and item > 0:
            out.append(item)
        else:
            text = str(item or "").strip()
            if text.isdigit():
                out.append(int(text))
        if len(out) >= MAX_BULK_IDS:
            break
    return out


def bulk_set_student_status(
    *,
    student_ids: list[int],
    status: str,
    school,
) -> dict[str, Any]:
    status = str(status or "").strip().upper()
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"Unsupported status: {status}")
    if not student_ids:
        raise ValueError("Select at least one student.")
    if school is None:
        raise ValueError("Tenant context required for bulk roster mutation.")

    qs = StudentProfile.objects.filter(pk__in=student_ids, is_active=True)
    from apps.tenancy.queryset_boundary import scoped_queryset_for_school

    qs = scoped_queryset_for_school(qs, school)
    students = list(qs.order_by("last_name", "first_name"))
    found_ids = {student.pk for student in students}
    missing = [str(sid) for sid in student_ids if sid not in found_ids]

    results: list[dict[str, Any]] = []
    for student in students:
        if student.status == status:
            results.append(
                {
                    "id": student.pk,
                    "ok": True,
                    "message": "Already set.",
                    "status": status,
                }
            )
            continue
        student.status = status
        with transaction.atomic():
            student.save(update_fields=["status", "updated_at"])
        results.append(
            {
                "id": student.pk,
                "ok": True,
                "message": f"Status set to {status}.",
                "status": status,
            }
        )

    for mid in missing:
        results.append({"id": mid, "ok": False, "error": "Student not found."})

    succeeded = sum(1 for row in results if row.get("ok"))
    return {
        "ok": succeeded > 0,
        "status": status,
        "processed": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
        "results": results,
    }

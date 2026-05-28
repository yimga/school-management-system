"""QR / card-sweep attendance pilot (batch 1534) — bulk path, phone-ban-safe."""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import date as date_type

from django.conf import settings

from apps.academics.bulk_attendance import (
    AttendanceRow,
    BulkAttendanceResult,
    apply_attendance_rows,
    normalize_status,
)

_TOKEN_PREFIX = "RMC-ATT"
_LINE_SPLIT = re.compile(r"[\n\r,;]+")


def _signing_key() -> bytes:
    secret = getattr(settings, "SECRET_KEY", "") or "dev-only"
    return secret.encode("utf-8")


def mint_student_attendance_token(*, school_id: int, student_id: int, student_code: str) -> str:
    """Short printable token for student ID card (no PII in token string)."""
    code = (student_code or "").strip()
    payload = f"{school_id}:{student_id}:{code}"
    sig = hmac.new(_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:12]
    return f"{_TOKEN_PREFIX}-{student_id}-{sig}"


def verify_student_attendance_token(
    token: str,
    *,
    school_id: int,
    student_id: int,
    student_code: str,
) -> bool:
    expected = mint_student_attendance_token(
        school_id=school_id,
        student_id=student_id,
        student_code=student_code,
    )
    return hmac.compare_digest((token or "").strip(), expected)


def parse_qr_token_lines(text: str) -> list[str]:
    """Split scanner paste / CSV token column into normalized token strings."""
    out: list[str] = []
    for part in _LINE_SPLIT.split(text or ""):
        piece = part.strip()
        if piece:
            out.append(piece)
    return out


def resolve_tokens_to_student_ids(
    tokens: list[str],
    *,
    school_id: int,
    classroom_id: int | None = None,
) -> tuple[list[int], list[dict]]:
    """
  Map tokens to student PKs under tenant scope.

  Accepts ``RMC-ATT-{id}-{sig}`` or raw ``student_code`` / admission number.
  """
    from apps.people.models import StudentProfile

    errors: list[dict] = []
    student_ids: list[int] = []
    seen: set[int] = set()

    # tenant-isolation-allow: qr-attendance-students-scoped-to-school-tenant
    qs = StudentProfile.objects.filter(school_id=school_id)
    if classroom_id:
        qs = qs.filter(classroom_id=classroom_id)
    by_code = {s.student_code: s for s in qs if s.student_code}
    by_adm = {s.admission_number: s for s in qs if s.admission_number}
    by_id = {s.id: s for s in qs}

    for raw in tokens:
        token = raw.strip()
        if not token:
            continue
        student = None
        if token.upper().startswith(_TOKEN_PREFIX):
            parts = token.split("-")
            if len(parts) >= 3 and parts[2].isdigit():
                sid = int(parts[2])
                student = by_id.get(sid)
                if student and not verify_student_attendance_token(
                    token,
                    school_id=school_id,
                    student_id=student.id,
                    student_code=student.student_code or "",
                ):
                    student = None
        if student is None:
            student = by_code.get(token) or by_adm.get(token)
        if student is None:
            errors.append({"token": token[:32], "reason": "not_found"})
            continue
        if student.id not in seen:
            seen.add(student.id)
            student_ids.append(student.id)
    return student_ids, errors


def apply_qr_sweep(
    *,
    classroom_id: int,
    date_value: date_type,
    tokens_text: str,
    school_id: int,
    default_status: str = "present",
) -> BulkAttendanceResult:
    """Mark resolved students present (or ``default_status``) via bulk apply."""
    tokens = parse_qr_token_lines(tokens_text)
    student_ids, errors = resolve_tokens_to_student_ids(
        tokens,
        school_id=school_id,
        classroom_id=classroom_id,
    )
    status = normalize_status(default_status)
    rows = [
        AttendanceRow(student_id=sid, status=status, student_external_id="")
        for sid in student_ids
    ]
    result = apply_attendance_rows(
        classroom_id=classroom_id,
        date_value=date_value,
        rows=rows,
        school_id=school_id,
    )
    result.errors.extend(errors)
    return result


__all__ = [
    "apply_qr_sweep",
    "mint_student_attendance_token",
    "parse_qr_token_lines",
    "resolve_tokens_to_student_ids",
    "verify_student_attendance_token",
]

"""Per-student canonical extraction + student transfer envelope (Wave A).

The design gap this closes (docs/TRANSFER_MERGE_SPLIT_ORCHESTRATOR_DESIGN.md §5):
``build_student_envelope`` validated caller-supplied dicts but nothing in-tree
ever READ the student's actual rows. This module is that reader — it extracts
one student's graph into canonical-domain rows (the same headers the
migration-cloud landers consume) so the sealed envelope is a complete,
apply-ready transfer artifact rather than an empty contract.

Finance is deliberately NOT in the default domain set: balances stay with the
source school unless the transfer case explicitly opts in (design §9).
"""

from __future__ import annotations

import logging
from typing import Any

from apps.interop.transfer_envelope import TransferEnvelope, build_envelope

logger = logging.getLogger(__name__)

TRANSFER_DEFAULT_DOMAINS = (
    "students",
    "guardians",
    "enrollment",
    "attendance",
    "grades",
)


def student_external_ref(profile) -> str:
    """Stable external id the target lander will key its upsert on.

    Mirrors the lander's lookup-candidate order (``admission_number`` is the
    field that exists on this deployment's StudentProfile); the final fallback
    guarantees the lander's required-field check never quarantines the student
    row for a blank id.
    """
    for attr in ("admission_number", "student_code", "exam_candidate_number"):
        value = (getattr(profile, attr, "") or "").strip()
        if value:
            return value
    return f"rmc-{profile.pk}"


def _drop_empty(row: dict[str, Any], keep: tuple[str, ...] = ()) -> dict[str, Any]:
    return {k: v for k, v in row.items() if v not in (None, "") or k in keep}


def _iso(value) -> str:
    return value.isoformat() if value else ""


def extract_student_domain_rows(
    profile,
    *,
    domains: tuple[str, ...] = TRANSFER_DEFAULT_DOMAINS,
) -> dict[str, list[dict[str, Any]]]:
    """Extract one student's rows per canonical domain. Read-only."""
    school = profile.school
    ref = student_external_ref(profile)
    wanted = set(domains)
    out: dict[str, list[dict[str, Any]]] = {}

    if "students" in wanted:
        classroom = getattr(profile, "classroom", None)
        out["students"] = [
            _drop_empty(
                {
                    "external_id": ref,
                    "first_name": profile.first_name,
                    "last_name": profile.last_name,
                    "date_of_birth": _iso(getattr(profile, "date_of_birth", None)),
                    "gender": getattr(profile, "gender", ""),
                    "email": getattr(getattr(profile, "user", None), "email", "") or "",
                    "phone": getattr(profile, "parent_phone", ""),
                    "grade_level": getattr(classroom, "name", "") or "",
                    "enrollment_status": getattr(profile, "status", ""),
                    "admission_number": getattr(profile, "admission_number", ""),
                },
                keep=("external_id", "first_name", "last_name"),
            )
        ]

    if "guardians" in wanted:
        from apps.people.models import StudentGuardian

        rows = []
        guardians = StudentGuardian.objects.filter(
            student=profile, student__school=school
        ).select_related("guardian_user")
        for g in guardians:
            guardian_user = getattr(g, "guardian_user", None)
            rows.append(
                _drop_empty(
                    {
                        "guardian_external_id": f"g-{g.pk}",
                        "first_name": getattr(guardian_user, "first_name", "") or "",
                        "last_name": getattr(guardian_user, "last_name", "") or "",
                        "email": g.email or getattr(guardian_user, "email", "") or "",
                        "phone": g.phone,
                        "relationship": g.relationship,
                        "is_primary": "true" if getattr(g, "is_primary", False) else "",
                        "student_external_id": ref,
                    },
                    keep=("guardian_external_id", "student_external_id"),
                )
            )
        if rows:
            out["guardians"] = rows

    if "enrollment" in wanted:
        classroom = getattr(profile, "classroom", None)
        out["enrollment"] = [
            _drop_empty(
                {
                    "student_external_id": ref,
                    "grade_level": getattr(classroom, "name", "") or "",
                    "enrollment_status": getattr(profile, "status", ""),
                    "enrollment_date": _iso(getattr(profile, "joined_date", None)),
                    "section": getattr(profile, "section", "")
                    or (getattr(classroom, "name", "") or ""),
                },
                keep=("student_external_id",),
            )
        ]

    if "attendance" in wanted:
        from apps.academics.models import Attendance

        rows = []
        records = Attendance.objects.filter(school=school, student=profile).order_by(
            "date"
        )
        for a in records.iterator():
            rows.append(
                _drop_empty(
                    {
                        "student_external_id": ref,
                        "date": _iso(a.date),
                        "status": a.status,
                        "notes": getattr(a, "remarks", ""),
                    },
                    keep=("student_external_id", "date"),
                )
            )
        if rows:
            out["attendance"] = rows

    if "grades" in wanted:
        from apps.evals.models import Evaluation

        rows = []
        evaluations = Evaluation.objects.filter(student=profile).select_related(  # tenant-isolation-allow: scoped-via-student-profile-school-fk-transfer-export
            "subject_assignment__subject", "term"
        )
        for ev in evaluations.iterator():
            subject = getattr(
                getattr(ev, "subject_assignment", None), "subject", None
            )
            score = getattr(ev, "final_score", None)
            rows.append(
                _drop_empty(
                    {
                        "student_external_id": ref,
                        "subject_code": getattr(subject, "code", "")
                        or getattr(subject, "name", "")
                        or "",
                        "term": getattr(getattr(ev, "term", None), "name", "") or "",
                        "score": "" if score is None else str(score),
                    },
                    keep=("student_external_id", "subject_code"),
                )
            )
        if rows:
            out["grades"] = rows

    return out


def build_student_transfer_envelope(
    profile,
    *,
    target_school,
    actor_id: str = "",
    domains: tuple[str, ...] = TRANSFER_DEFAULT_DOMAINS,
) -> TransferEnvelope:
    """Extract + seal a checksummed student envelope, source → target."""
    source_school = profile.school
    rows = extract_student_domain_rows(profile, domains=domains)
    envelope = build_envelope(
        envelope_kind="student",
        source_tenant_id=str(source_school.pk),
        target_tenant_id=str(target_school.pk),
        canonical_data={},
        domain_rows=rows,
        actor_id=actor_id,
    )
    logger.info(
        "student_transfer_export.sealed student=%s domains=%s checksum=%s",
        profile.pk,
        sorted(rows.keys()),
        envelope.checksum[:12],
        extra={"scope": "student_transfer_export"},
    )
    return envelope


__all__ = [
    "TRANSFER_DEFAULT_DOMAINS",
    "build_student_transfer_envelope",
    "extract_student_domain_rows",
    "student_external_ref",
]

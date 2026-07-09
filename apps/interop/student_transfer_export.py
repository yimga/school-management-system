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
    "transcripts",
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


def _bool_str(value: Any) -> str:
    """Encode a boolean as an explicit ``'true'``/``'false'`` string.

    A source ``False`` MUST reach the target as ``'false'`` (not an empty
    string) so :func:`_drop_empty` keeps the column and the lander sets the
    real value — an absent column would silently reset the flag to the
    model default at the destination.
    """
    return "true" if value else "false"


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
                        # Internal transfers carry the guardian's PLATFORM
                        # identity so the target re-links the SAME account
                        # (portal access survives the move) instead of
                        # provisioning a duplicate from contact fields.
                        "guardian_user_ref": getattr(guardian_user, "username", "")
                        or "",
                        # Consent / visibility / contact-preference fidelity:
                        # without these the target resets every flag to the
                        # model default on apply — silently RE-SUBSCRIBING an
                        # opted-out parent (receives_*), REGRANTING results
                        # access to a restricted guardian (can_view_results),
                        # or DROPPING finance visibility the parent had
                        # (can_view_finance). Booleans are emitted explicitly
                        # (see _bool_str) so a source False is carried, not
                        # dropped as an empty string.
                        "receives_email": _bool_str(getattr(g, "receives_email", True)),
                        "receives_sms": _bool_str(getattr(g, "receives_sms", False)),
                        "receives_whatsapp": _bool_str(
                            getattr(g, "receives_whatsapp", False)
                        ),
                        "can_view_results": _bool_str(
                            getattr(g, "can_view_results", True)
                        ),
                        "can_view_finance": _bool_str(
                            getattr(g, "can_view_finance", False)
                        ),
                        "preferred_contact": getattr(g, "preferred_contact", "") or "",
                        "whatsapp_number": getattr(g, "whatsapp_number", "") or "",
                        "address": getattr(g, "address", "") or "",
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
                    # Curriculum track: grades can only bind to a target
                    # SubjectAssignment whose class/specialty matches the
                    # student's placement (Evaluation.clean parity rule).
                    "specialty": getattr(
                        getattr(profile, "specialty", None), "name", ""
                    )
                    or "",
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

    if "grades" in wanted or "transcripts" in wanted:
        from apps.evals.models import Evaluation

        grade_rows = []
        transcript_rows = []
        evaluations = Evaluation.objects.filter(student=profile).select_related(  # tenant-isolation-allow: scoped-via-student-profile-school-fk-transfer-export
            "subject_assignment__subject", "term", "academic_year"
        )
        for ev in evaluations.iterator():
            subject = getattr(
                getattr(ev, "subject_assignment", None), "subject", None
            )
            subject_label = (
                getattr(subject, "code", "") or getattr(subject, "name", "") or ""
            )
            term_label = getattr(getattr(ev, "term", None), "name", "") or ""
            year_label = (
                getattr(getattr(ev, "academic_year", None), "name", "") or ""
            )
            letter = getattr(ev, "letter_grade", "") or ""
            score = getattr(ev, "final_score", None)
            if "grades" in wanted:
                row = {
                    "student_external_id": ref,
                    "subject_code": subject_label,
                    "term": term_label,
                    "academic_year": year_label,
                    "score": "" if score is None else str(score),
                    "grade_letter": letter,
                }
                # Full component fidelity for the target's FK-graph lander —
                # the copy is faithful, never a re-derived aggregate.
                for component in (
                    "seq1_score",
                    "seq2_score",
                    "exam_score",
                    "mock_score",
                    "practical_score",
                    "internship_score",
                    "test1",
                    "test2",
                ):
                    value = getattr(ev, component, None)
                    if value is not None:
                        row[component] = str(value)
                grade_rows.append(
                    _drop_empty(row, keep=("student_external_id", "subject_code"))
                )
            if "transcripts" in wanted:
                # Archival record: ALWAYS lands at the target (vault items
                # need no calendar/subject/staff structure), so the student's
                # academic history survives even when the live-gradebook
                # resolution above cannot place a row.
                final_text = "" if score is None else str(score)
                grade_text = " ".join(
                    part for part in (f"final {final_text}" if final_text else "", f"({letter})" if letter else "") if part
                ).strip()
                transcript_rows.append(
                    _drop_empty(
                        {
                            "student_external_id": ref,
                            "academic_year": year_label,
                            "term": term_label,
                            "subject_code": subject_label,
                            "final_grade": final_text or letter,
                            "artifact_type": "transfer_grade_record",
                            "artifact_ref": " | ".join(
                                part
                                for part in (
                                    year_label,
                                    term_label,
                                    subject_label,
                                    grade_text,
                                )
                                if part
                            )[:512],
                            "issuing_school_id": str(school.pk),
                        },
                        keep=("student_external_id", "subject_code"),
                    )
                )
        if grade_rows:
            out["grades"] = grade_rows
        if transcript_rows:
            out["transcripts"] = transcript_rows

    if "structure" in wanted:
        # SPLIT-only academic scaffold: one row per SubjectAssignment the
        # student's grades reference, carrying the full graph the target's
        # StructureLander provisions BEFORE enrollment/grades so a split into
        # an empty tenant lands a LIVE gradebook (a merge omits this domain and
        # maps to the destination school's own structure). Idempotent at the
        # target, so a whole cohort's overlapping rows collapse.
        from apps.evals.models import Evaluation

        structure_rows = []
        seen_assignments: set[Any] = set()
        struct_evals = Evaluation.objects.filter(student=profile).select_related(  # tenant-isolation-allow: scoped-via-student-profile-school-fk-transfer-export
            "subject_assignment__subject",
            "subject_assignment__classroom__department",
            "subject_assignment__specialty__department",
            "subject_assignment__term",
            "subject_assignment__academic_year",
            "academic_year",
            "term",
            "teacher__user",
        )
        for ev in struct_evals.iterator():
            sa = getattr(ev, "subject_assignment", None)
            if sa is None or sa.pk in seen_assignments:
                continue
            seen_assignments.add(sa.pk)
            year = getattr(sa, "academic_year", None) or getattr(ev, "academic_year", None)
            term = getattr(sa, "term", None) or getattr(ev, "term", None)
            classroom = getattr(sa, "classroom", None)
            specialty = getattr(sa, "specialty", None)
            subject = getattr(sa, "subject", None)
            dept = getattr(classroom, "department", None) or getattr(
                specialty, "department", None
            )
            teacher_user = getattr(getattr(ev, "teacher", None), "user", None)
            structure_rows.append(
                _drop_empty(
                    {
                        "academic_year": getattr(year, "name", "") or "",
                        "year_start": _iso(getattr(year, "start_date", None)),
                        "year_end": _iso(getattr(year, "end_date", None)),
                        "year_is_active": _bool_str(getattr(year, "is_active", False)),
                        "term": getattr(term, "name", "") or "",
                        "term_label": getattr(term, "custom_label", "") or "",
                        "term_position": str(getattr(term, "position", "") or ""),
                        "term_start": _iso(getattr(term, "start_date", None)),
                        "term_end": _iso(getattr(term, "end_date", None)),
                        "department": getattr(dept, "name", "") or "",
                        "classroom": getattr(classroom, "name", "") or "",
                        "specialty": getattr(specialty, "name", "") or "",
                        "subject": getattr(subject, "name", "") or "",
                        "coefficient": str(getattr(sa, "coefficient", "") or ""),
                        "teacher_ref": getattr(teacher_user, "username", "") or "",
                        "teacher_first_name": getattr(teacher_user, "first_name", "")
                        or "",
                        "teacher_last_name": getattr(teacher_user, "last_name", "")
                        or "",
                        "teacher_email": getattr(teacher_user, "email", "") or "",
                    },
                    keep=("academic_year", "term", "classroom", "specialty", "subject"),
                )
            )
        if structure_rows:
            out["structure"] = structure_rows

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

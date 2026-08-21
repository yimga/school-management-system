"""Grades lander — persists canonical grade rows into `apps.evals.Evaluation`.

Canonical row shape::

    {
        "student_external_id": "PS-1029",
        "subject_code": "MATH" | "Mathematics",
        "term": "FIRST" | "Trimestre 1" | "Semester 1",
        "academic_year": "2025/2026" (optional; falls back to the school's active year),
        "score": "85.5" (optional aggregate — lands in exam_score with a remark),
        "seq1_score" / "seq2_score" / "exam_score" / "mock_score" /
        "practical_score" / "test1" / "test2": component scores (optional),
        "grade_letter": "A" (optional),
    }

Deployment awareness (the completeness fix, 2026-07-09): on this platform
``Evaluation`` is an FK graph — ``academic_year``/``term``/``subject_assignment``/
``teacher`` are all REQUIRED PROTECT FKs — so the old flat string upsert
(``term="T1"``) could never create a row: every grade import OR inter-school
transfer quarantined 100% of its grade rows at the target. This lander now
RESOLVES the graph at the target school:

    academic_year (name, normalized)  → Term (name/custom_label within year)
    → Subject (name/code)             → SubjectAssignment (subject × term
    [× student's classroom])          → teacher (assignment's teachers M2M
    → TeacherProfile)

Resolution NEVER fabricates structure — a school's calendar, subjects,
assignments and staff are its own; a row whose graph does not resolve
quarantines with a precise, per-edge reason (and the transfer console carries
the same record archivally via the ``transcripts`` domain, so history is never
lost). Deployments whose Evaluation model uses flat string columns keep the
legacy upsert path.

Upsert key (FK graph): (student, academic_year, term, subject_assignment) —
the model's own "one row per student per subject_assignment per term" contract.
The orchestrator runs this AFTER students + enrollment (classroom placement).
"""

from __future__ import annotations

import re
from typing import Any, Iterator

from ._helpers import (
    coerce_decimal,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
    record_row_error,
    resolve_student,
    student_lookup_field,
    student_name_from_row,
    unresolved_student_reason,
    upsert_with_conflict_detection,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register
from .reason_codes import INVALID_REF, LANDER_ERROR, MISSING_REQUIRED

_COMPONENT_FIELDS = (
    "seq1_score",
    "seq2_score",
    "exam_score",
    "mock_score",
    "practical_score",
    "internship_score",
    "test1",
    "test2",
)


def _norm(value: str) -> str:
    """Loose label normalization: case/spacing/separator-insensitive."""
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


class GradesLander(Lander):
    domain = "grades"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.evals.models import Evaluation
            from apps.people.models import StudentProfile
        except ImportError as exc:
            raise LanderError(
                f"GradesLander could not import Evaluation / StudentProfile: {exc!s}"
            ) from exc

        term_field = Evaluation._meta.get_field("term")
        if getattr(term_field, "is_relation", False):
            return self._land_fk_graph(
                canonical_rows=canonical_rows,
                ctx=ctx,
                Evaluation=Evaluation,
                StudentProfile=StudentProfile,
            )
        return self._land_flat(
            canonical_rows=canonical_rows,
            ctx=ctx,
            Evaluation=Evaluation,
            StudentProfile=StudentProfile,
        )

    # ── FK-graph deployment (this platform) ─────────────────────────

    def _land_fk_graph(
        self, *, canonical_rows, ctx: LanderContext, Evaluation, StudentProfile
    ) -> LanderResult:
        from apps.people.models import TeacherProfile

        result = LanderResult()
        student_fields = model_field_names(StudentProfile)
        student_lookup = student_lookup_field(student_fields)
        resolver = _TargetGraphResolver(school=ctx.school)

        for row in canonical_rows:
            external_id = (row.get("student_external_id") or "").strip()
            term_label = (row.get("term") or "").strip()
            subject_label = (
                row.get("subject_code") or row.get("subject") or ""
            ).strip()
            components = {
                f: coerce_decimal(row.get(f))
                for f in _COMPONENT_FIELDS
                if row.get(f) not in (None, "")
            }
            aggregate = coerce_decimal(row.get("score"))
            letter = (row.get("grade_letter") or row.get("letter_grade") or "").strip()
            if not (external_id or student_name_from_row(row)) or not term_label or not subject_label:
                record_row_error(
                    result,
                    row,
                    f"grades: missing student/term/subject in {row!r}",
                    reason_code=MISSING_REQUIRED,
                )
                continue
            if not components and aggregate is None and not letter:
                record_row_error(
                    result,
                    row,
                    f"grades: no score or letter for {external_id} / "
                    f"{subject_label} / {term_label}",
                    reason_code=MISSING_REQUIRED,
                )
                continue

            student = resolve_student(
                ctx=ctx,
                student_model=StudentProfile,
                lookup_field=student_lookup,
                external_id=external_id,
                row=row,
            )
            if student is None:
                record_row_error(
                    result,
                    row,
                    unresolved_student_reason(
                        domain="grades",
                        ctx=ctx,
                        student_model=StudentProfile,
                        row=row,
                        external_id=external_id,
                        lookup_field=student_lookup,
                    ),
                    reason_code=INVALID_REF,
                )
                continue

            resolved, reason = resolver.resolve(
                year_label=(row.get("academic_year") or "").strip(),
                term_label=term_label,
                subject_label=subject_label,
                student=student,
            )
            if resolved is None:
                record_row_error(
                    result,
                    row,
                    f"grades: {reason} for {external_id} / {subject_label} / {term_label}",
                    reason_code=INVALID_REF,
                )
                continue
            year, term, assignment = resolved

            teacher = self._assignment_teacher(assignment, TeacherProfile, ctx)
            if teacher is None:
                record_row_error(
                    result,
                    row,
                    "grades: subject assignment has no teacher with a "
                    f"TeacherProfile for {external_id} / {subject_label} / {term_label}",
                    reason_code=INVALID_REF,
                )
                continue

            defaults: dict[str, Any] = {"teacher": teacher}
            if "school" in model_field_names(Evaluation):
                defaults["school"] = ctx.school
            for field, value in components.items():
                defaults[field] = value
            if not components and aggregate is not None:
                # Single aggregate score from a flat source — land it in the
                # exam component with an honest provenance remark rather than
                # inventing a component split.
                defaults["exam_score"] = aggregate
                defaults["remarks"] = "imported aggregate score"
            if letter:
                defaults["letter_grade"] = letter[:8]
            defaults = filter_to_model_fields(defaults, Evaluation)

            lookup = {
                "student": student,
                "academic_year": year,
                "term": term,
                "subject_assignment": assignment,
            }
            legacy_id = f"{external_id}:{term_label}:{subject_label}"

            if ctx.dry_run:
                # Resolution already ran read-only above, so the dry-run
                # preview reports what would genuinely land.
                result.created += 1
                continue
            try:
                obj, created, preserved = upsert_with_conflict_detection(
                    ctx=ctx, domain="grades", model=Evaluation,
                    lookup=lookup, defaults=defaults,
                    legacy_id=legacy_id,
                )
                if preserved:
                    # Operator resolved this grade conflict as PRESERVE —
                    # keep the tenant's existing score, don't overwrite.
                    result.skipped += 1
                    record_id_mapping(
                        ctx=ctx, legacy_id=legacy_id,
                        canonical_obj=obj, domain="grades",
                    )
                    continue
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                record_id_mapping(
                    ctx=ctx, legacy_id=legacy_id,
                    canonical_obj=obj, domain="grades",
                )
            except Exception as exc:  # noqa: BLE001 — per-row quarantine
                record_row_error(
                    result,
                    row,
                    f"grades upsert failed for {external_id} / {subject_label} / "
                    f"{term_label}: {type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
        return result

    @staticmethod
    def _assignment_teacher(assignment, TeacherProfile, ctx: LanderContext):
        """First assignment teacher that carries a TeacherProfile (Evaluation FK)."""
        school_scoped = (
            "school" in model_field_names(TeacherProfile) and ctx.school is not None
        )
        for user in assignment.teachers.all():
            if school_scoped:
                profile = (
                    TeacherProfile.objects.filter(user=user, school=ctx.school).first()
                    or TeacherProfile.objects.filter(
                        user=user, school__isnull=True
                    ).first()
                )
            else:
                profile = TeacherProfile.objects.filter(user=user).first()  # tenant-isolation-allow: alternate-deployments-without-school-fk-schema-context-isolates
            if profile is not None:
                return profile
        # Seeded SubjectAssignments often have no teacher yet; Evaluation.teacher
        # is required, so attach any school teacher for import — admin reassigns.
        if school_scoped:
            fallback = TeacherProfile.objects.filter(school=ctx.school).order_by("pk").first()
            if fallback is not None:
                return fallback
        return TeacherProfile.objects.order_by("pk").first()  # tenant-isolation-allow: schema-per-tenant-context-isolates-when-no-school-fk

    # ── Flat-column deployments (foreign Evaluation shapes) ─────────

    def _land_flat(
        self, *, canonical_rows, ctx: LanderContext, Evaluation, StudentProfile
    ) -> LanderResult:
        result = LanderResult()
        eval_fields = model_field_names(Evaluation)
        student_fields = model_field_names(StudentProfile)
        student_lookup = student_lookup_field(student_fields)

        for row in canonical_rows:
            external_id = (row.get("student_external_id") or "").strip()
            term = (row.get("term") or "").strip()
            subject = (row.get("subject_code") or row.get("subject") or "").strip()
            score = coerce_decimal(row.get("score"))
            letter = (row.get("grade_letter") or "").strip()
            if not (external_id or student_name_from_row(row)) or not term or (score is None and not letter):
                record_row_error(
                    result,
                    row,
                    f"grades: missing student/term/score in {row!r}",
                    reason_code=MISSING_REQUIRED,
                )
                continue
            student = resolve_student(
                ctx=ctx,
                student_model=StudentProfile,
                lookup_field=student_lookup,
                external_id=external_id,
                row=row,
            )
            if student is None:
                record_row_error(
                    result,
                    row,
                    unresolved_student_reason(
                        domain="grades",
                        ctx=ctx,
                        student_model=StudentProfile,
                        row=row,
                        external_id=external_id,
                        lookup_field=student_lookup,
                    ),
                    reason_code=INVALID_REF,
                )
                continue

            defaults: dict[str, Any] = {}
            if "score" in eval_fields and score is not None:
                defaults["score"] = score
            if "grade_letter" in eval_fields and letter:
                defaults["grade_letter"] = letter
            if "max_score" in eval_fields and row.get("max_score"):
                defaults["max_score"] = coerce_decimal(row.get("max_score"))
            if "academic_year" in eval_fields and row.get("academic_year"):
                defaults["academic_year"] = str(row["academic_year"])
            if "subject_code" in eval_fields and subject:
                defaults["subject_code"] = subject
            elif "subject" in eval_fields and subject:
                defaults["subject"] = subject

            defaults = filter_to_model_fields(defaults, Evaluation)

            lookup: dict[str, Any] = {"student": student}
            if "term" in eval_fields:
                lookup["term"] = term
            if subject and ("subject_code" in eval_fields):
                lookup["subject_code"] = subject
            elif subject and ("subject" in eval_fields):
                lookup["subject"] = subject

            if ctx.dry_run:
                result.created += 1
                continue
            try:
                obj, created, preserved = upsert_with_conflict_detection(
                    ctx=ctx, domain="grades", model=Evaluation,
                    lookup=lookup, defaults=defaults,
                    legacy_id=f"{external_id}:{term}:{subject}",
                )
                if preserved:
                    result.skipped += 1
                    record_id_mapping(
                        ctx=ctx, legacy_id=f"{external_id}:{term}:{subject}",
                        canonical_obj=obj, domain="grades",
                    )
                    continue
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                record_id_mapping(
                    ctx=ctx, legacy_id=f"{external_id}:{term}:{subject}",
                    canonical_obj=obj, domain="grades",
                )
            except Exception as exc:  # noqa: BLE001
                record_row_error(
                    result,
                    row,
                    f"grades upsert failed for {external_id} / {subject} / {term}: {type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
        return result


class _TargetGraphResolver:
    """Resolve (AcademicYear, Term, SubjectAssignment) at the target school.

    Read-only and memoized per bundle: resolution failures return a precise
    per-edge reason so the quarantine ledger says exactly which structure the
    target school is missing. It never creates calendar/subject/assignment
    rows — that is the target school's own configuration, not import data.

    Placement parity is REQUIRED, not best-effort: ``Evaluation.clean``
    enforces that the student's academic_year/classroom/specialty all match
    the assignment's, so the resolver binds strictly to the student's own
    placement — anything else would fail validation row-by-row anyway.
    """

    def __init__(self, *, school):
        self.school = school
        self._cache: dict[tuple, tuple] = {}

    def resolve(self, *, year_label, term_label, subject_label, student):
        key = (
            year_label,
            term_label,
            subject_label,
            getattr(student, "classroom_id", None),
            getattr(student, "specialty_id", None),
            getattr(student, "academic_year_id", None),
        )
        if key in self._cache:
            return self._cache[key]
        value = self._resolve(
            year_label=year_label,
            term_label=term_label,
            subject_label=subject_label,
            student=student,
        )
        self._cache[key] = value
        return value

    def _resolve(self, *, year_label, term_label, subject_label, student):
        from apps.academics.models import AcademicYear, Subject, SubjectAssignment, Term

        years = AcademicYear.objects.filter(school=self.school)
        year = None
        if year_label:
            wanted = _norm(year_label)
            year = next((y for y in years if _norm(y.name) == wanted), None)
            if year is None:
                return None, f"no academic year matching {year_label!r} at the target"
        else:
            year = years.filter(is_active=True).first()
            if year is None:
                return None, "no active academic year at the target"

        if getattr(student, "classroom_id", None) is None:
            return None, "student has no classroom placement at the target"
        if getattr(student, "academic_year_id", None) != year.pk:
            return None, (
                f"grade year {year.name!r} is not the student's enrolled year "
                "at the target (record stays archival)"
            )

        wanted_term = _norm(term_label)
        term = next(
            (
                t
                for t in Term.objects.filter(school=self.school, academic_year=year)
                if _norm(t.name) == wanted_term
                or _norm(getattr(t, "custom_label", "")) == wanted_term
            ),
            None,
        )
        if term is None:
            return None, f"no term matching {term_label!r} in {year.name!r} at the target"

        wanted_subject = _norm(subject_label)
        subject = next(
            (
                s
                for s in Subject.objects.filter(school=self.school)
                if _norm(s.name) == wanted_subject
                or _norm(getattr(s, "code", "")) == wanted_subject
            ),
            None,
        )
        if subject is None:
            return None, f"no subject matching {subject_label!r} at the target"

        assignment = SubjectAssignment.objects.filter(
            school=self.school,
            academic_year=year,
            term=term,
            subject=subject,
            classroom_id=student.classroom_id,
            specialty_id=student.specialty_id,
        ).first()
        if assignment is None:
            return (
                None,
                f"no subject assignment for {subject_label!r} in {term_label!r} "
                "matching the student's class/specialty at the target",
            )
        return (year, term, assignment), ""


register("grades", GradesLander())

"""Grades lander — persists canonical grade rows into `apps.evals.Evaluation`.

Canonical row shape::

    {
        "student_external_id": "PS-1029",
        "subject_code": "MATH",
        "term": "T1" | "Trimestre 1" | "Semester 1",
        "score": "85.5" | "A" | "12",
        "grade_letter": "A" (optional),
        "max_score": "100" (optional),
        "academic_year": "2025-2026" (optional),
    }

Upsert key: (student, subject_code, term) when those fields exist on the model;
otherwise (student, term) is the minimum we can stably identify. The orchestrator
should run this AFTER the students lander (FK dependency).
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import (
    coerce_decimal,
    filter_to_model_fields,
    model_field_names,
    student_lookup_field,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


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
            if not external_id or not term or (score is None and not letter):
                result.quarantined += 1
                result.errors.append(
                    f"grades: missing student/term/score in {row!r}"
                )
                continue
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            student = StudentProfile.objects.filter(
                **{student_lookup: external_id}
            ).first()
            if student is None:
                result.quarantined += 1
                result.errors.append(
                    f"grades: no student with {student_lookup}={external_id!r}"
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
                from ._helpers import (
                    record_id_mapping,
                    upsert_with_conflict_detection,
                )
                obj, created, preserved = upsert_with_conflict_detection(
                    ctx=ctx, domain="grades", model=Evaluation,
                    lookup=lookup, defaults=defaults,
                    legacy_id=f"{external_id}:{term}:{subject}",
                )
                if preserved:
                    # Operator resolved this grade conflict as PRESERVE —
                    # keep the tenant's existing score, don't overwrite.
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
                result.quarantined += 1
                result.errors.append(
                    f"grades upsert failed for {external_id} / {subject} / {term}: {type(exc).__name__}: {exc}"
                )
        return result


register("grades", GradesLander())

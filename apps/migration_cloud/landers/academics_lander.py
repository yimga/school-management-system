"""Academics lander — persists canonical course/subject rows into
``apps.academics.Subject``.

Gap this closes (2026-07-11): the OneRoster/PowerSchool/Alma accelerators
pre-classify ``courses.csv`` to the ``academics`` domain, but NO lander was
registered for it — so the orchestrator fell through to the ``custom_fields``
catch-all and every course landed as an opaque ``DynamicFieldValue`` blob,
never a real ``Subject``. Downstream, ``grades_lander`` resolves a grade's
``Subject`` by name at the target (``Subject.objects.filter(school=…)``); with
zero Subjects, every grade quarantined. A plain SIS import therefore could not
land grades. This lander creates the Subject rows the grade path binds to.

Runs in wave 1 (independent roots, alongside students/staff/sections) so
Subjects exist before grades land in a later wave.

Canonical row shape (source field names)::

    {
        "subject_code": "MATH101",
        "subject_name": "Mathematics",
        "credits": "3.0",
        "department": "Science"
    }
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import (
    coerce_decimal,
    get_or_create_named,
    model_field_names,
    record_id_mapping,
    record_row_error,
    row_marks_deletion,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


class AcademicsLander(Lander):
    domain = "academics"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.academics.models import Subject
        except ImportError as exc:
            raise LanderError(f"AcademicsLander could not import Subject: {exc!s}") from exc

        result = LanderResult()
        subject_fields = model_field_names(Subject)

        for row in canonical_rows:
            # D-3: a source row marked tobedeleted must NOT land as an active
            # Subject. Subject has no is_active/status column and grades FK into
            # it, so we neither import it as active nor hard-delete an existing one
            # (that could orphan grades) — it is held for review with its source row.
            if row_marks_deletion(row):
                record_row_error(
                    result, row,
                    "academics: source marked this course deleted — held for review, "
                    "not imported as active; any existing subject is left intact for "
                    "referential safety (remove manually if intended).",
                )
                continue
            name = (row.get("subject_name") or row.get("name") or row.get("title") or "").strip()
            code = (row.get("subject_code") or row.get("code") or "").strip()
            # ``Subject`` is keyed by name (unique per school); fall back to the
            # code when a source only carries a code.
            name = name or code
            if not name:
                result.quarantined += 1
                result.errors.append(f"academics: missing subject_name/code in {row!r}")
                continue

            if ctx.dry_run:
                exists = self._exists(Subject, ctx.school, name)
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue

            try:
                credits = coerce_decimal(row.get("credits"))
                obj, created = get_or_create_named(
                    model=Subject,
                    school=ctx.school,
                    name=name[:120],  # magic-number-allow: Subject.name CharField max_length
                    create_kwargs=lambda c=credits: (
                        {"credits": c} if c is not None and "credits" in subject_fields else {}
                    ),
                    result=result,
                )
                if created:
                    result.created += 1
                else:
                    result.skipped += 1
                record_id_mapping(ctx=ctx, legacy_id=code or name, canonical_obj=obj, domain="academics")
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"academics upsert failed for {name}: {type(exc).__name__}: {exc}"
                )
        return result

    @staticmethod
    def _exists(Subject, school, name) -> bool:
        qs = Subject.objects.all()  # tenant-isolation-allow: scoped-below-by-school-when-present / schema-context-isolates
        if "school" in model_field_names(Subject) and school is not None:
            qs = qs.filter(school=school)
        return qs.filter(name=name).exists()


register("academics", AcademicsLander())

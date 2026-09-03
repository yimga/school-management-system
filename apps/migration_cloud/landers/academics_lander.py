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
    record_row_note,
    row_is_pdf_noise_hold,
    row_is_unstructured_text_fragment,
    row_marks_deletion,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register
from .reason_codes import LANDER_ERROR, MISSING_REQUIRED
from .reason_codes import SOURCE_DELETION


def _resolve_category(raw, Subject):
    """A recognized category label -> a ``Subject.Category`` value; else ``None``.

    Matching is against the model's OWN choices -- values ("PROFESSIONAL") and
    display labels ("Professional") both count, case/space/underscore-insensitive --
    so a new choice added to the model is understood here with no edit. An
    unrecognized label maps to nothing rather than to a guess: OTHER is a real
    curriculum statement, not a bucket for text we failed to read.
    """
    text = str(raw or "").strip()
    if not text:
        return None
    compact = text.replace(" ", "").replace("-", "").replace("_", "").upper()
    for value, label in Subject.Category.choices:
        if compact in (value.replace("_", ""), str(label).replace(" ", "").upper()):
            return value
    return None


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
                    reason_code=SOURCE_DELETION,
                )
                continue
            name = (row.get("subject_name") or row.get("name") or row.get("title") or "").strip()
            code = (row.get("subject_code") or row.get("code") or "").strip()
            # ``Subject`` is keyed by name (unique per school); fall back to the
            # code when a source only carries a code.
            name = name or code
            if not name:
                artifact_path = str(getattr(ctx, "artifact_path", "") or "")
                if row_is_unstructured_text_fragment(row, artifact=artifact_path) or row_is_pdf_noise_hold(
                    "academics", row, artifact_path
                ):
                    result.skipped += 1
                    continue
                record_row_error(
                    result,
                    row,
                    f"academics: missing subject_name/code in {row!r}",
                    reason_code=MISSING_REQUIRED, field="subject_name",
                )
                continue

            if ctx.dry_run:
                exists = self._exists(Subject, ctx.school, name)
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue

            try:
                credits = coerce_decimal(row.get("credits"))
                # The CATEGORY column (a real Subject field with choices) used to be
                # read by NOTHING: 108 subjects landed and every "Professional" /
                # "General" cell fell to residual capture, invisible in the catalog.
                category = (
                    _resolve_category(row.get("category"), Subject)
                    if "category" in subject_fields
                    else None
                )
                def _create_kwargs(c=credits, cat=category):
                    kwargs = {}
                    if c is not None and "credits" in subject_fields:
                        kwargs["credits"] = c
                    if cat is not None:
                        kwargs["category"] = cat
                    return kwargs
                obj, created = get_or_create_named(
                    model=Subject,
                    school=ctx.school,
                    name=name[:120],  # magic-number-allow: Subject.name CharField max_length
                    create_kwargs=_create_kwargs,
                    result=result,
                )
                if created:
                    result.created += 1
                else:
                    result.skipped += 1
                    # Backfill: only a row still on the field DEFAULT may take the
                    # import's category -- a category somebody set by hand is that
                    # school's decision and a re-upload must not overturn it.
                    if category is not None and getattr(obj, "category", None) != category:
                        if obj.category == Subject.Category.OTHER:
                            obj.category = category
                            obj.save(update_fields=["category"])
                            result.updated += 1
                        else:
                            record_row_note(
                                result,
                                f"academics: kept category {obj.category!r} for"
                                f" {name!r} (import says {category!r}; the row was"
                                " set deliberately and an import does not outrank it)",
                            )
                if row.get("category") and category is None:
                    record_row_note(
                        result,
                        f"academics: category {str(row.get('category'))[:40]!r} on"
                        f" {name!r} matches no Subject.Category choice; left at"
                        " the model default (value preserved in custom fields)",
                    )
                record_id_mapping(ctx=ctx, legacy_id=code or name, canonical_obj=obj, domain="academics")
            except Exception as exc:  # noqa: BLE001
                record_row_error(
                    result,
                    row,
                    f"academics upsert failed for {name}: {type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
        return result

    @staticmethod
    def _exists(Subject, school, name) -> bool:
        qs = Subject.objects.all()  # tenant-isolation-allow: scoped-below-by-school-when-present / schema-context-isolates
        if "school" in model_field_names(Subject) and school is not None:
            qs = qs.filter(school=school)
        return qs.filter(name=name).exists()


register("academics", AcademicsLander())

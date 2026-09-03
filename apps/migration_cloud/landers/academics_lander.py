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

import re
from typing import Any, Iterator

from ._helpers import (
    coerce_decimal,
    detect_conflict,
    explicit_conflict_resolution_for,
    get_or_create_named,
    model_field_names,
    persist_dfv_extras,
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

_CATEGORY_ALIASES: dict[str, str] = {
    "general": "GENERAL",
    "generale": "GENERAL",
    "professional": "PROFESSIONAL",
    "professionnel": "PROFESSIONAL",
    "professionnelle": "PROFESSIONAL",
    "related": "RELATED",
    "other": "OTHER",
}


def _resolve_subject_category(raw: object) -> str | None:
    token = str(raw or "").strip().lower()
    if not token:
        return None
    compact = re.sub(r"[^a-z]+", "", token)
    return _CATEGORY_ALIASES.get(token) or _CATEGORY_ALIASES.get(compact)



def _resolve_row_coefficient(row: dict[str, Any], *, category: str | None) -> Any:
    """Francophone ``coef`` belongs on SpecialtySubject, not Subject.credits."""
    explicit = row.get("coefficient") or row.get("coef")
    if explicit not in (None, ""):
        return coerce_decimal(explicit)
    credits = row.get("credits")
    if credits not in (None, "") and category:
        return coerce_decimal(credits)
    return coerce_decimal(credits) if credits not in (None, "") else None


def _link_subject_curriculum(
    *,
    ctx: LanderContext,
    result: LanderResult,
    subject,
    row: dict[str, Any],
    category: str | None,
    coefficient,
) -> None:
    """Upsert ``SpecialtySubject`` rows (track ↔ matière + coef)."""
    try:
        from apps.academics.models import Specialty, SpecialtySubject
    except ImportError:
        return

    from apps.migration_cloud.curriculum_link_heuristics import (
        is_general_subject_name,
        specialty_codes_for_subject,
    )
    from apps.migration_cloud.ingestion_lexicon import resolve_school_ingestion_lexicon

    lexicon = resolve_school_ingestion_lexicon(ctx.school)
    coef = coefficient
    if coef is None and category:
        if category == "GENERAL":
            coef = lexicon.default_general_coef
        elif category == "PROFESSIONAL":
            coef = lexicon.default_professional_coef

    specialty_name = (
        row.get("specialty")
        or row.get("filiere")
        or row.get("specialty_name")
        or row.get("speciality")
        or ""
    ).strip()

    specialties: list = []
    if specialty_name:
        specialties = list(
            Specialty.objects.filter(school=ctx.school, name__iexact=specialty_name)
        )
        if not specialties:
            record_row_note(
                result,
                f"academics: specialty {specialty_name!r} not found for {subject.name!r}",
            )
            return
    elif category == "GENERAL" or is_general_subject_name(subject.name, category):
        specialties = list(Specialty.objects.filter(school=ctx.school))
    elif category == "PROFESSIONAL":
        codes = list(
            Specialty.objects.filter(school=ctx.school).values_list("code", flat=True)
        )
        matched_codes = specialty_codes_for_subject(subject.name, codes)
        if matched_codes:
            specialties = list(
                Specialty.objects.filter(school=ctx.school, code__in=matched_codes)
            )
        if not specialties:
            record_row_note(
                result,
                f"academics: professional subject {subject.name!r} has no specialty link yet",
            )
            return
    else:
        return

    is_core = category != "GENERAL" if category else True
    for sp in specialties:
        link, created = SpecialtySubject.objects.get_or_create(
            specialty=sp,
            subject=subject,
            defaults={
                "coefficient": coef if coef is not None else 1,
                "is_core": is_core,
            },
        )
        if link.school_id != ctx.school_id:
            link.school = ctx.school
            link.save(update_fields=["school"])
        updates: list[str] = []
        if coef is not None and link.coefficient != coef:
            link.coefficient = coef
            updates.append("coefficient")
        if link.is_core != is_core:
            link.is_core = is_core
            updates.append("is_core")
        if updates:
            link.save(update_fields=updates)
        if created:
            result.created += 0  # curriculum links are not primary entity counts


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
                # Two resolvers, merged from parallel fixes: the model-derived
                # matcher understands any choice the model grows; the alias map
                # catches French spellings the display labels do not.
                raw_category = row.get("category") or row.get("subject_category")
                category = (
                    (
                        _resolve_category(raw_category, Subject)
                        or _resolve_subject_category(raw_category)
                    )
                    if "category" in subject_fields
                    else None
                )
                coefficient = _resolve_row_coefficient(row, category=category)
                create_kwargs: dict[str, Any] = {}
                # Credits column is higher-ed semantics; francophone coef maps to curriculum.
                credits = coerce_decimal(row.get("credits"))
                if (
                    credits is not None
                    and "credits" in subject_fields
                    and not category
                    and not row.get("coef")
                    and not row.get("coefficient")
                ):
                    create_kwargs["credits"] = credits
                if category is not None and "category" in subject_fields:
                    create_kwargs["category"] = category
                if code and "code" in subject_fields:
                    create_kwargs["code"] = code[:30]  # magic-number-allow: Subject.code max_length
                obj, created = get_or_create_named(
                    model=Subject,
                    school=ctx.school,
                    name=name[:120],  # magic-number-allow: Subject.name CharField max_length
                    create_kwargs=(lambda ck=create_kwargs: ck) if create_kwargs else None,
                    result=result,
                )
                updates: dict[str, Any] = {}
                if category is not None and "category" in subject_fields and obj.category != category:
                    # Backfill: only a row still on the field DEFAULT may take the
                    # import's category -- a category somebody set by hand is that
                    # school's decision and a re-upload must not overturn it.
                    if obj.category == Subject.Category.OTHER:
                        updates["category"] = category
                    elif explicit_conflict_resolution_for(ctx=ctx, canonical_obj=obj) in (
                        "OVERWRITE",
                        "MERGE",
                    ):
                        # The operator reviewed this exact disagreement and said
                        # the file wins. That recorded decision is the provenance
                        # Subject.category itself lacks.
                        updates["category"] = category
                    else:
                        # A note is durable but is NOT a held row -- nothing in
                        # the review queue would ever offer this to an operator.
                        # detect_conflict makes the disagreement ACTIONABLE: it
                        # mints a MigrationConflict the conflicts screen shows,
                        # and an explicit OVERWRITE there is honoured by the
                        # branch above on the next apply of this bundle.
                        detect_conflict(
                            ctx=ctx,
                            domain="academics",
                            canonical_obj=obj,
                            incoming={"category": category},
                            legacy_id=code or name,
                        )
                        record_row_note(
                            result,
                            f"academics: kept category {obj.category!r} for"
                            f" {name!r} (import says {category!r}; the row was"
                            " set deliberately and an import does not outrank it;"
                            " logged for conflict review)",
                        )
                if code and "code" in subject_fields:
                    trimmed = code[:30]  # magic-number-allow: Subject.code max_length
                    if trimmed and obj.code != trimmed:
                        updates["code"] = trimmed
                if (
                    credits is not None
                    and "credits" in subject_fields
                    and not category
                    and not row.get("coef")
                    and not row.get("coefficient")
                    and obj.credits != credits
                ):
                    updates["credits"] = credits
                if updates:
                    for field, value in updates.items():
                        setattr(obj, field, value)
                    obj.save(update_fields=list(updates.keys()))
                if created:
                    result.created += 1
                elif updates:
                    result.updated += 1
                else:
                    result.skipped += 1
                if raw_category and category is None:
                    record_row_note(
                        result,
                        f"academics: category {str(raw_category)[:40]!r} on"
                        f" {name!r} matches no Subject.Category choice; left at"
                        " the model default (value preserved in custom fields)",
                    )
                record_id_mapping(ctx=ctx, legacy_id=code or name, canonical_obj=obj, domain="academics")
                persist_dfv_extras(
                    ctx=ctx,
                    entity_type="subject",
                    entity_id=obj.pk,
                    extras={
                        "description": (row.get("description") or "").strip(),
                        "fr_title": (row.get("fr_title") or "").strip(),
                        "source_coef": str(row.get("coef") or row.get("coefficient") or ""),
                    },
                    result=result,
                )
                _link_subject_curriculum(
                    ctx=ctx,
                    result=result,
                    subject=obj,
                    row=row,
                    category=category,
                    coefficient=coefficient,
                )
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

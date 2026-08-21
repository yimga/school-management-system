"""Structure lander — provisions the academic scaffold a SPLIT needs.

The gap this closes (2026-07-09 follow-up to the merge/split completeness fix
b69fb559d): the grades lander RESOLVES an FK graph at the target and, by
explicit design, "NEVER fabricates structure". That is correct for a MERGE
(land into an existing school and map to its own calendar/subjects), but a
SPLIT lands a cohort into a fresh/greenfield target that has NONE of the
source's ``AcademicYear``/``Term``/``Subject``/``Specialty``/``Classroom``/
``SubjectAssignment`` — so enrollment and grades quarantine 100% and the split
school arrives with an empty gradebook. This lander is the "deploy the metadata
before the data" step (the Salesforce pattern): it runs in wave 0, BEFORE
students/enrollment/grades, and provisions the graph the resolver later binds
to. It is emitted ONLY for splits (``school_batch_service`` adds the
``structure`` domain when ``batch.kind == SPLIT``); a merge never carries it.

Canonical row shape — one per source ``SubjectAssignment`` the student's grades
reference (idempotent, so a whole cohort's overlapping rows collapse)::

    {
        "academic_year": "2025/2026",  "year_start": "2025-09-01",
        "year_end": "2026-07-01",      "year_is_active": "true",
        "term": "FIRST",  "term_label": "",  "term_position": "1",
        "term_start": "2025-09-01",  "term_end": "2025-12-15",
        "department": "Science",
        "classroom": "Form 4A",
        "specialty": "General",
        "subject": "Mathematics",  "coefficient": "1",
        "teacher_ref": "j.doe",  "teacher_first_name": "Jane",
        "teacher_last_name": "Doe",  "teacher_email": "jane@example.com",
    }

Guardrails (nothing is chanced):
  * REUSE-FIRST by (school, name): an existing target structure is never
    modified or duplicated — the row binds to what the school already has.
  * ``Department``/``Specialty``/``Classroom`` carry a GLOBALLY-unique ``code``
    (not per-school). The source's code MUST NOT be reused at the target — on
    a single-schema deployment it would collide or, worse, resolve the SOURCE
    school's row (cross-tenant leak). We look up by name and MINT a fresh
    target-scoped code on create.
  * The teacher is a NEW, TARGET-SCOPED ``User`` (role TEACHER, UNUSABLE
    password — no credential is minted) + its own ``TeacherProfile``. We never
    re-link the source teacher's ``User``: ``TeacherProfile.user`` is OneToOne,
    so the source teacher (who already has a profile) cannot get a second one.
  * ``ctx.dry_run`` writes nothing and only counts would-be creates.
  * Per-row failures quarantine and continue — a bad row never aborts the
    scaffold or lands a half-built graph.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterator

from ._helpers import (
    coerce_date,
    coerce_decimal,
    mint_scoped_code,
    model_field_names,
    record_id_mapping,
    record_row_error,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register
from .reason_codes import LANDER_ERROR, MISSING_REQUIRED


def _truthy(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "y", "t")


def _mint_code(*, prefix: str, name: str, school, model, code_field: str = "code") -> str:
    """Thin alias over the shared :func:`_helpers.mint_scoped_code` (single source
    of truth). Kept so existing call sites are unchanged. The shared minter
    length-bounds the school token so the NAME survives the 30-char ``code`` cap
    even when ``School.pk`` is a UUID — the duplicate that used to live here
    silently collapsed every provisioned Department/Specialty/Classroom code to
    one value (UUID filled the first 30 chars), quarantining the whole scaffold."""
    return mint_scoped_code(
        prefix=prefix, name=name, school=school, model=model, code_field=code_field
    )


def _free_username(User, base: str) -> str:
    base = (re.sub(r"[^a-zA-Z0-9._-]+", "", base or "") or "teacher")[:130]  # magic-number-allow: username-stem-cap-leaves-digest-suffix-room-under-150
    if not User.objects.filter(username=base).exists():
        return base
    digest = hashlib.sha256(base.lower().encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}"[:150]  # magic-number-allow: django-username-field-max-length-150


class StructureLander(Lander):
    domain = "structure"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.academics.models import (
                AcademicYear,
                Classroom,
                Department,
                Specialty,
                Subject,
                SubjectAssignment,
                Term,
            )
        except ImportError as exc:
            raise LanderError(
                f"StructureLander could not import academics models: {exc!s}"
            ) from exc

        school = getattr(ctx, "school", None)
        result = LanderResult()

        for row in canonical_rows:
            year_name = (row.get("academic_year") or "").strip()
            term_name = (row.get("term") or "").strip()
            classroom_name = (row.get("classroom") or "").strip()
            specialty_name = (row.get("specialty") or "").strip()
            subject_name = (row.get("subject") or "").strip()
            if not (year_name and term_name and classroom_name and specialty_name and subject_name):
                record_row_error(
                    result,
                    row,
                    f"structure: missing year/term/classroom/specialty/subject in {row!r}",
                    reason_code=MISSING_REQUIRED,
                )
                continue

            if ctx.dry_run:
                # Report what would be provisioned without writing.
                result.created += 1
                continue

            try:
                self._provision_row(
                    row=row,
                    school=school,
                    ctx=ctx,
                    result=result,
                    models=(
                        AcademicYear,
                        Term,
                        Department,
                        Classroom,
                        Specialty,
                        Subject,
                        SubjectAssignment,
                    ),
                    names=(year_name, term_name, classroom_name, specialty_name, subject_name),
                )
            except Exception as exc:  # noqa: BLE001 — per-row quarantine, never abort the scaffold
                record_row_error(
                    result,
                    row,
                    f"structure provision failed for {classroom_name}/{term_name}/"
                    f"{subject_name}: {type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
        return result

    def _provision_row(self, *, row, school, ctx, result, models, names):
        (
            AcademicYear,
            Term,
            Department,
            Classroom,
            Specialty,
            Subject,
            SubjectAssignment,
        ) = models
        year_name, term_name, classroom_name, specialty_name, subject_name = names

        # 1. AcademicYear — reuse by (school, name), else create with dates.
        year = self._get_or_create_named(
            model=AcademicYear,
            school=school,
            name=year_name,
            create_kwargs=lambda: {
                "start_date": coerce_date(row.get("year_start")) or _fallback_year_start(),
                "end_date": coerce_date(row.get("year_end")) or _fallback_year_end(),
                "is_active": _truthy(row.get("year_is_active")),
            },
            result=result,
        )

        # 2. Department — reuse by (school, name); mint a target-scoped code.
        dept_name = (row.get("department") or "").strip() or "General"
        department = self._get_or_create_named(
            model=Department,
            school=school,
            name=dept_name,
            create_kwargs=lambda: {
                "code": _mint_code(prefix="DPT", name=dept_name, school=school, model=Department)
            },
            result=result,
        )

        # 3. Classroom — reuse by (school, name); needs year + department; mint code.
        classroom = self._get_or_create_named(
            model=Classroom,
            school=school,
            name=classroom_name,
            create_kwargs=lambda: {
                "academic_year": year,
                "department": department,
                "code": _mint_code(
                    prefix="CLS", name=classroom_name, school=school, model=Classroom
                ),
            },
            result=result,
        )

        # 4. Specialty — reuse by (school, name); needs department; mint code.
        specialty = self._get_or_create_named(
            model=Specialty,
            school=school,
            name=specialty_name,
            create_kwargs=lambda: {
                "department": department,
                "code": _mint_code(
                    prefix="SPC", name=specialty_name, school=school, model=Specialty
                ),
            },
            result=result,
        )

        # 5. Term — reuse by (school, year, name); needs start/end dates.
        term = self._get_or_create_term(
            Term=Term,
            school=school,
            year=year,
            row=row,
            term_name=term_name,
            result=result,
        )

        # 6. Subject — reuse by (school, name).
        subject = self._get_or_create_named(
            model=Subject,
            school=school,
            name=subject_name,
            create_kwargs=lambda: {},
            result=result,
        )

        # 7. Teacher — target-scoped User (role TEACHER, unusable password) + own
        #    TeacherProfile. NEVER re-links the source teacher (OneToOne profile).
        teacher_user = self._resolve_or_provision_teacher(
            row=row, school=school, ctx=ctx, result=result
        )

        # 8. SubjectAssignment — reuse by the model's own unique tuple; attach teacher.
        assignment, created = self._get_or_create_assignment(
            SubjectAssignment=SubjectAssignment,
            school=school,
            year=year,
            term=term,
            classroom=classroom,
            specialty=specialty,
            subject=subject,
            coefficient=coerce_decimal(row.get("coefficient")),
            result=result,
        )
        if teacher_user is not None and not assignment.teachers.filter(pk=teacher_user.pk).exists():
            assignment.teachers.add(teacher_user)

        legacy_id = f"{year_name}:{term_name}:{classroom_name}:{specialty_name}:{subject_name}"
        record_id_mapping(ctx=ctx, legacy_id=legacy_id, canonical_obj=assignment, domain="structure")
        if created:
            result.created += 1
        else:
            result.skipped += 1

    # ── helpers ────────────────────────────────────────────────────────

    def _get_or_create_named(self, *, model, school, name, create_kwargs, result):
        """Reuse an existing (school, name) row or create one. Never mutates
        an existing row (the target's own config wins)."""
        qs = model.objects.all()  # tenant-isolation-allow: scoped-below-by-school-when-present / schema-context-isolates
        fields = model_field_names(model)
        if "school" in fields and school is not None:
            qs = qs.filter(school=school)
        obj = qs.filter(name=name).order_by("pk").first()
        if obj is not None:
            return obj
        kwargs: dict[str, Any] = {"name": name}
        if "school" in fields and school is not None:
            kwargs["school"] = school
        kwargs.update(create_kwargs())
        obj = model.objects.create(**kwargs)
        result.created_ids.append(obj.pk)
        return obj

    def _get_or_create_term(self, *, Term, school, year, row, term_name, result):
        qs = Term.objects.filter(academic_year=year)  # tenant-isolation-allow: academic_year is school-bound; scoped via its parent
        obj = qs.filter(name=term_name).order_by("pk").first()
        if obj is not None:
            return obj
        position = None
        raw_pos = (str(row.get("term_position") or "").strip())
        if raw_pos.isdigit() and 1 <= int(raw_pos) <= 12:
            position = int(raw_pos)
        kwargs: dict[str, Any] = {
            "academic_year": year,
            "name": term_name[:20],
            "custom_label": (row.get("term_label") or "").strip()[:30],
            "start_date": coerce_date(row.get("term_start"))
            or getattr(year, "start_date", None)
            or _fallback_year_start(),
            "end_date": coerce_date(row.get("term_end"))
            or getattr(year, "end_date", None)
            or _fallback_year_end(),
        }
        if "school" in model_field_names(Term) and school is not None:
            kwargs["school"] = school
        if position is not None:
            kwargs["position"] = position
        obj = Term.objects.create(**kwargs)
        result.created_ids.append(obj.pk)
        return obj

    def _get_or_create_assignment(
        self, *, SubjectAssignment, school, year, term, classroom, specialty, subject,
        coefficient, result,
    ):
        lookup = {
            "academic_year": year,
            "term": term,
            "classroom": classroom,
            "specialty": specialty,
            "subject": subject,
        }
        obj = SubjectAssignment.objects.filter(**lookup).order_by("pk").first()  # tenant-isolation-allow: FKs above are all school-bound rows resolved for ctx.school
        if obj is not None:
            return obj, False
        create_kwargs = dict(lookup)
        if "school" in model_field_names(SubjectAssignment) and school is not None:
            create_kwargs["school"] = school
        if coefficient is not None:
            create_kwargs["coefficient"] = coefficient
        obj = SubjectAssignment.objects.create(**create_kwargs)
        result.created_ids.append(obj.pk)
        return obj, True

    def _resolve_or_provision_teacher(self, *, row, school, ctx, result):
        """A target-scoped teacher User (role TEACHER, unusable password) + its
        own TeacherProfile. Idempotent by the minted username. Returns the User
        or None (the caller quarantines the grade later if no teacher exists)."""
        from django.contrib.auth import get_user_model

        from apps.people.models import TeacherProfile

        User = get_user_model()
        teacher_ref = (row.get("teacher_ref") or "").strip()
        sid = str(getattr(school, "pk", "") or "0")
        # Target-scoped username so we NEVER collide with / re-link the source
        # teacher's own User (which already owns a TeacherProfile — OneToOne).
        base = f"{teacher_ref or 'teacher'}.s{sid}"
        username = _free_username(User, base)

        user = User.objects.filter(username=username).first()
        if user is None:
            user = User.objects.create_user(
                username=username,
                email=(row.get("teacher_email") or "").strip(),
                first_name=(row.get("teacher_first_name") or "").strip(),
                last_name=(row.get("teacher_last_name") or "").strip(),
            )
            if hasattr(user, "role") and hasattr(User, "Role"):
                user.role = User.Role.TEACHER
            user.set_unusable_password()
            user.save()
            result.created_ids.append(user.pk)

        # One TeacherProfile per user (OneToOne); create it at the target school.
        profile_qs = TeacherProfile.objects.filter(user=user)  # tenant-isolation-allow: OneToOne user resolves a single profile row
        if not profile_qs.exists():
            create_kwargs: dict[str, Any] = {"user": user}
            if "school" in model_field_names(TeacherProfile) and school is not None:
                create_kwargs["school"] = school
            profile = TeacherProfile.objects.create(**create_kwargs)
            result.created_ids.append(profile.pk)
        return user


def _fallback_year_start():
    # Structure rows always carry the source dates; this is a defensive floor
    # only for a malformed row missing them (better a provisioned year than a
    # quarantined cohort). Date.today() is avoided (kept deterministic).
    import datetime as _dt

    return _dt.date(2000, 1, 1)


def _fallback_year_end():
    import datetime as _dt

    return _dt.date(2000, 12, 31)


register("structure", StructureLander())

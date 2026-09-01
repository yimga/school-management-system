"""Student lander — persists canonical student rows into ``apps.people.StudentProfile``.

Upsert keyed on ``external_id`` (the source-system identifier) — the
single most-asked-for property of any migration ("re-running the bundle
must not create duplicate students").
"""

from __future__ import annotations

import re
from typing import Any, Iterator

from ._helpers import (
    _clean_source_string,
    _jsonable,
    conflict_resolution_for,
    derive_external_id,
    detect_and_register_assets,
    detect_conflict,
    map_enrollment_status,
    persist_dfv_extras,
    record_id_mapping,
    record_row_error,
    record_row_note,
    row_savepoint,
    save_scoped,
    split_name_for,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register
from .reason_codes import LANDER_ERROR, MISSING_REQUIRED


class StudentLander(Lander):
    domain = "students"
    # Sweeps every custom_fields.*/_unmapped.* key into StudentProfile
    # .custom_attributes (see _sweep_custom_attributes), so the orchestrator's
    # residual net must NOT double-capture behind it.
    sweeps_custom_columns = True

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        # Deferred import: tenant model only resolves under schema_context.
        try:
            from apps.people.models import StudentProfile
        except ImportError as exc:
            raise LanderError(
                f"StudentLander could not import StudentProfile: {exc!s}"
            ) from exc

        result = LanderResult()
        for row in canonical_rows:
            external_id = _clean_source_string(row.get("external_id"))
            first_name = _clean_source_string(row.get("first_name"))
            last_name = _clean_source_string(row.get("last_name"))
            middle_name = _clean_source_string(row.get("middle_name"))
            # Combined-name fallback: many real exports (African / French-model
            # SIS) carry ONE "Name"/"NAME" column, not separate given/family
            # columns. When the source has no first/last, split the canonical
            # ``full_name`` locale-aware so the row is NOT quarantined for
            # "missing first/last" — historically the single biggest real-world
            # data-loss cause on these rosters (0/426 students landed).
            full_name = _clean_source_string(row.get("full_name"))
            if full_name and (not first_name or not last_name):
                fn, mn, ln = split_name_for(ctx, full_name)
                first_name = first_name or fn
                last_name = last_name or ln
                middle_name = middle_name or mn
            # No source-system id: derive a STABLE one from the row's identity so
            # the roster lands and stays idempotent on re-apply. Plenty of real
            # exports carry only name/DOB/class -- this school's did -- and the
            # AND-gate below quarantined every such row ("missing_required"),
            # which on an atomic bundle rolled back the valid files beside it too.
            # Runs after the full_name split so a combined-name roster keys off the
            # same resolved name the row will actually be stored under.
            if not external_id:
                external_id = derive_external_id(
                    first_name=first_name,
                    middle_name=middle_name,
                    last_name=last_name,
                    date_of_birth=row.get("date_of_birth"),
                    place_of_birth=row.get("place_of_birth"),
                )
            if not external_id or not first_name or not last_name:
                record_row_error(
                    result,
                    row,
                    f"Missing required fields (external_id/first/last) in row {row!r}",
                    reason_code=MISSING_REQUIRED,
                )
                continue

            # Canonical enrollment_status is a lifecycle token; StudentProfile
            # stores it on ``status`` (a constrained choice), NOT a field named
            # ``enrollment_status`` — writing that key silently dropped the state.
            mapped_status = map_enrollment_status(row.get("enrollment_status"))
            phone_val = (row.get("phone") or "").strip()
            parent_phone_val = (row.get("parent_phone") or "").strip()
            defaults = {
                "first_name": first_name,
                "last_name": last_name,
                "middle_name": middle_name,
                "admission_number": _clean_source_string(row.get("admission_number")),
                "email": (row.get("email") or "").strip(),
                "phone": phone_val,
                "date_of_birth": row.get("date_of_birth") or None,
                "gender": (row.get("gender") or "").strip(),
                "grade_level": (row.get("grade_level") or "").strip(),
                "status": mapped_status,
                "address": (row.get("address") or "").strip(),
                # Real StudentProfile columns most SIS exports carry inline —
                # these used to quarantine as 0%-confidence custom fields (no
                # ontology entry). Now mapped + landed into their proper home.
                "place_of_birth": (row.get("place_of_birth") or "").strip(),
                "joined_date": row.get("joined_date") or None,
                "joined_term": (row.get("joined_term") or "").strip(),
                "section": (row.get("section") or "").strip(),
                "parent_phone": parent_phone_val,
                "exam_candidate_number": (row.get("exam_candidate_number") or "").strip(),
                "exam_center_code": (row.get("exam_center_code") or "").strip(),
                "exam_system": (row.get("exam_system") or "").strip(),
            }
            # Filter to fields the model actually has, to be schema-tolerant.
            model_fields = {f.name for f in StudentProfile._meta.get_fields()}
            # Closest-real-home fallback: this StudentProfile has no student
            # ``phone`` column but does have ``parent_phone``. On a student
            # roster the lone "Mobile Number" is the contact number, so land it
            # in the real column rather than as an inert custom field (operator
            # can re-map). Only when parent_phone wasn't itself provided.
            if (
                phone_val
                and "phone" not in model_fields
                and "parent_phone" in model_fields
                and not defaults.get("parent_phone")
            ):
                defaults["parent_phone"] = phone_val
            # Canonical columns this tenant's StudentProfile doesn't model
            # (middle_name/email/phone/grade_level/address vary by deployment) —
            # preserved as custom fields after the upsert so no source data is
            # silently dropped. The raw enrollment_status token is kept too.
            extras = {
                "middle_name": middle_name,
                "email": (row.get("email") or "").strip(),
                "phone": phone_val,
                "grade_level": (row.get("grade_level") or "").strip(),
                "address": (row.get("address") or "").strip(),
                "enrollment_status": (row.get("enrollment_status") or "").strip(),
            }
            extras = {k: v for k, v in extras.items() if k not in model_fields and v}
            # If phone was folded into the real parent_phone column above, don't
            # ALSO duplicate it as a custom field.
            if defaults.get("parent_phone") == phone_val and phone_val:
                extras.pop("phone", None)
            defaults = {k: v for k, v in defaults.items() if k in model_fields and v not in (None, "")}

            # Bind created/updated rows to the bundle's school, and scope the
            # upsert key by school too — on single-schema deployments the
            # external id is only unique per school (an inter-school transfer
            # deliberately reuses it at the target).
            school_scope: dict[str, Any] = {}
            if ctx.school is not None and "school" in model_fields:
                # Scope the lookup only — never put the School instance into
                # ``defaults`` (it leaks into updated_ids → MigrationRun JSON).
                school_scope = {"school": ctx.school}

            if ctx.dry_run:
                exists = StudentProfile.objects.filter(  # tenant-isolation-allow: lander runs inside schema_context(bundle.schema_name)
                    **school_scope,
                    **{_lookup_field("external_id", model_fields): external_id},
                ).exists()
                if exists:
                    result.updated += 1
                else:
                    result.created += 1
                continue

            try:
                lookup_field = _lookup_field("external_id", model_fields)
                # Never let defaults overwrite the upsert key with a *different*
                # source column (e.g. lookup admission_number=external_id while
                # defaults.admission_number=CSV-adm). That creates a row whose
                # unique key no longer matches the lookup, so re-apply 500s as
                # UNIQUE constraint on (school, admission_number).
                defaults.pop(lookup_field, None)
                if (
                    "student_code" in model_fields
                    and lookup_field != "student_code"
                    and not defaults.get("student_code")
                ):
                    defaults["student_code"] = external_id
                existing_obj = StudentProfile.objects.filter(  # tenant-isolation-allow: lander runs inside schema_context(bundle.schema_name)
                    **school_scope,
                    **{lookup_field: external_id},
                ).first()
                if existing_obj is None and "admission_number" in model_fields:
                    # Legacy rows created under the pre-fix bug (lookup key
                    # drifted from admission_number) — recover by admission
                    # number when the CSV still carries it.
                    adm = (row.get("admission_number") or "").strip()
                    if adm:
                        existing_obj = StudentProfile.objects.filter(  # tenant-isolation-allow: lander runs inside schema_context(bundle.schema_name)
                            **school_scope,
                            admission_number=adm,
                        ).first()
                # Second-chance FUZZY match: the same person arriving under a
                # DIFFERENT source key (a re-migration, or a second source
                # system) would otherwise create a duplicate student. When both
                # key-based lookups miss, an UNAMBIGUOUS high-confidence name+DOB
                # match links to the existing row instead of inserting. Gated to
                # exact-DOB + single-candidate + score floor so it can never
                # wrong-merge two distinct people; anything short of that falls
                # through to create + post-hoc surfacing (unchanged).
                fuzzy_linked = False
                fuzzy_score = None
                if existing_obj is None:
                    match = _find_fuzzy_duplicate(
                        StudentProfile, school_scope, row, model_fields
                    )
                    if match is not None:
                        existing_obj, fuzzy_score = match
                        fuzzy_linked = True
                # On a fuzzy link, never let the incoming identity keys clobber
                # the existing student's own keys — the new source id is recorded
                # as an id-mapping, not written over the canonical key.
                apply_defaults = defaults
                if fuzzy_linked:
                    apply_defaults = {
                        k: v for k, v in defaults.items()
                        if k not in _IDENTITY_KEY_FIELDS
                    }
                if existing_obj is not None:
                    detect_conflict(
                        ctx=ctx, domain="students",
                        canonical_obj=existing_obj, incoming=apply_defaults,
                        legacy_id=external_id,
                    )
                    resolution = conflict_resolution_for(ctx=ctx, canonical_obj=existing_obj)
                    if resolution == "PRESERVE":
                        result.skipped += 1
                        record_id_mapping(
                            ctx=ctx, legacy_id=external_id,
                            canonical_obj=existing_obj, domain="students",
                        )
                        if fuzzy_linked:
                            _record_fuzzy_link(ctx, existing_obj, external_id, fuzzy_score, row)
                        continue
                    # Update in place when we recovered via admission_number or a
                    # fuzzy name+DOB match rather than the primary lookup field.
                    written: list[str] = []
                    for k, v in apply_defaults.items():
                        setattr(existing_obj, k, v)
                        written.append(k)
                    if lookup_field in model_fields and not fuzzy_linked:
                        setattr(existing_obj, lookup_field, external_id)
                        written.append(lookup_field)
                    # Per-row savepoint: students land in an EARLIER wave of the same
                    # forced-atomic finance transaction, so a bad student row must roll
                    # back only itself — not poison the whole apply (see _helpers.row_savepoint).
                    #
                    # save_scoped, NOT save(): this is the ONLY update path a student
                    # takes, and a bare save() rewrote all ~35 columns from the snapshot
                    # read above. Every column this file did not mention was re-asserted
                    # from stale memory, reverting whatever the alumni artifact running
                    # BESIDE it in wave 1 (parallel thread, own connection) had already
                    # committed. The lander then reported the row as a clean update.
                    with row_savepoint():
                        save_scoped(existing_obj, written)
                    obj, created = existing_obj, False
                    if fuzzy_linked:
                        _record_fuzzy_link(ctx, existing_obj, external_id, fuzzy_score, row)
                else:
                    with row_savepoint():
                        obj, created = StudentProfile.objects.update_or_create(
                            **school_scope,
                            **{lookup_field: external_id},
                            defaults=defaults,
                        )
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                    _surface_dedup_candidates(StudentProfile, obj, row, ctx)
                else:
                    result.updated += 1
                    result.updated_ids_with_old_values.append(
                        {
                            "pk": obj.pk,
                            "old": {
                                k: _jsonable(getattr(obj, k, None)) for k in defaults
                            },
                        }
                    )
                persist_dfv_extras(
                    ctx=ctx, entity_type="student", entity_id=obj.pk,
                    extras=extras, result=result,
                )
                record_id_mapping(
                    ctx=ctx, legacy_id=external_id,
                    canonical_obj=obj, domain="students",
                )
                detect_and_register_assets(
                    ctx=ctx, legacy_id=external_id, entity_kind="student", row=row,
                )
                # Place the student on their trade Specialty (created in wave 0).
                # Best-effort enrichment: an unresolved specialty is preserved as
                # a custom field and never quarantines the (already-landed) student.
                _link_student_specialty(obj, row, ctx, model_fields, result)
                # Place the student in a first-class Classroom derived from their
                # class/form label ('Form Two'), creating it (default 2025/2026
                # year, admin-editable) if the school doesn't have it. Runs after
                # the specialty link so the classroom can inherit the trade's
                # department. Best-effort — never quarantines the landed student.
                _link_student_classroom(obj, row, ctx, model_fields, result)
                # Preserve a free-text parent/guardian NAME from the roster as a
                # student-scoped, ACCOUNT-FREE claimable hint (G6) — never a User /
                # StudentGuardian at ingest (COPPA-safe). A parent who later links
                # this child sees it surfaced for confirmation.
                _link_student_guardian_hint(obj, row, ctx, result)
                # Sweep EVERY still-unmapped column into the student's own
                # ``custom_attributes`` JSON so nothing on the roster is lost AND
                # it stays joined to the student (unlike the generic DFV path,
                # which keys to a synthetic migration_artifact row). This is what
                # makes "always ingest everything" true even for columns with no
                # canonical home. Best-effort — never quarantines the landed row.
                _sweep_custom_attributes(obj, row, model_fields, result)
            except Exception as exc:  # noqa: BLE001 — per-row quarantine
                record_row_error(
                    result,
                    row,
                    f"upsert failed for {external_id}: {type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
        return result


def _norm_spec(v: str) -> str:
    """Normalize a specialty label for matching: drop a trailing source code
    ('FASHION DESIGN - FD' / 'WELDING AND METAL FABRICATION - MWIP'), fold to
    upper, collapse punctuation + runs of whitespace."""
    s = re.sub(r"\s+-\s+[A-Z0-9]{1,6}\s*$", "", (v or "").strip().upper())
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _resolve_specialty_fuzzy(school, ref: str):
    """Resolve a student's inline specialty label to a ``Specialty`` row.

    The single-file TVET roster carries the specialty name INLINE ('WELDING AND
    METAL FABRICATION') while the catalog row may carry a trailing code ('WELDING
    AND METAL FABRICATION - MWIP'), so exact code/name is tried first, then a
    normalized-name match (strip the trailing code, fold case/whitespace). No
    guessy token-subset step — an unmatched label stays unresolved (never
    wrong-links two distinct trades).
    """
    ref = (ref or "").strip()
    if not ref:
        return None
    try:
        from apps.academics.models import Specialty
    except ImportError:
        return None
    qs = (  # tenant-isolation-allow: scoped by school kwarg when present; schema_context isolates otherwise
        Specialty.objects.filter(school=school)
        if school is not None
        else Specialty.objects.all()
    )
    exact = (
        qs.filter(code__iexact=ref).first()  # tenant-isolation-allow: scoped-above-via-school-or-schema-context
        or qs.filter(name__iexact=ref).first()  # tenant-isolation-allow: scoped-above-via-school-or-schema-context
    )
    if exact is not None:
        return exact
    target = _norm_spec(ref)
    if not target:
        return None
    for spec in qs[:300]:  # tenant-isolation-allow: scoped-above-via-school-or-schema-context  # magic-number-allow: specialty-catalog scan cap
        if _norm_spec(spec.name) == target:
            return spec
    return None


def _link_student_specialty(obj, row: dict[str, Any], ctx, model_fields, result) -> None:
    """Best-effort: set ``StudentProfile.specialty`` from the roster's inline
    specialty label, and always preserve the raw label as a custom field so an
    unresolved specialty is never dropped. Never raises / quarantines."""
    ref = (row.get("specialty") or "").strip()
    if not ref:
        return
    # Preserve the source label regardless of whether it resolves.
    persist_dfv_extras(
        ctx=ctx, entity_type="student", entity_id=obj.pk,
        extras={"specialty_source": ref}, result=result,
    )
    if "specialty" not in model_fields or getattr(obj, "specialty_id", None):
        return  # model has no FK, or the student is already placed — never overwrite
    spec = _resolve_specialty_fuzzy(getattr(ctx, "school", None), ref)
    if spec is None:
        return
    try:
        with row_savepoint():
            obj.specialty = spec
            # save_scoped: setting the third of academic_year/specialty/classroom makes
            # the model mint an admission_number inside save(); a bare
            # update_fields=["specialty"] computed it and dropped it on the floor.
            save_scoped(obj, ["specialty"])
    except Exception:  # noqa: BLE001 — enrichment is best-effort; student already landed
        pass


def _resolve_department_for_student(school, student):
    """The department a student's classroom should hang off: the student's own
    trade Specialty's department (TVET) when placed, else the school's General
    department. Never raises — returns ``None`` only if even the General
    department cannot be ensured."""
    spec = getattr(student, "specialty", None)
    if spec is not None and getattr(spec, "department_id", None):
        try:
            return spec.department
        except Exception:  # noqa: BLE001 — fall back to General
            pass
    try:
        from apps.academics.structure_provisioning import ensure_general_department

        return ensure_general_department(school)
    except Exception:  # noqa: BLE001
        return None


def _resolve_or_create_classroom(school, label: str, student):
    """Reuse-or-create a school-scoped ``Classroom`` named after the roster's
    class/form label. Its two required PROTECT FKs are supplied: the school's
    academic year (default 2025/2026, created only if none exists) and the
    student's specialty department (else General). The globally-unique code is
    minted UUID-safe via ``mint_scoped_code``. Returns the classroom or ``None``
    when a required FK cannot be resolved."""
    from apps.academics.models import Classroom

    from ._helpers import get_or_create_named, mint_scoped_code

    name = re.sub(r"\s+", " ", (label or "").strip())
    if not name:
        return None
    from apps.migration_cloud.post_apply_provision import ensure_default_academic_year

    year, _created = ensure_default_academic_year(school)
    if year is None:
        return None
    dept = _resolve_department_for_student(school, student)
    if dept is None:
        return None
    classroom, _made = get_or_create_named(
        model=Classroom,
        school=school,
        name=name,
        create_kwargs=lambda: {
            "code": mint_scoped_code(prefix="CLS", name=name, school=school, model=Classroom),
            "academic_year": year,
            "department": dept,
        },
    )
    return classroom


def _link_student_classroom(obj, row: dict[str, Any], ctx, model_fields, result) -> None:
    """Best-effort: place the student in a first-class ``Classroom`` derived from
    the roster's class/form label (canonical ``grade_level`` — 'Form Two'),
    creating the classroom (2025/2026 year, the trade's department) if the school
    doesn't have it yet. Always preserves the raw label as a custom field so an
    unresolved class is never dropped. Never raises / quarantines.

    ``StudentProfile.classroom`` is a nullable compat-projection FK (the SOT is
    ``Enrollment``, but ``current_classroom`` falls back to it), so setting it +
    ``academic_year`` places the student without constructing a full Enrollment
    row. The write goes through ``save_scoped`` rather than a FULL ``save()``:
    the full save was here so the admission-number auto-generation that setting
    all three of academic_year/specialty/classroom triggers would persist, and
    save_scoped carries that output (and search_index) without also re-asserting
    every other column from a stale in-memory snapshot."""
    ref = (row.get("grade_level") or row.get("classroom") or "").strip()
    if not ref:
        return
    # Preserve the source label regardless of whether it resolves to a classroom.
    persist_dfv_extras(
        ctx=ctx, entity_type="student", entity_id=obj.pk,
        extras={"class_source": ref}, result=result,
    )
    if "classroom" not in model_fields or getattr(obj, "classroom_id", None):
        return  # model has no FK, or the student is already placed — never overwrite
    school = getattr(ctx, "school", None)
    if school is None:
        return
    try:
        classroom = _resolve_or_create_classroom(school, ref, obj)
    except Exception:  # noqa: BLE001 — placement is best-effort; student already landed
        classroom = None
    if classroom is None:
        return
    try:
        with row_savepoint():
            obj.classroom = classroom
            if "academic_year" in model_fields and getattr(obj, "academic_year_id", None) is None:
                obj.academic_year = classroom.academic_year
            save_scoped(obj, ["classroom", "academic_year"])
    except Exception:  # noqa: BLE001 — enrichment is best-effort; student already landed
        pass


# A roster embeds a parent/guardian NAME in a free-text column ("Parent",
# "Guardian", "Mother/Father", "Next of Kin"). Match the column NAME, not values.
_GUARDIAN_NAME_HINT_RE = re.compile(
    r"(parent|guardian|mother|father|next[\s_]*of[\s_]*kin|\bnok\b)", re.IGNORECASE
)
_GUARDIAN_PHONE_HINT_RE = re.compile(
    r"(phone|mobile|tel|contact|msisdn|cell|whatsapp)", re.IGNORECASE
)
# A guardian-ish column that is NOT the name (so we don't store an email/id/etc.
# under parent_name).
_GUARDIAN_NON_NAME_RE = re.compile(
    r"(email|mail|\bid\b|occupation|address|relation|status|number)", re.IGNORECASE
)
_HINT_NULL_LITERALS = frozenset({"", "none", "nan", "n/a", "na", "null", "-", "0"})


def _extract_guardian_hint(row: dict[str, Any]) -> tuple[str, str]:
    """Return ``(name, phone)`` for a parent/guardian named in a student roster.

    Scans only the pass-through columns (``custom_fields.*`` / ``_unmapped.*``) so
    a mapped first-class field is never re-read. Keyed on the column NAME carrying
    a parent/guardian token; a phone-ish guardian column feeds ``phone``, an
    id/email/occupation-ish one is ignored, everything else is the name. First
    non-empty wins."""
    name = ""
    phone = ""
    for key, value in row.items():
        if not isinstance(key, str):
            continue
        m = re.match(r"^(?:custom_fields|_unmapped)\.(.+)$", key)
        if not m:
            continue
        col = m.group(1)
        if not _GUARDIAN_NAME_HINT_RE.search(col):
            continue
        v = str(value).strip() if value is not None else ""
        if v.lower() in _HINT_NULL_LITERALS:
            continue
        if _GUARDIAN_PHONE_HINT_RE.search(col):
            phone = phone or v
        elif not _GUARDIAN_NON_NAME_RE.search(col):
            name = name or v
    return name, phone


def _extract_guardian_email(row: dict[str, Any]) -> str:
    """Parent/guardian email from a student-roster pass-through column."""
    mapped = (row.get("parent_email") or row.get("guardian_email") or "").strip()
    if mapped:
        return mapped
    for key, value in row.items():
        if not isinstance(key, str):
            continue
        m = re.match(r"^(?:custom_fields|_unmapped)\.(.+)$", key)
        if not m:
            continue
        col = m.group(1)
        if not _GUARDIAN_NAME_HINT_RE.search(col):
            continue
        if not re.search(r"(email|mail)", col, re.IGNORECASE):
            continue
        v = str(value).strip() if value is not None else ""
        if v.lower() in _HINT_NULL_LITERALS:
            continue
        return v
    return ""


def _link_student_guardian_hint(obj, row: dict[str, Any], ctx, result) -> None:
    """Persist the roster parent name as a student-scoped hint AND promote it
    into the live Guardian directory (``StudentGuardian`` + PARENT user).

    Login stays consent-first: the account is created with an UNUSABLE password.
    Activation is invite or a handed one-time password after apply — never a
    credential minted here. The DFV hint is kept so the claim UX can still show
    the source name. Best-effort; never raises/quarantines."""
    name, phone = _extract_guardian_hint(row)
    phone = phone or (row.get("parent_phone") or "").strip()
    email = _extract_guardian_email(row)
    extras: dict[str, Any] = {}
    if name:
        extras["parent_name"] = name[:120]
    if phone:
        extras["parent_phone"] = phone[:40]
    if extras:
        persist_dfv_extras(
            ctx=ctx, entity_type="student", entity_id=obj.pk, extras=extras, result=result,
        )
    if not (name or phone or email):
        return
    try:
        from apps.migration_cloud.guardian_directory import promote_guardian_directory_link

        promote_guardian_directory_link(
            student=obj,
            name=name,
            phone=phone,
            email=email,
            school=getattr(ctx, "school", None),
            dry_run=bool(getattr(ctx, "dry_run", False)),
        )
    except Exception:  # noqa: BLE001 — directory promote must not quarantine the student
        if result is not None:
            record_row_note(
                result,
                f"guardian directory promote failed for student {getattr(obj, 'pk', '?')}",
            )


# Cap on how many still-unmapped columns are folded into one student's
# custom_attributes — guards against a pathologically wide roster bloating the
# JSON blob. A real roster carries far fewer than this.
_CUSTOM_ATTR_MAX_KEYS = 60
_CUSTOM_ATTR_KEY_CAP = 120
_CUSTOM_ATTR_VALUE_CAP = 500
_CUSTOM_FIELD_KEY_RE = re.compile(r"^(?:custom_fields|_unmapped)\.(.+)$")
_CUSTOM_ATTR_NULL_LITERALS = frozenset({"", "none", "nan", "n/a", "na", "null", "-"})


def _sweep_custom_attributes(obj, row: dict[str, Any], model_fields, result) -> None:
    """Fold every still-unmapped roster column into ``StudentProfile.custom_attributes``.

    Columns with no canonical home arrive on the row as ``custom_fields.<slug>``
    (below-threshold) or ``_unmapped.<col>`` (no candidate). Inside a students
    artifact only THIS lander runs, so those keys would otherwise never be
    persisted — the row would land with its first-class fields but silently drop
    its custom columns. Writing them to the student's own ``custom_attributes``
    JSON keeps the no-data-loss invariant AND keeps the values joined to the
    student (queryable in reports/exports), unlike the generic DFV path that
    keys to a synthetic ``migration_artifact`` row. Best-effort; existing keys
    are preserved (incoming fills/refreshes, never wipes). Never raises."""
    if "custom_attributes" not in model_fields:
        return
    swept: dict[str, str] = {}
    for key, value in row.items():
        if not isinstance(key, str):
            continue
        m = _CUSTOM_FIELD_KEY_RE.match(key)
        if not m:
            continue
        if value is None:
            continue
        text = str(value).strip()
        if text.lower() in _CUSTOM_ATTR_NULL_LITERALS:
            continue
        swept[m.group(1)[:_CUSTOM_ATTR_KEY_CAP]] = text[:_CUSTOM_ATTR_VALUE_CAP]
        if len(swept) >= _CUSTOM_ATTR_MAX_KEYS:
            break
    if not swept:
        return
    try:
        current = dict(getattr(obj, "custom_attributes", None) or {})
        changed = False
        for k, v in swept.items():
            if current.get(k) != v:
                current[k] = v
                changed = True
        if not changed:
            return
        with row_savepoint():
            obj.custom_attributes = current
            # save_scoped: custom_attributes feed the dynamic-field map that
            # build_student_search_index folds in, so a bare
            # update_fields=["custom_attributes"] left every swept column unsearchable.
            save_scoped(obj, ["custom_attributes"])
    except Exception:  # noqa: BLE001 — enrichment is best-effort; student already landed
        if result is not None:
            record_row_note(
                result,
                f"custom_attributes sweep failed for student {getattr(obj, 'pk', '?')}",
            )


def _surface_dedup_candidates(model, new_obj, row: dict[str, Any], ctx: "LanderContext") -> None:
    """After creating a new student, scan for likely duplicates and flag them.

    Cheap deterministic scoring runs first (always); the AI bridge is asked
    only in the ambiguous 0.55–0.92 band. Findings are written to the
    bundle's ``mapping_summary['dedup_candidates']`` for operator review.
    """
    try:
        from apps.people.ai_dedup import deterministic_score, propose_match
    except Exception:  # noqa: BLE001
        return

    try:
        from apps.migration_cloud.models import MigrationBundle
        bundle = MigrationBundle.objects.filter(pk=ctx.bundle_id).first()  # tenant-isolation-allow: PK lookup by internal bundle id
    except Exception:  # noqa: BLE001
        bundle = None
    if bundle is None:
        return

    last = (row.get("last_name") or "").strip()
    if not last:
        return

    candidates_qs = model.objects.exclude(pk=new_obj.pk)
    if "last_name" in {f.name for f in model._meta.get_fields()}:
        candidates_qs = candidates_qs.filter(last_name__iexact=last)
    candidates = list(candidates_qs[:5])

    findings: list[dict[str, Any]] = []
    for other in candidates:
        left = {f: row.get(f) for f in ("first_name", "last_name", "middle_name", "date_of_birth", "phone", "email")}
        right = {
            "first_name": getattr(other, "first_name", ""),
            "last_name": getattr(other, "last_name", ""),
            "middle_name": getattr(other, "middle_name", ""),
            "date_of_birth": getattr(other, "date_of_birth", None),
            "phone": getattr(other, "phone", ""),
            "email": getattr(other, "email", ""),
        }
        det = deterministic_score(left, right)
        finding: dict[str, Any] = {
            "new_pk": new_obj.pk,
            "other_pk": other.pk,
            "deterministic_score": det,
        }
        if 0.55 <= det <= 0.92:
            proposal = propose_match(school=getattr(bundle, "school", None), left=left, right=right)
            if proposal is not None:
                finding.update({
                    "ai_same_person": proposal.same_person,
                    "ai_confidence": proposal.confidence,
                    "ai_reasoning": proposal.reasoning,
                })
        if det >= 0.55:
            findings.append(finding)

    if not findings:
        return
    summary = dict(bundle.mapping_summary or {})
    summary.setdefault("dedup_candidates", []).extend(findings)
    bundle.mapping_summary = summary
    bundle.save(update_fields=["mapping_summary"])


_IDENTITY_KEY_FIELDS = (
    "external_id",
    "sis_external_id",
    "source_id",
    "student_code",
    "admission_number",
)


def _find_fuzzy_duplicate(model, school_scope, row, model_fields):
    """Return ``(existing_obj, score)`` for an UNAMBIGUOUS high-confidence
    name+DOB duplicate of ``row`` whose source key missed, else ``None``.

    Three rules make an auto-link unable to wrong-merge two distinct people:
      * date-of-birth must be present on the incoming row AND matched exactly
        (a shared exact birthdate is the strong discriminator);
      * the deterministic name+DOB score must clear the configurable
        ``migration_cloud.dedup.autolink_min_score`` floor;
      * exactly ONE candidate may clear the bar — 0 candidates → create a fresh
        row, >1 → ambiguous, both cases left to the post-hoc ``dedup_candidates``
        review lane rather than risking a merge.
    """
    dob = row.get("date_of_birth")
    first = (row.get("first_name") or "").strip()
    last = (row.get("last_name") or "").strip()
    if not dob or not first or not last:
        return None
    if "date_of_birth" not in model_fields or "last_name" not in model_fields:
        return None
    try:
        from apps.people.ai_dedup import deterministic_score
    except Exception:  # noqa: BLE001 — dedup helper absent → no auto-link
        return None
    from apps.migration_cloud import defaults as mc_defaults

    try:
        min_score = float(mc_defaults.get("migration_cloud.dedup.autolink_min_score"))
    except Exception:  # noqa: BLE001 — unknown/blank key → conservative default
        min_score = 0.95
    candidates = list(
        model.objects.filter(  # tenant-isolation-allow: lander runs inside schema_context(bundle.schema_name); scoped by school_scope
            **school_scope,
            last_name__iexact=last,
            date_of_birth=dob,
        )[:10]
    )
    hits = []
    for other in candidates:
        left = {
            f: row.get(f)
            for f in ("first_name", "last_name", "middle_name", "date_of_birth", "phone", "email")
        }
        right = {
            "first_name": getattr(other, "first_name", ""),
            "last_name": getattr(other, "last_name", ""),
            "middle_name": getattr(other, "middle_name", ""),
            "date_of_birth": getattr(other, "date_of_birth", None),
            "phone": getattr(other, "phone", ""),
            "email": getattr(other, "email", ""),
        }
        score = deterministic_score(left, right)
        if score >= min_score:
            hits.append((other, score))
    if len(hits) == 1:
        return hits[0]
    return None


def _record_fuzzy_link(ctx, existing_obj, external_id, score, row) -> None:
    """Note (for operator review) that an incoming source key was linked to an
    existing student via a fuzzy name+DOB match rather than the source key —
    so the auto-link is never silent. Best-effort; never breaks the land."""
    try:
        from apps.migration_cloud.models import MigrationBundle

        bundle = MigrationBundle.objects.filter(pk=ctx.bundle_id).first()  # tenant-isolation-allow: PK lookup by internal bundle id
    except Exception:  # noqa: BLE001
        return
    if bundle is None:
        return
    try:
        summary = dict(bundle.mapping_summary or {})
        summary.setdefault("dedup_links", []).append(
            {
                "canonical_pk": existing_obj.pk,
                "linked_external_id": external_id,
                "score": score,
                "matched_on": "name+dob",
            }
        )
        bundle.mapping_summary = summary
        bundle.save(update_fields=["mapping_summary"])
    except Exception:  # noqa: BLE001
        return


def _lookup_field(canonical: str, available: set[str]) -> str:
    """Map a canonical field name to the tenant model's actual column name.

    Different model versions may use ``external_id`` or ``sis_external_id`` or
    ``source_id``. Picks the first available match; falls back to the
    canonical name so the caller sees a clean error if no candidate exists.
    """
    candidates = {
        # Prefer student_code on RunMyCampus StudentProfile — it is the stable
        # SIS key. admission_number is a separate unique column and must not be
        # the sole upsert key when the CSV also sends a different adm number.
        "external_id": (
            "external_id",
            "sis_external_id",
            "source_id",
            "student_code",
            "admission_number",
        ),
    }.get(canonical, (canonical,))
    for c in candidates:
        if c in available:
            return c
    return canonical


register("students", StudentLander())

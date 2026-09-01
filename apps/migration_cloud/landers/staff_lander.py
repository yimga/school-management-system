"""Staff lander — persists canonical staff rows into ``apps.people.TeacherProfile``.

Completeness fix (2026-07-11): the old lander wrote ``first_name``/``last_name``/
``email``/``role`` straight onto ``TeacherProfile`` (those live on ``User``, not
the profile), keyed the upsert on ``staff_external_id`` (not a real field →
``FieldError``), and NEVER set the REQUIRED ``TeacherProfile.user`` OneToOne
(→ ``IntegrityError``). Every staff/teacher row therefore quarantined and the
imported count was pinned to 0 — the same class already fixed for guardians.

The lander now RESOLVES-or-PROVISIONS the staff ``User`` (workbook ``role``
mapped onto ``User.Role`` — bursar/HOD/admin/… — with TEACHER as the safe
fallback; SUPERADMIN is never granted). Password stays unusable so activation
rides invite/reset. Then it creates the
``TeacherProfile(user=…, school=…, staff_id=external_id)`` keyed on the OneToOne
user. Real profile fields (``staff_id``/``position_title``/``phone``/
``department`` FK) are written; source-only columns (``hire_date``, the raw
``role`` string) land on the DynamicFieldValue engine so nothing is lost.

Canonical row shape::

    {
        "staff_external_id": "EMP-021",
        "first_name": "Jane", "last_name": "Doe",
        "email": "jane@example.com",
        "staff_user_ref": "jane.doe",     # internal transfers only
        "role": "Teacher", "department": "Science",
        "phone": "+233...", "hire_date": "2020-09-01",
    }
"""

from __future__ import annotations

import re
from typing import Any, Iterator

# Module scope, not lazy: this class is named in ``except`` tuples that guard lazy
# model imports, and a class imported inside the same ``try`` would be unbound at
# the moment the tuple is evaluated.
from django.db import DatabaseError

from ._helpers import (
    derive_external_id,
    detect_and_register_assets,
    get_or_create_named,
    mint_scoped_code,
    model_field_names,
    persist_dfv_extras,
    record_id_mapping,
    record_row_error,
    record_row_note,
    resolve_canonical_pk_by_legacy,
    resolve_or_provision_user,
    row_savepoint,
    split_name_for,
    upsert_with_conflict_detection,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register

# Canonical role SOT (Django-free module, so it is safe to import at module level
# unlike the ORM imports below). The bare "TEACHER" literal must not be inlined:
# scan_role_strings.py enforces that the token comes from here or User.Role.
from apps.platform_runtime.role_registry import ROLE_TEACHER
from apps.migration_cloud.staff_role_map import (
    ROLE_FORBIDDEN,
    apply_imported_staff_role,
    resolve_staff_role,
    unresolvable_staff_role,
)
from .reason_codes import INVALID_REF, LANDER_ERROR, MISSING_REQUIRED

# OneRoster/SIS role tokens that must NEVER be provisioned as teachers.
_NON_STAFF_ROLES = {"student", "guardian", "parent", "relative"}
_CUSTOM_ATTR_MAX_KEYS = 60  # magic-number-allow: staff-custom-attributes-key-ceiling
_CUSTOM_ATTR_KEY_CAP = 120  # magic-number-allow: staff-custom-attributes-key-length
_CUSTOM_ATTR_VALUE_CAP = 500  # magic-number-allow: staff-custom-attributes-value-length
_CUSTOM_FIELD_KEY_RE = re.compile(r"^(?:custom_fields|_unmapped)\.(.+)$")
_CUSTOM_ATTR_NULL_LITERALS = frozenset({"", "none", "nan", "n/a", "na", "null", "-"})


def _compact_header(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (raw or "").lower())


def _staff_field_from_row(row: dict[str, Any], field: str) -> str:
    """Canonical value, or a leftover column whose header is a known synonym."""
    direct = str(row.get(field) or "").strip()
    if direct:
        return direct
    try:
        from apps.migration_cloud.ontology import all_synonyms

        wanted = {_compact_header(field)}
        wanted.update(_compact_header(s) for s in all_synonyms(field, domain="staff"))
    except Exception:  # noqa: BLE001
        wanted = {_compact_header(field)}
    for key, value in row.items():
        if not isinstance(key, str):
            continue
        m = _CUSTOM_FIELD_KEY_RE.match(key)
        label = m.group(1) if m else key
        if _compact_header(label) not in wanted:
            continue
        text = str(value or "").strip()
        if text and text.lower() not in _CUSTOM_ATTR_NULL_LITERALS:
            return text
    return ""


def _sweep_custom_attributes(obj, row: dict[str, Any], model_fields, result) -> None:
    """Fold leftover staff columns into ``TeacherProfile.custom_attributes``."""
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
            obj.save(update_fields=["custom_attributes"])
    except Exception:  # noqa: BLE001 — enrichment is best-effort; staff already landed
        if result is not None:
            record_row_note(
                result,
                f"custom_attributes sweep failed for staff {getattr(obj, 'pk', '?')}",
            )


class StaffLander(Lander):
    domain = "staff"
    sweeps_custom_columns = True

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from django.contrib.auth import get_user_model

            from apps.academics.models import Department
            from apps.people.models import TeacherProfile
        except ImportError as exc:
            raise LanderError(f"StaffLander could not import TeacherProfile: {exc!s}") from exc
        User = get_user_model()

        result = LanderResult()
        model_fields = model_field_names(TeacherProfile)
        # Prefer the ORM-layer SOT (User.Role TextChoices); fall back to the
        # registry constant if a swapped user model has no Role enum. Mirrors
        # guardian_lander's hasattr idiom -- neither branch inlines the token.
        default_staff_role = User.Role.TEACHER if hasattr(User, "Role") else ROLE_TEACHER
        # Role-decision tally. Every row lands in EXACTLY ONE bucket and the
        # buckets sum to rows_total -- a partial tally would be worse than none
        # here, because a row that took the default and a row whose label we
        # actually read otherwise wear the same shape from the outside.
        role_tally = {
            "role_mapped": 0,
            "role_defaulted_blank": 0,
            "role_held_unmapped": 0,
            "role_held_forbidden": 0,
            "role_skipped_non_staff": 0,
            "role_not_evaluated": 0,
        }
        rows_total = 0

        for row in canonical_rows:
            rows_total += 1
            external_id = (
                row.get("staff_external_id")
                or row.get("external_id")
                or row.get("employee_id")
                or ""
            ).strip()
            first_name = (row.get("first_name") or "").strip()
            last_name = (row.get("last_name") or "").strip()
            # Combined-name fallback (mirrors student_lander): a single
            # "Name"/"NAME" staff column is split locale-aware into first/last
            # so a teacher roster with no separate given/family columns is not
            # quarantined for "missing name".
            full_name = (row.get("full_name") or "").strip()
            if full_name and (not first_name or not last_name):
                fn, _mn, ln = split_name_for(ctx, full_name)
                first_name = first_name or fn
                last_name = last_name or ln
            email = (row.get("email") or "").strip()
            user_ref = (row.get("staff_user_ref") or "").strip()
            # A teacher roster off a payroll sheet or a printed staff list carries
            # no employee id. Derive a stable one so the row lands and re-applies
            # idempotently, exactly as for students.
            if not external_id and (first_name or last_name):
                external_id = derive_external_id(
                    first_name=first_name,
                    last_name=last_name,
                    date_of_birth=row.get("date_of_birth"),
                    place_of_birth=row.get("place_of_birth"),
                    prefix="auto-staff",
                )
            if not external_id or not (first_name or last_name or user_ref or email):
                # Rejected before the role cell is read -- no role decision was
                # made, which is its own answer and needs its own bucket.
                role_tally["role_not_evaluated"] += 1
                record_row_error(
                    result,
                    row,
                    f"Missing required staff fields in row {row!r}",
                    reason_code=MISSING_REQUIRED,
                )
                continue

            # Role gate: a combined OneRoster ``users.csv`` is pre-classified to
            # ``staff`` but carries every role. NEVER provision a student/parent/
            # guardian as a teacher — skip them here (they land via their own
            # domain). Blank/teacher/admin/aide/proctor roles fall through.
            role_label = _staff_field_from_row(row, "role")
            role_raw = role_label.strip().lower()
            if role_raw in _NON_STAFF_ROLES:
                role_tally["role_skipped_non_staff"] += 1
                result.skipped += 1
                continue
            # Deny-All on a privilege we could not read. A label that mapped
            # to nothing used to collapse onto default_staff_role (TEACHER),
            # and TEACHER is NOT inert: the post_save in apps/accounts/
            # signals.py attaches the TEACHER AccessRole, whose seeded codes
            # include attendance.manage and grades.enter. So a 'Canteen
            # Vendor' or 'Bus Driver' row was provisioned as a school-wide
            # attendance and grade-audit reader -- and is_staff_setup_role
            # then let them activate that account themselves. Hold the row:
            # no user, no membership, no profile. record_row_error keeps the
            # source row so it replays once someone maps the label, and the
            # loop continues, so one unreadable title cannot stall an import.
            role_problem = unresolvable_staff_role(role_label)
            if role_problem is not None:
                role_tally[
                    "role_held_forbidden"
                    if role_problem == ROLE_FORBIDDEN
                    else "role_held_unmapped"
                ] += 1
                record_row_error(
                    result,
                    row,
                    f"staff {external_id}: source role {role_label!r} is not a"
                    f" role this system can grant ({role_problem}); held for"
                    " review rather than provisioned with default access",
                    reason_code=INVALID_REF,
                    field="role",
                )
                continue
            staff_role = resolve_staff_role(
                role_label, default=default_staff_role
            )
            # A BLANK role cell keeps flowing to the caller's default, on
            # purpose: holding a payroll export that simply has no role column
            # would be worse than the disease. But the default is TEACHER and
            # TEACHER is a privilege grant, so a 400-row role-less sheet mints
            # 400 teachers with nothing on screen saying so. Count it.
            if role_label.strip():
                role_tally["role_mapped"] += 1
            else:
                role_tally["role_defaulted_blank"] += 1

            if ctx.dry_run:
                result.created += 1
                continue

            try:
                # Exact employee-number dedup (strongest signal, runs FIRST): a
                # TeacherProfile already carrying this staff_id in THIS school is
                # the same person, so reuse its user and let the upsert update in
                # place — instead of provisioning a DUPLICATE account when the
                # same staffer re-appears under a different / absent email.
                # staff_id is the source SIS's stable identity key (not an
                # ambiguous shared signal like a household phone), so an exact
                # single match is a safe auto-merge.
                teacher_user = _match_staff_user_by_staff_id(
                    TeacherProfile, ctx.school, external_id
                )
                if teacher_user is not None:
                    if not _resolution_would_reach(teacher_user, user_ref, email):
                        # The strong-key match linked a user that username/email
                        # would NOT have reached (a re-import under a different /
                        # absent email) — surface it so the auto-link is never
                        # silent.
                        _record_staff_dedup_link(ctx, teacher_user, external_id, email)
                else:
                    teacher_user, reason = resolve_or_provision_user(
                        User=User,
                        username_hint=user_ref,
                        email=email,
                        first_name=first_name,
                        last_name=last_name,
                        role=staff_role,
                        dry_run=ctx.dry_run,
                        school=ctx.school,
                    )
                    if teacher_user is None:
                        record_row_error(
                            result,
                            row,
                            f"staff {external_id}: {reason or 'no linkable user'}",
                            reason_code=INVALID_REF,
                        )
                        continue

                # Optional Department FK (SET_NULL) — reuse an existing one by
                # (school, name); mint a target-scoped code on create so we never
                # reuse the source's globally-unique department code.
                department = None
                dept_name = _staff_field_from_row(row, "department")
                if dept_name and "department" in model_fields:
                    department, _ = get_or_create_named(
                        model=Department,
                        school=ctx.school,
                        name=dept_name,
                        create_kwargs=lambda dn=dept_name: {
                            "code": mint_scoped_code(
                                prefix="DPT", name=dn, school=ctx.school, model=Department
                            )
                        },
                        result=result,
                    )

                defaults: dict[str, Any] = {
                    "staff_id": external_id,
                    "position_title": role_label[:120],  # magic-number-allow: position_title CharField max_length
                    "phone": _staff_field_from_row(row, "phone")[:50],
                    "department": department,
                }
                if "school" in model_fields and ctx.school is not None:
                    defaults["school"] = ctx.school
                defaults = {k: v for k, v in defaults.items() if k in model_fields and v not in (None, "")}

                obj, created, preserved = upsert_with_conflict_detection(
                    ctx=ctx, domain="staff", model=TeacherProfile,
                    lookup={"user": teacher_user}, defaults=defaults,
                    legacy_id=external_id,
                )
                if preserved:
                    # Operator resolved this staff conflict as PRESERVE.
                    result.skipped += 1
                    record_id_mapping(ctx=ctx, legacy_id=external_id, canonical_obj=obj, domain="staff")
                    continue
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                    result.updated_ids_with_old_values.append(
                        {"pk": obj.pk, "old": {k: getattr(obj, k, None) for k in defaults}}
                    )
                # Source-only columns with no TeacherProfile home → DFV (no data loss).
                persist_dfv_extras(
                    ctx=ctx, entity_type="staff", entity_id=obj.pk,
                    extras={"hire_date": _staff_field_from_row(row, "hire_date"),
                            "source_role": role_label},
                    result=result,
                )
                _sweep_custom_attributes(obj, row, model_fields, result)
                record_id_mapping(ctx=ctx, legacy_id=external_id, canonical_obj=obj, domain="staff")
                detect_and_register_assets(ctx=ctx, legacy_id=external_id, entity_kind="staff", row=row)
                # G8: a teacher row often carries the SOURCE system's cross-refs as
                # underscore id-lists (SUBJECTS="96_98_106", CLASSROOMS="12_15").
                # Preserve them verbatim (no data loss) AND resolve them to canonical
                # names via the id-mapping layer where those entities landed.
                _link_teacher_teaching_hints(obj, row, ctx, result)
                try:
                    apply_imported_staff_role(
                        user=teacher_user,
                        school=ctx.school,
                        role=staff_role,
                    )
                except Exception:  # noqa: BLE001 — membership is additive; staff already landed
                    if result is not None:
                        record_row_note(result, f"staff membership attach failed for {external_id}")
            except Exception as exc:  # noqa: BLE001
                record_row_error(
                    result,
                    row,
                    f"staff upsert failed for {external_id}: {type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
        _record_staff_role_disposition(
            ctx,
            role_tally,
            rows_total=rows_total,
            default_token=str(default_staff_role),
        )
        return result


# A teacher roster carries teaching cross-refs as underscore/comma id-lists under
# a SUBJECTS / CLASSROOMS-ish column. Match the column NAME.
_SUBJECTS_COL_RE = re.compile(r"subject", re.IGNORECASE)
_CLASSROOMS_COL_RE = re.compile(r"class", re.IGNORECASE)
_ID_LIST_SPLIT_RE = re.compile(r"[\s_,;|/]+")
_ID_LIST_NULLS = frozenset({"", "none", "nan", "n/a", "na", "null", "-"})


def _split_id_list(value: Any) -> list[str]:
    """Split a source id-list ('96_98_106_229_' / '12, 15') into clean ids."""
    parts = _ID_LIST_SPLIT_RE.split(str(value or "").strip())
    return [p for p in parts if p and p.lower() not in _ID_LIST_NULLS]


def _extract_teacher_id_lists(row: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return ``(subject_ids, classroom_ids)`` from a teacher roster's pass-through
    columns (``custom_fields.*`` / ``_unmapped.*``). Match on column NAME."""
    subject_ids: list[str] = []
    classroom_ids: list[str] = []
    for key, value in row.items():
        if not isinstance(key, str):
            continue
        m = re.match(r"^(?:custom_fields|_unmapped)\.(.+)$", key)
        if not m:
            continue
        col = m.group(1)
        ids = _split_id_list(value)
        if not ids:
            continue
        if _SUBJECTS_COL_RE.search(col):
            subject_ids.extend(ids)
        elif _CLASSROOMS_COL_RE.search(col):
            classroom_ids.extend(ids)
    return subject_ids, classroom_ids


def _resolve_names(ctx, ids: list[str], domain: str, model) -> list[str]:
    """Resolve source legacy ids to canonical row names via the id-mapping layer.
    Unresolved ids are skipped here (kept verbatim in ``source_*`` extras)."""
    names: list[str] = []
    for legacy_id in ids:
        pk = resolve_canonical_pk_by_legacy(ctx=ctx, legacy_id=legacy_id, domain=domain)
        if not pk:
            continue
        try:
            obj = model.objects.filter(pk=pk).first()  # tenant-isolation-allow: pk resolved from school-scoped id-mapping
        except Exception:  # noqa: BLE001
            obj = None
        name = getattr(obj, "name", None) if obj is not None else None
        if name:
            names.append(str(name))
    return names


def _link_teacher_teaching_hints(obj, row: dict[str, Any], ctx, result) -> None:
    """Preserve a teacher's SUBJECTS/CLASSROOMS id-lists and resolve them to names.

    The raw id-lists are always kept (``source_subject_ids`` / ``source_classroom_ids``)
    so nothing is lost. Where the referenced subjects/classrooms LANDED in this same
    migration (and recorded a ``MigrationIdMapping``), the ids resolve to canonical
    NAMES (``teaching_subjects`` / ``teaching_classrooms``) an admin can read and turn
    into real assignments. We do NOT auto-create SubjectAssignments from the id-lists:
    a class holds students of several specialties, so the (classroom, specialty) a
    ``SubjectAssignment`` needs is genuinely ambiguous from a teacher roster — that
    stays an explicit admin/teacher step. Best-effort; never raises/quarantines."""
    subject_ids, classroom_ids = _extract_teacher_id_lists(row)
    if not subject_ids and not classroom_ids:
        return
    extras: dict[str, Any] = {}
    if subject_ids:
        extras["source_subject_ids"] = ", ".join(subject_ids)[:500]
    if classroom_ids:
        extras["source_classroom_ids"] = ", ".join(classroom_ids)[:500]
    try:
        from apps.academics.models import Classroom, Subject

        subj_names = _resolve_names(ctx, subject_ids, "academics", Subject)
        class_names = _resolve_names(ctx, classroom_ids, "sections", Classroom)
        if not class_names:
            # Classrooms may have landed under the structure lander's namespace.
            class_names = _resolve_names(ctx, classroom_ids, "structure", Classroom)
        if subj_names:
            extras["teaching_subjects"] = ", ".join(subj_names)[:500]
        if class_names:
            extras["teaching_classrooms"] = ", ".join(class_names)[:500]
    except Exception:  # noqa: BLE001 — resolution is best-effort; raw ids already preserved
        pass
    persist_dfv_extras(
        ctx=ctx, entity_type="staff", entity_id=obj.pk, extras=extras, result=result,
    )


def _match_staff_user_by_staff_id(TeacherProfile, school: Any, external_id: str):
    """Exact employee-number dedup: return the ``User`` of an existing
    ``TeacherProfile`` in THIS school carrying this ``staff_id``, else ``None``.

    ``staff_id`` is the source SIS's stable identity key for the record (not an
    ambiguous shared signal like a household phone), so an exact match is a safe
    auto-merge. Guardrailed so it can never wrong-merge:
      * ``staff_id`` must be present AND matched exactly;
      * scoped to the bundle's school (never reaches across tenants);
      * exactly ONE distinct user may match — legacy duplicate data (>1 profile
        sharing a staff_id) is ambiguous, so don't guess; fall through to the
        normal username/email resolution and let the merge engine reconcile.
    """
    external_id = (external_id or "").strip()
    if not external_id:
        return None
    scope: dict[str, Any] = {}
    if school is not None:
        scope["school"] = school
    profiles = TeacherProfile.objects.filter(  # tenant-isolation-allow: lander runs inside schema_context; scoped by school kwarg
        staff_id=external_id, **scope,
    ).select_related("user")[:5]
    matched: dict[Any, Any] = {}
    for tp in profiles:
        u = getattr(tp, "user", None)
        if u is not None:
            matched[u.pk] = u
    if len(matched) == 1:
        return next(iter(matched.values()))
    return None


def _resolution_would_reach(user, user_ref: str, email: str) -> bool:
    """True when the normal username/email resolution would have reached THIS
    user anyway — so the staff_id auto-link is only surfaced (as a dedup link)
    when it actually prevented a different / duplicate resolution."""
    if user_ref and getattr(user, "username", "") == user_ref:
        return True
    if email and (getattr(user, "email", "") or "").strip().lower() == email.strip().lower():
        return True
    return False


def _record_staff_dedup_link(ctx, user, external_id: str, email: str) -> None:
    """Note (for operator review) that an incoming staff row was linked to an
    existing teacher account by EXACT staff_id rather than by email/username —
    so the auto-link is never silent. Best-effort; never breaks the land."""
    bundle_id = getattr(ctx, "bundle_id", None)
    if bundle_id is None:
        return
    try:
        from apps.migration_cloud.models import MigrationBundle

        bundle = MigrationBundle.objects.filter(pk=bundle_id).first()  # tenant-isolation-allow: PK lookup by internal bundle id
    except Exception:  # noqa: BLE001
        return
    if bundle is None:
        return
    try:
        summary = dict(bundle.mapping_summary or {})
        summary.setdefault("dedup_links", []).append(
            {
                "canonical_user_pk": user.pk,
                "linked_staff_id": external_id,
                "incoming_email": (email or "").strip(),
                "matched_on": "staff_id",
            }
        )
        bundle.mapping_summary = summary
        bundle.save(update_fields=["mapping_summary"])
    except Exception:  # noqa: BLE001
        return


def _record_staff_role_disposition(
    ctx, tally: dict[str, int], *, rows_total: int, default_token: str
) -> None:
    """Publish the role-decision tally onto the bundle's mapping_summary.

    A blank role cell still flows to the caller's default -- that behaviour is
    deliberate. What was missing is that it was SILENT: the default is TEACHER,
    TEACHER is a privilege grant (see the deny-all note in the land loop), so a
    role-less payroll import mints teachers at scale with nothing saying so.
    ``role_defaulted_blank`` is that number.

    The tally CLOSES. Every row is in exactly one bucket and the buckets sum to
    ``rows_total``; ``balanced`` publishes whether they actually did, so a new
    exit path added later without a bucket shows up as a stated discrepancy
    instead of quietly shrinking a number someone is trusting.

    Best-effort; a reporting write never breaks a lander.
    """
    bundle_id = getattr(ctx, "bundle_id", None)
    if bundle_id is None or rows_total <= 0:
        return
    try:
        from apps.migration_cloud.models import MigrationBundle

        bundle = MigrationBundle.objects.filter(pk=bundle_id).first()  # tenant-isolation-allow: PK lookup by internal bundle id
    except (ImportError, DatabaseError, TypeError, ValueError):
        # Exhaustive for these two statements: the models module may be absent
        # (ImportError); the bundle table may be missing or unreachable
        # (DatabaseError, which covers Operational/Programming/Interface); and a
        # ``bundle_id`` that is not a valid pk makes Django's IntegerField raise
        # TypeError/ValueError. A typo in this function is NOT in that list.
        return
    if bundle is None:
        return
    try:
        summary = dict(bundle.mapping_summary or {})
        merged = dict(tally)
        merged["rows_total"] = rows_total
        prior = summary.get("staff_role_disposition")
        if isinstance(prior, dict):
            # A bundle can land staff across several artifacts. Accumulate so
            # the published number is the BUNDLE's, not the last artifact's.
            for key in list(merged):
                was = prior.get(key)
                if isinstance(was, int) and not isinstance(was, bool):
                    merged[key] += was
        counted = sum(merged[key] for key in tally)
        merged["default_token"] = default_token
        merged["balanced"] = counted == merged["rows_total"]
        if not merged["balanced"]:
            merged["unaccounted"] = merged["rows_total"] - counted
        summary["staff_role_disposition"] = merged
        bundle.mapping_summary = summary
        bundle.save(update_fields=["mapping_summary"])
    except (DatabaseError, TypeError, ValueError):
        # The block does exactly three kinds of thing. ``dict(...)`` over a JSON
        # column whose stored value is not a mapping raises TypeError/ValueError;
        # the arithmetic runs only on isinstance-checked ints, so TypeError is its
        # worst case; the write raises DatabaseError. Losing the disposition is
        # survivable -- the staff rows already landed -- but losing a NameError
        # here is not, because this reporting write is the only thing that says a
        # role-less payroll import minted teachers at scale.
        return


register("staff", StaffLander())

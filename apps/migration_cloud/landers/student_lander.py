"""Student lander — persists canonical student rows into ``apps.people.StudentProfile``.

Upsert keyed on ``external_id`` (the source-system identifier) — the
single most-asked-for property of any migration ("re-running the bundle
must not create duplicate students").
"""

from __future__ import annotations

import re
from typing import Any, Iterator

from ._helpers import (
    _jsonable,
    conflict_resolution_for,
    detect_and_register_assets,
    detect_conflict,
    map_enrollment_status,
    persist_dfv_extras,
    record_id_mapping,
    row_savepoint,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


class StudentLander(Lander):
    domain = "students"

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
            external_id = (row.get("external_id") or "").strip()
            first_name = (row.get("first_name") or "").strip()
            last_name = (row.get("last_name") or "").strip()
            middle_name = (row.get("middle_name") or "").strip()
            # Combined-name fallback: many real exports (African / French-model
            # SIS) carry ONE "Name"/"NAME" column, not separate given/family
            # columns. When the source has no first/last, split the canonical
            # ``full_name`` locale-aware so the row is NOT quarantined for
            # "missing first/last" — historically the single biggest real-world
            # data-loss cause on these rosters (0/426 students landed).
            full_name = (row.get("full_name") or "").strip()
            if full_name and (not first_name or not last_name):
                from apps.migration_cloud.transformers.name_split import split_full_name

                country = getattr(ctx.school, "country_code", "") if ctx.school else ""
                fn, mn, ln = split_full_name(full_name, country=country)
                first_name = first_name or fn
                last_name = last_name or ln
                middle_name = middle_name or mn
            if not external_id or not first_name or not last_name:
                result.quarantined += 1
                result.errors.append(
                    f"Missing required fields (external_id/first/last) in row {row!r}"
                )
                continue

            # Canonical enrollment_status is a lifecycle token; StudentProfile
            # stores it on ``status`` (a constrained choice), NOT a field named
            # ``enrollment_status`` — writing that key silently dropped the state.
            mapped_status = map_enrollment_status(row.get("enrollment_status"))
            defaults = {
                "first_name": first_name,
                "last_name": last_name,
                "middle_name": middle_name,
                "admission_number": (row.get("admission_number") or "").strip(),
                "email": (row.get("email") or "").strip(),
                "phone": (row.get("phone") or "").strip(),
                "date_of_birth": row.get("date_of_birth") or None,
                "gender": (row.get("gender") or "").strip(),
                "grade_level": (row.get("grade_level") or "").strip(),
                "status": mapped_status,
                "address": (row.get("address") or "").strip(),
            }
            # Filter to fields the model actually has, to be schema-tolerant.
            model_fields = {f.name for f in StudentProfile._meta.get_fields()}
            # Canonical columns this tenant's StudentProfile doesn't model
            # (middle_name/email/phone/grade_level/address vary by deployment) —
            # preserved as custom fields after the upsert so no source data is
            # silently dropped. The raw enrollment_status token is kept too.
            extras = {
                "middle_name": middle_name,
                "email": (row.get("email") or "").strip(),
                "phone": (row.get("phone") or "").strip(),
                "grade_level": (row.get("grade_level") or "").strip(),
                "address": (row.get("address") or "").strip(),
                "enrollment_status": (row.get("enrollment_status") or "").strip(),
            }
            extras = {k: v for k, v in extras.items() if k not in model_fields and v}
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
                    for k, v in apply_defaults.items():
                        setattr(existing_obj, k, v)
                    if lookup_field in model_fields and not fuzzy_linked:
                        setattr(existing_obj, lookup_field, external_id)
                    # Per-row savepoint: students land in an EARLIER wave of the same
                    # forced-atomic finance transaction, so a bad student row must roll
                    # back only itself — not poison the whole apply (see _helpers.row_savepoint).
                    with row_savepoint():
                        existing_obj.save()
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
            except Exception as exc:  # noqa: BLE001 — per-row quarantine
                result.quarantined += 1
                result.errors.append(f"upsert failed for {external_id}: {type(exc).__name__}: {exc}")
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
            obj.save(update_fields=["specialty"])
    except Exception:  # noqa: BLE001 — enrichment is best-effort; student already landed
        pass


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

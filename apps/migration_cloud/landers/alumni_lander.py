"""Alumni lander — preserves alumni records via the StudentProfile pathway.

Honest scope note: the platform has no dedicated ``Alumni`` model. The
operationally correct landing target is a ``StudentProfile`` with
``enrollment_status='graduated'`` (or 'alumni') and the canonical fields
preserved. This lander upserts those records so alumni rosters from
legacy SIS migrate as graduated students with the right status, rather
than landing as ``custom_fields`` blobs.

When the platform grows a dedicated ``AlumniProfile`` model later, swap
the import target and keep the canonical row shape intact.

Canonical row shape::

    {
        "external_id":      "AL-2018-0042",
        "first_name":       "Aisha",
        "last_name":        "Bello",
        "graduation_year":  2018,
        "email":            "aisha@example.com",
        "phone":            "+234 803 555 0100",
        "current_employer": "Lagos Tech Co.",
        "current_role":     "Senior Engineer",
    }

Upsert key: external_id. Extra fields (current_employer, current_role,
graduation_year) land on the matching StudentProfile via
``DynamicFieldValue`` so they're preserved without a schema migration.
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import (
    coerce_int,
    derive_external_id,
    detect_and_register_assets,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
    record_row_error,
    record_row_note,
    split_name_for,
    student_lookup_field,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register
from .reason_codes import LANDER_ERROR, MISSING_REQUIRED


_ALUMNI_EXTRA_KEYS = ("graduation_year", "current_employer", "current_role")


class AlumniLander(Lander):
    domain = "alumni"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.people.models import StudentProfile
        except ImportError as exc:
            raise LanderError(
                f"AlumniLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        student_fields = model_field_names(StudentProfile)
        student_lookup = student_lookup_field(student_fields)

        for row in canonical_rows:
            external_id = (row.get("external_id") or "").strip()
            first_name = (row.get("first_name") or "").strip()
            last_name = (row.get("last_name") or "").strip()
            # Combined-name fallback (mirrors student_lander / staff_lander,
            # which alumni never received): an alumni roster is the MOST likely
            # of the three to arrive as one "Name" column off a printed
            # graduation list, and without this every such row quarantined.
            full_name = (row.get("full_name") or "").strip()
            if full_name and (not first_name or not last_name):
                fn, _mn, ln = split_name_for(ctx, full_name)
                first_name = first_name or fn
                last_name = last_name or ln
            # Alumni are the least likely records to carry a source-system id --
            # they predate the SIS being migrated. Derive a stable key so the
            # roster lands and stays idempotent on re-apply.
            if not external_id:
                external_id = derive_external_id(
                    first_name=first_name,
                    last_name=last_name,
                    date_of_birth=row.get("date_of_birth"),
                    place_of_birth=row.get("place_of_birth"),
                )
            if not external_id or not first_name or not last_name:
                record_row_error(
                    result,
                    row,
                    f"alumni: missing external_id/first/last in {row!r}",
                    reason_code=MISSING_REQUIRED,
                )
                continue

            grad_year = coerce_int(row.get("graduation_year"))
            defaults: dict[str, Any] = {
                "first_name": first_name[:64],
                "last_name": last_name[:64],
                "email": (row.get("email") or "")[:255],
                "phone": (row.get("phone") or "")[:32],
                # Real field + real choice: alumni land as ALUMNI-status students.
                # The model has no ``enrollment_status`` column — that phantom key
                # was dropped by filter_to_model_fields, so status was NEVER set
                # and alumni were indistinguishable from active students.
                "status": StudentProfile.Status.ALUMNI,
            }
            if grad_year and "graduation_year" in student_fields:
                defaults["graduation_year"] = grad_year
            defaults = filter_to_model_fields(defaults, StudentProfile)

            # School-scope the upsert: on single-schema / sqlite deployments an
            # unscoped external-id (admission_number) can resolve a same-id
            # student from ANOTHER school. Scope both the conflict probe and the
            # create when the model carries a school column.
            lookup_kwargs: dict[str, Any] = {student_lookup: external_id}
            if "school" in student_fields and ctx.school is not None:
                lookup_kwargs["school"] = ctx.school

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = StudentProfile.objects.filter(**lookup_kwargs).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                from ._helpers import upsert_with_conflict_detection
                obj, created, preserved = upsert_with_conflict_detection(
                    ctx=ctx, domain="alumni", model=StudentProfile,
                    lookup=lookup_kwargs, defaults=defaults, legacy_id=external_id,
                )
                if preserved:
                    result.skipped += 1
                    record_id_mapping(ctx=ctx, legacy_id=external_id, canonical_obj=obj, domain="alumni")
                    continue
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                    result.updated_ids_with_old_values.append(
                        {"pk": obj.pk, "old": {k: getattr(obj, k, None) for k in defaults}}
                    )
                record_id_mapping(
                    ctx=ctx, legacy_id=external_id,
                    canonical_obj=obj, domain="alumni",
                )
                detect_and_register_assets(
                    ctx=ctx, legacy_id=external_id, entity_kind="alumni", row=row,
                )
                # Preserve alumni-specific extras (current_employer/role/grad_year
                # if the model didn't have a column for it) via the metadata
                # DynamicFieldValue path. Best-effort, never blocks the upsert.
                _persist_alumni_extras(
                    ctx=ctx, alumni_pk=obj.pk, row=row,
                    student_fields=student_fields, result=result,
                )
            except Exception as exc:  # noqa: BLE001
                record_row_error(
                    result,
                    row,
                    f"alumni upsert failed for {external_id}: {type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
        return result


def _persist_alumni_extras(
    *,
    ctx: LanderContext,
    alumni_pk: int,
    row: dict[str, Any],
    student_fields: set[str],
    result: LanderResult,
) -> None:
    """Write alumni-only fields not present on StudentProfile to DynamicFieldValue.

    Correct DFV shape (the old writer hand-built ``definition=/object_id=/value=``
    kwargs + a ``slug=/entity_kind=`` definition — none of which are model
    fields, so every write raised and was swallowed by a bare ``except``, and
    current_employer / current_role / graduation_year NEVER persisted):

      * definition keyed by real fields (entity_type / field_key / school);
      * value keyed by (entity_type, entity_id, field_key) with the raw value
        under ``value_json={"v": value}`` and ``school`` set (NOT NULL).

    Tolerates a missing metadata app — alumni extras are nice-to-have, not
    load-bearing — but a failure is now recorded on the result, never swallowed.
    """
    try:
        from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
    except Exception as exc:  # noqa: BLE001
        record_row_note(result, f"alumni extras: metadata models unavailable: {type(exc).__name__}")
        return
    for key in _ALUMNI_EXTRA_KEYS:
        if key in student_fields:
            continue  # written directly to the model
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            DynamicFieldDefinition.objects.get_or_create(
                entity_type="student",
                field_key=key[:120],
                school=ctx.school,
                defaults={"label": f"Alumni {key}"[:255], "data_type": "json"},
            )
            # school belongs in the LOOKUP: DynamicFieldValue.unique_together is
            # [school, entity_type, entity_id, field_key] and metadata is a SHARED
            # app, so omitting it matches ANOTHER tenant's row and update_or_create
            # overwrites its value and re-parents it.
            DynamicFieldValue.objects.update_or_create(
                school=ctx.school,
                entity_type="student",
                entity_id=str(alumni_pk)[:64],
                field_key=key[:120],
                defaults=filter_to_model_fields(
                    {"value_json": {"v": str(value)[:1024]}},
                    DynamicFieldValue,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — best-effort, recorded
            record_row_note(
                result,
                f"alumni extras write failed for {key}: {type(exc).__name__}: {exc}",
            )
            continue


register("alumni", AlumniLander())

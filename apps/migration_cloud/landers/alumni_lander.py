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
    detect_and_register_assets,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
    student_lookup_field,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


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
            if not external_id or not first_name or not last_name:
                result.quarantined += 1
                result.errors.append(
                    f"alumni: missing external_id/first/last in {row!r}"
                )
                continue

            grad_year = coerce_int(row.get("graduation_year"))
            defaults: dict[str, Any] = {
                "first_name": first_name[:64],
                "last_name": last_name[:64],
                "email": (row.get("email") or "")[:255],
                "phone": (row.get("phone") or "")[:32],
                "enrollment_status": "graduated",
            }
            if grad_year and "graduation_year" in student_fields:
                defaults["graduation_year"] = grad_year
            defaults = filter_to_model_fields(defaults, StudentProfile)

            lookup_kwargs = {student_lookup: external_id}

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = StudentProfile.objects.filter(**lookup_kwargs).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                obj, created = StudentProfile.objects.update_or_create(
                    defaults=defaults, **lookup_kwargs,
                )
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
                _persist_alumni_extras(ctx=ctx, alumni_pk=obj.pk, row=row, student_fields=student_fields)
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"alumni upsert failed for {external_id}: {type(exc).__name__}: {exc}"
                )
        return result


def _persist_alumni_extras(
    *, ctx: LanderContext, alumni_pk: int, row: dict[str, Any], student_fields: set[str],
) -> None:
    """Write alumni-only fields not present on StudentProfile to DynamicFieldValue.

    Tolerates a missing metadata app — alumni extras are nice-to-have,
    not load-bearing.
    """
    try:
        from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
    except Exception:  # noqa: BLE001
        return
    for key in _ALUMNI_EXTRA_KEYS:
        if key in student_fields:
            continue  # written directly to the model
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            definition, _ = DynamicFieldDefinition.objects.get_or_create(
                slug=f"alumni_{key}",
                defaults={"label": f"Alumni {key}", "entity_kind": "student"},
            )
            DynamicFieldValue.objects.create(
                definition=definition,
                object_id=str(alumni_pk),
                value={"raw": str(value)[:1024]},
            )
        except Exception:  # noqa: BLE001
            continue


register("alumni", AlumniLander())

"""Guardian lander — persists canonical guardian rows + the student↔guardian link."""

from __future__ import annotations

from typing import Any, Iterator

from .base import Lander, LanderContext, LanderError, LanderResult, register


class GuardianLander(Lander):
    domain = "guardians"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.people.models import StudentGuardian, StudentProfile
        except ImportError as exc:
            raise LanderError(
                f"GuardianLander could not import StudentGuardian / StudentProfile: {exc!s}"
            ) from exc

        result = LanderResult()
        guardian_model_fields = {f.name for f in StudentGuardian._meta.get_fields()}
        student_model_fields = {f.name for f in StudentProfile._meta.get_fields()}

        for row in canonical_rows:
            student_external_id = (row.get("student_external_id") or "").strip()
            first_name = (row.get("first_name") or "").strip()
            last_name = (row.get("last_name") or "").strip()
            if not student_external_id or not (first_name or last_name):
                result.quarantined += 1
                result.errors.append(
                    f"Missing student_external_id or name in guardian row {row!r}"
                )
                continue

            student_lookup_field = _student_lookup(student_model_fields)
            try:
                student = StudentProfile.objects.filter(
                    **{student_lookup_field: student_external_id}
                ).first()
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"student lookup failed for {student_external_id}: {type(exc).__name__}"
                )
                continue
            if student is None:
                result.quarantined += 1
                result.errors.append(
                    f"No student with {student_lookup_field}={student_external_id!r} for guardian"
                )
                continue

            defaults = {
                "first_name": first_name,
                "last_name": last_name,
                "email": (row.get("email") or "").strip(),
                "phone": (row.get("phone") or "").strip(),
                "relationship": (row.get("relationship") or "").strip(),
                "is_primary": _truthy(row.get("is_primary")),
            }
            defaults = {k: v for k, v in defaults.items() if k in guardian_model_fields}

            if ctx.dry_run:
                result.created += 1
                continue

            try:
                obj, created = StudentGuardian.objects.update_or_create(
                    student=student,
                    email=defaults.get("email") or "",
                    last_name=defaults.get("last_name") or "",
                    defaults=defaults,
                )
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                    result.updated_ids_with_old_values.append(
                        {"pk": obj.pk, "old": {k: getattr(obj, k, None) for k in defaults}}
                    )
                from ._helpers import record_id_mapping
                record_id_mapping(
                    ctx=ctx,
                    legacy_id=f"{external_id}:{defaults.get('email', '')}",
                    canonical_obj=obj, domain="guardians",
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(f"guardian upsert failed: {type(exc).__name__}: {exc}")
        return result


def _student_lookup(available: set[str]) -> str:
    for c in ("external_id", "sis_external_id", "source_id", "admission_number"):
        if c in available:
            return c
    return "admission_number"


def _truthy(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "y", "t", "primary")


register("guardians", GuardianLander())

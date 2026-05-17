"""Staff lander — persists canonical staff rows into ``apps.people.TeacherProfile``.

Best-effort: only the universally-present fields are written. Schools
with custom HR fields land those via the ``DynamicFieldLander`` fallback
(custom_fields domain) per the no-data-loss invariant.
"""

from __future__ import annotations

from typing import Any, Iterator

from .base import Lander, LanderContext, LanderError, LanderResult, register


class StaffLander(Lander):
    domain = "staff"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.people.models import TeacherProfile
        except ImportError as exc:
            raise LanderError(f"StaffLander could not import TeacherProfile: {exc!s}") from exc

        result = LanderResult()
        model_fields = {f.name for f in TeacherProfile._meta.get_fields()}
        for row in canonical_rows:
            external_id = (row.get("staff_external_id") or "").strip()
            first_name = (row.get("first_name") or "").strip()
            last_name = (row.get("last_name") or "").strip()
            if not external_id or not first_name or not last_name:
                result.quarantined += 1
                result.errors.append(
                    f"Missing required staff fields in row {row!r}"
                )
                continue

            defaults = {
                "first_name": first_name,
                "last_name": last_name,
                "email": (row.get("email") or "").strip(),
                "role": (row.get("role") or "").strip(),
                "department": (row.get("department") or "").strip(),
                "hire_date": row.get("hire_date") or None,
            }
            defaults = {k: v for k, v in defaults.items() if k in model_fields and v not in (None, "")}

            if ctx.dry_run:
                result.created += 1
                continue

            try:
                lookup_field = _lookup_field("staff_external_id", model_fields)
                obj, created = TeacherProfile.objects.update_or_create(
                    **{lookup_field: external_id},
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
                from ._helpers import detect_and_register_assets, record_id_mapping
                record_id_mapping(ctx=ctx, legacy_id=external_id, canonical_obj=obj, domain="staff")
                detect_and_register_assets(ctx=ctx, legacy_id=external_id, entity_kind="staff", row=row)
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(f"staff upsert failed for {external_id}: {type(exc).__name__}: {exc}")
        return result


def _lookup_field(canonical: str, available: set[str]) -> str:
    for c in ("staff_external_id", "external_id", "source_id", "employee_id"):
        if c in available:
            return c
    return canonical


register("staff", StaffLander())

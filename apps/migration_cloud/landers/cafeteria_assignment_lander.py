"""Cafeteria assignment lander — persists per-student meal-plan balances.

Migration scope: the per-student side of the cafeteria catalog. The
sibling :mod:`cafeteria_lander` owns the menu / meal catalog
(``CanteenMeal``); this lander owns the row that says "student PS-1029
is on the Vegetarian Lunch plan with a 50.00 USD balance".

Target model — fallback rationale:
    The tenant ``apps.schoolops`` package does not currently ship a
    first-class ``MealPlanBalance`` / ``CafeteriaAccount`` model. Until
    one lands, this lander persists each row into
    ``apps.metadata.DynamicFieldValue`` keyed by
    ``entity_type='student_cafeteria_assignment'`` and
    ``entity_id=<student.pk>:<meal_plan_token>``. The balance is held as
    a string on ``value_json`` (NEVER ``float``) so precision survives
    until a first-class ledger model promotes these rows.

Money handling:
    ``coerce_decimal()`` is used on the balance — ``float()`` is banned
    on money paths (``scan_money_float`` zero-tolerance gate). The
    Decimal is serialised to ``str`` for JSON storage, preserving
    ledger-grade precision.

Canonical row shape::

    {
        "student_external_id": "PS-1029",
        "meal_plan":           "Vegetarian Lunch",
        "balance":             50.00,                  # Decimal-coerced
        "currency":            "USD",                  # optional
        "dietary_notes":       "vegetarian, nut-free", # optional
    }

Upsert key: ``(school, entity_type='student_cafeteria_assignment',
entity_id=f"{student.pk}:{meal_plan_token}")``.
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import (
    coerce_decimal,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
    student_lookup_field,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


_ENTITY_TYPE = "student_cafeteria_assignment"
_ENTITY_ID_LENGTH_CAP = 96
_PAYLOAD_VALUE_CAP = 128
_DIETARY_NOTES_CAP = 512
_FIELD_KEY = "payload"


class CafeteriaAssignmentLander(Lander):
    domain = "cafeteria_assignments"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.metadata.models import DynamicFieldValue
            from apps.people.models import StudentProfile
            from apps.schoolops.models import CanteenMeal
        except ImportError as exc:
            raise LanderError(
                f"CafeteriaAssignmentLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        student_fields = model_field_names(StudentProfile)
        student_lookup = student_lookup_field(student_fields)
        meal_fields = model_field_names(CanteenMeal)
        dfv_fields = model_field_names(DynamicFieldValue)
        meal_cache: dict[str, Any] = {}

        for row in canonical_rows:
            external_id = (row.get("student_external_id") or "").strip()
            meal_plan_name = (row.get("meal_plan") or "").strip()
            if not external_id or not meal_plan_name:
                result.quarantined += 1
                result.errors.append(
                    f"cafeteria_assignments: missing student/meal_plan in {row!r}"
                )
                continue

            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
            student = StudentProfile.objects.filter(
                **{student_lookup: external_id}
            ).first()
            if student is None:
                result.quarantined += 1
                result.errors.append(
                    f"cafeteria_assignments: no student with "
                    f"{student_lookup}={external_id!r}"
                )
                continue

            meal_key = (
                f"{getattr(ctx.school, 'pk', '')}:{meal_plan_name.lower()}"
            )
            meal = meal_cache.get(meal_key)
            if meal is None and meal_key not in meal_cache:
                meal_filter: dict[str, Any] = {"name": meal_plan_name[:128]}
                if "school" in meal_fields and ctx.school is not None:
                    meal_filter["school"] = ctx.school
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                meal = CanteenMeal.objects.filter(**meal_filter).first()
                meal_cache[meal_key] = meal

            meal_token = str(getattr(meal, "pk", "") or meal_plan_name)[:32]
            entity_id = f"{student.pk}:{meal_token}"[:_ENTITY_ID_LENGTH_CAP]

            balance = coerce_decimal(row.get("balance"))
            currency = (row.get("currency") or "").strip().upper()
            dietary_notes = (row.get("dietary_notes") or "").strip()

            payload: dict[str, Any] = {
                "student_external_id": external_id[:_PAYLOAD_VALUE_CAP],
                "meal_plan": meal_plan_name[:_PAYLOAD_VALUE_CAP],
            }
            if balance is not None:
                # Decimal → str preserves precision; banned-float gate stays clean.
                payload["balance"] = str(balance)
            if currency:
                payload["currency"] = currency[:8]
            if dietary_notes:
                payload["dietary_notes"] = dietary_notes[:_DIETARY_NOTES_CAP]
            if meal is not None:
                payload["meal_pk"] = meal.pk

            defaults: dict[str, Any] = {"value_json": payload}
            defaults = filter_to_model_fields(defaults, DynamicFieldValue)

            lookup_kwargs: dict[str, Any] = {
                "entity_type": _ENTITY_TYPE,
                "entity_id": entity_id,
                "field_key": _FIELD_KEY,
            }
            if "school" in dfv_fields and ctx.school is not None:
                lookup_kwargs["school"] = ctx.school

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = DynamicFieldValue.objects.filter(**lookup_kwargs).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                obj, created = DynamicFieldValue.objects.update_or_create(
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
                    ctx=ctx,
                    legacy_id=f"{external_id}:{meal_plan_name}",
                    canonical_obj=obj, domain="cafeteria_assignments",
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"cafeteria_assignments upsert failed for "
                    f"{external_id}/{meal_plan_name!r}: "
                    f"{type(exc).__name__}: {exc}"
                )
        return result


register("cafeteria_assignments", CafeteriaAssignmentLander())

"""Cafeteria assignment lander — persists per-student meal-plan balances.

Promoted v3.29.0: first-class :class:`apps.schoolops.MealPlanBalance`
when the student resolves; the meal-plan FK is optional (null = generic
canteen credit). Falls back to ``apps.metadata.DynamicFieldValue`` only
on first-class upsert failure (defensive: should not happen for valid
canonical rows). Quarantines the row only when the student itself can't
be resolved.

Money handling:
    All money fields are :class:`Decimal` end-to-end. ``coerce_decimal()``
    is used; ``float()`` is banned on money paths (``scan_money_float``
    zero-tolerance gate). On duplicate (same student + meal_plan), the
    lander UPDATES the existing balance — last-wins semantics for
    canonical bundles — and records ``last_topup_amount = max(0, new -
    old)`` plus ``last_topup_at = now()`` so the canteen UI can show a
    timeline of credit events even after consolidation.

Migration scope: the per-student side of the cafeteria catalog. The
sibling :mod:`cafeteria_lander` owns the menu / meal catalog
(``CanteenMeal``); this lander owns the row that says "student PS-1029
is on the Vegetarian Lunch plan with a 50.00 USD balance".

Canonical row shape::

    {
        "student_external_id":  "PS-1029",
        "meal_plan":            "Vegetarian Lunch",      # optional
        "balance":              50.00,                   # Decimal-coerced
        "currency":             "USD",                   # ISO 4217
        "low_balance_threshold": 5.00,                   # optional
        "status":                "active",               # optional choice
        "dietary_notes":         "vegetarian, nut-free", # informational only
    }

Upsert keys:
    * First-class path: ``(student, meal_plan)`` unique-together (a
      single balance per student per plan; meal_plan may be NULL).
    * DFV fallback path: ``(school, entity_type='student_cafeteria_assignment',
      entity_id=f"{student.pk}:{meal_plan_token}")``.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Iterator

from django.utils import timezone

from ._helpers import (
    coerce_decimal,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
    record_row_error,
    resolve_student,
    row_savepoint,
    student_lookup_field,
    student_name_from_row,
    unresolved_student_reason,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register
from .reason_codes import INVALID_REF, LANDER_ERROR, MISSING_REQUIRED


logger = logging.getLogger(__name__)

_ENTITY_TYPE = "student_cafeteria_assignment"
_ENTITY_ID_LENGTH_CAP = 96
_PAYLOAD_VALUE_CAP = 128
_DIETARY_NOTES_CAP = 512
_FIELD_KEY = "payload"
_VALID_STATUSES = ("active", "suspended", "closed")
_ZERO = Decimal("0")
_DEFAULT_THRESHOLD = Decimal("5.00")
_DEFAULT_CURRENCY = "USD"


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
            from apps.schoolops.models import CanteenMeal, MealPlanBalance
        except ImportError as exc:
            raise LanderError(
                f"CafeteriaAssignmentLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        student_fields = model_field_names(StudentProfile)
        student_lookup = student_lookup_field(student_fields)
        meal_fields = model_field_names(CanteenMeal)
        dfv_fields = model_field_names(DynamicFieldValue)
        mpb_fields = model_field_names(MealPlanBalance)
        meal_cache: dict[str, Any] = {}

        for row_index, row in enumerate(canonical_rows):
            external_id = (row.get("student_external_id") or "").strip()
            meal_plan_name = (row.get("meal_plan") or "").strip()
            # NOTE: meal_plan is optional for first-class MealPlanBalance
            # (null FK = generic credit). Only student_external_id is required.
            if not (external_id or student_name_from_row(row)):
                record_row_error(
                    result,
                    row,
                    f"cafeteria_assignments[row={row_index}]: "
                    f"missing student_external_id",
                    reason_code=MISSING_REQUIRED, field="student_external_id",
                )
                continue

            student = resolve_student(
                ctx=ctx,
                student_model=StudentProfile,
                lookup_field=student_lookup,
                external_id=external_id,
                row=row,
            )
            if student is None:
                record_row_error(
                    result,
                    row,
                    f"[row={row_index}] "
                    + unresolved_student_reason(
                        domain="cafeteria_assignments",
                        ctx=ctx,
                        student_model=StudentProfile,
                        row=row,
                        external_id=external_id,
                        lookup_field=student_lookup,
                    ),
                    reason_code=INVALID_REF,
                )
                logger.info(
                    "cafeteria_assignments quarantine row=%d reason=student_unresolved",
                    row_index,
                )
                continue

            meal = None
            if meal_plan_name:
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

            new_balance = coerce_decimal(row.get("balance"))
            if new_balance is None:
                new_balance = _ZERO
            currency = (row.get("currency") or _DEFAULT_CURRENCY).strip().upper()[:3]
            if not currency:
                currency = _DEFAULT_CURRENCY
            threshold = coerce_decimal(row.get("low_balance_threshold"))
            if threshold is None:
                threshold = _DEFAULT_THRESHOLD
            status_raw = (row.get("status") or "active").strip().lower()
            status = status_raw if status_raw in _VALID_STATUSES else "active"
            dietary_notes = (row.get("dietary_notes") or "").strip()

            # FIRST-CLASS PATH — always attempt, regardless of meal resolution.
            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = MealPlanBalance.objects.filter(
                    student=student, meal_plan=meal,
                ).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue

            try:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                existing = MealPlanBalance.objects.filter(
                    student=student, meal_plan=meal,
                ).first()
                old_balance = (
                    existing.balance if existing is not None else _ZERO
                )
                # Decimal arithmetic only — no float() anywhere on this path.
                topup_delta = new_balance - old_balance
                last_topup_amount = topup_delta if topup_delta > _ZERO else None
                last_topup_at = (
                    timezone.now() if last_topup_amount is not None else None
                )

                defaults: dict[str, Any] = {
                    "balance": new_balance,
                    "currency": currency,
                    "low_balance_threshold": threshold,
                    "status": status,
                }
                if last_topup_amount is not None:
                    defaults["last_topup_amount"] = last_topup_amount
                    defaults["last_topup_at"] = last_topup_at
                elif existing is None:
                    # Brand-new account: no prior balance, so any starting
                    # non-zero amount is the initial top-up.
                    if new_balance > _ZERO:
                        defaults["last_topup_amount"] = new_balance
                        defaults["last_topup_at"] = timezone.now()

                defaults = filter_to_model_fields(defaults, MealPlanBalance)

                lookup_kwargs: dict[str, Any] = {
                    "student": student,
                    "meal_plan": meal,
                }
                if "school" in mpb_fields and ctx.school is not None:
                    lookup_kwargs["school"] = ctx.school

                with row_savepoint():  # atomic-apply isolation
                    obj, created = MealPlanBalance.objects.update_or_create(
                        defaults=defaults, **lookup_kwargs,
                    )
            except (TypeError, ValueError) as exc:
                record_row_error(
                    result,
                    row,
                    f"cafeteria_assignments[row={row_index}]: "
                    f"first-class upsert input error: {type(exc).__name__}",
                    reason_code=LANDER_ERROR,
                )
                continue
            except Exception as exc:  # noqa: BLE001
                # IntegrityError / FieldError / DatabaseError — fall through
                # to DFV so the row is captured.
                logger.info(
                    "cafeteria_assignments[row=%d]: first-class upsert "
                    "raised %s; falling back to DFV",
                    row_index, type(exc).__name__,
                )
            else:
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                    result.updated_ids_with_old_values.append(
                        {"pk": obj.pk, "old": {k: getattr(obj, k, None)
                                               for k in defaults}}
                    )
                record_id_mapping(
                    ctx=ctx,
                    legacy_id=f"{external_id}:{meal_plan_name or 'generic'}",
                    canonical_obj=obj,
                    domain="cafeteria_assignments",
                )
                continue

            # FALLBACK PATH (first-class raised non-input error)
            meal_token = str(getattr(meal, "pk", "") or meal_plan_name or "generic")[:32]
            entity_id = f"{student.pk}:{meal_token}"[:_ENTITY_ID_LENGTH_CAP]

            payload: dict[str, Any] = {
                "student_external_id": external_id[:_PAYLOAD_VALUE_CAP],
            }
            if meal_plan_name:
                payload["meal_plan"] = meal_plan_name[:_PAYLOAD_VALUE_CAP]
            # Decimal → str preserves precision; banned-float gate stays clean.
            payload["balance"] = str(new_balance)
            payload["currency"] = currency
            payload["low_balance_threshold"] = str(threshold)
            payload["status"] = status
            if dietary_notes:
                payload["dietary_notes"] = dietary_notes[:_DIETARY_NOTES_CAP]
            if meal is not None:
                payload["meal_pk"] = meal.pk

            defaults_dfv: dict[str, Any] = {"value_json": payload}
            defaults_dfv = filter_to_model_fields(defaults_dfv, DynamicFieldValue)

            lookup_kwargs_dfv: dict[str, Any] = {
                "entity_type": _ENTITY_TYPE,
                "entity_id": entity_id,
                "field_key": _FIELD_KEY,
            }
            if "school" in dfv_fields and ctx.school is not None:
                lookup_kwargs_dfv["school"] = ctx.school

            try:
                with row_savepoint():  # atomic-apply isolation
                    obj, created = DynamicFieldValue.objects.update_or_create(
                        defaults=defaults_dfv, **lookup_kwargs_dfv,
                    )
            except (TypeError, ValueError) as exc:
                record_row_error(
                    result,
                    row,
                    f"cafeteria_assignments[row={row_index}]: "
                    f"DFV upsert input error: {type(exc).__name__}",
                    reason_code=LANDER_ERROR,
                )
                continue
            except Exception as exc:  # noqa: BLE001
                record_row_error(
                    result,
                    row,
                    f"cafeteria_assignments[row={row_index}] DFV upsert failed: "
                    f"{type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
                continue
            if created:
                result.created += 1
                result.created_ids.append(obj.pk)
            else:
                result.updated += 1
                result.updated_ids_with_old_values.append(
                    {"pk": obj.pk, "old": {k: getattr(obj, k, None)
                                           for k in defaults_dfv}}
                )
            record_id_mapping(
                ctx=ctx,
                legacy_id=f"{external_id}:{meal_plan_name or 'generic'}",
                canonical_obj=obj, domain="cafeteria_assignments",
            )
        return result


register("cafeteria_assignments", CafeteriaAssignmentLander())

__all__ = ["CafeteriaAssignmentLander"]

"""Cafeteria lander — persists canonical cafeteria-menu rows into ``apps.schoolops.CanteenMeal``.

Migration scope: meal catalog (the menu of meals offered). Per-student meal
plans and balances are handled by the sibling ``cafeteria_assignments`` lander;
this lander owns the catalog so re-imports stay clean.

Canonical row shape::

    {
        "meal_plan":     "Vegetarian Lunch",   # treated as the menu item name
        "balance":       50.00,                 # informational; not persisted on the meal record
        "currency":      "USD",                 # informational
        "dietary_notes": "vegetarian, nut-free",# informational
    }

Upsert key: (school, meal name).
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import (
    coerce_decimal,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
    record_row_error,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register
from .reason_codes import LANDER_ERROR, MISSING_REQUIRED


class CafeteriaLander(Lander):
    domain = "cafeteria"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.schoolops.models import CanteenMeal
        except ImportError as exc:
            raise LanderError(
                f"CafeteriaLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        m_fields = model_field_names(CanteenMeal)
        seen: set[str] = set()

        for row in canonical_rows:
            meal_name = (row.get("meal_plan") or row.get("name") or "").strip()
            if not meal_name:
                record_row_error(
                    result,
                    row,
                    f"cafeteria: missing meal name in {row!r}",
                    reason_code=MISSING_REQUIRED, field="name",
                )
                continue
            key = f"{getattr(ctx.school, 'pk', '')}:{meal_name.lower()}"
            if key in seen:
                result.skipped += 1
                continue
            seen.add(key)

            price = coerce_decimal(row.get("price") or row.get("balance"))
            defaults: dict[str, Any] = {"name": meal_name[:128]}
            if price is not None and "price" in m_fields:
                defaults["price"] = price
            if "is_active" in m_fields:
                defaults["is_active"] = True
            if "school" in m_fields and ctx.school is not None:
                defaults["school"] = ctx.school
            defaults = filter_to_model_fields(defaults, CanteenMeal)

            lookup_kwargs: dict[str, Any] = {"name": meal_name[:128]}
            if "school" in m_fields and ctx.school is not None:
                lookup_kwargs["school"] = ctx.school

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = CanteenMeal.objects.filter(**lookup_kwargs).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                from ._helpers import upsert_with_conflict_detection
                obj, created, preserved = upsert_with_conflict_detection(
                    ctx=ctx, domain="cafeteria", model=CanteenMeal,
                    lookup=lookup_kwargs, defaults=defaults, legacy_id=meal_name,
                )
                if preserved:
                    result.skipped += 1
                    record_id_mapping(ctx=ctx, legacy_id=meal_name, canonical_obj=obj, domain="cafeteria")
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
                    ctx=ctx, legacy_id=meal_name,
                    canonical_obj=obj, domain="cafeteria",
                )
            except Exception as exc:  # noqa: BLE001
                record_row_error(
                    result,
                    row,
                    f"cafeteria upsert failed for {meal_name!r}: "
                    f"{type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
        return result


register("cafeteria", CafeteriaLander())

"""v3.32.0 — Shared helpers for DFV -> first-class assignment promotion.

Extracted from :mod:`apps.migration_cloud.management.commands.promote_dyna_assignments`
so the new replay command (:mod:`replay_dfv_assignments`) can share the
canonical resolution logic without duplicating it. The promote command
remains the SOT for FIRST-pass promotion (rows still in DFV after their
landing); the replay command is for OUT-OF-ORDER bundles where the
catalog side arrived after the assignment row was quarantined to DFV.

Module-level constants are mirrored from the original promote command
so existing tests against that command continue to work.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.utils import timezone


logger = logging.getLogger(__name__)


# Canonical DFV entity_type tokens emitted by the v3.28 landers.
TX_ENTITY = "student_transport_assignment"
HX_ENTITY = "student_hostel_assignment"
CX_ENTITY = "student_cafeteria_assignment"
VALID_ENTITY_TYPES = (TX_ENTITY, HX_ENTITY, CX_ENTITY)

ZERO = Decimal("0")
DEFAULT_LOW_BALANCE_THRESHOLD = Decimal("5.00")
DEFAULT_CURRENCY = "USD"


def coerce_decimal(v: Any) -> Decimal | None:
    """Parse a money string -> Decimal. Never falls through to float."""
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v).strip().replace(",", "").replace("$", ""))
    except (TypeError, ValueError, ArithmeticError):
        return None


def coerce_date(v: Any):
    """Parse ``v`` -> :class:`datetime.date` or ``None`` on failure."""
    if v in (None, ""):
        return None
    import datetime as _dt
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    try:
        return _dt.date.fromisoformat(str(v).strip()[:10])
    except (TypeError, ValueError):
        return None


def resolve_student(StudentProfile, *, tenant_id: int, external_id: str):
    """Best-effort student lookup. Walks the four canonical ID fields."""
    if not external_id:
        return None
    lookup_field = None
    for f in ("external_id", "sis_external_id", "source_id", "admission_number"):
        if f in {fd.name for fd in StudentProfile._meta.get_fields()}:
            lookup_field = f
            break
    if lookup_field is None:
        return None
    # tenant-isolation-allow: helper-resolves-student-within-tenant-school-id-arg
    student = StudentProfile.objects.filter(
        **{lookup_field: external_id}
    ).filter(school_id=tenant_id).first()
    if student is not None:
        return student
    # tenant-isolation-allow: helper-fallback-student-lookup-without-school-fk-cross-tenant-safe-because-external-id-namespace
    return StudentProfile.objects.filter(
        **{lookup_field: external_id}
    ).first()


def promote_transport(
    *,
    payload: dict[str, Any],
    student,
    tenant_id: int,
    apply_changes: bool,
    Route,
    TransportAssignment,
    summary: dict[str, int],
):
    """Promote a single transport-assignment DFV payload."""
    route_pk = payload.get("route_pk")
    route_name = (payload.get("route") or "").strip()
    route = None
    if route_pk:
        # tenant-isolation-allow: route-pk-from-prior-dfv-payload-validated-against-tenant-id
        route = Route.objects.filter(
            pk=route_pk, school_id=tenant_id,
        ).first()
    if route is None and route_name:
        # tenant-isolation-allow: route-name-lookup-scoped-to-tenant-school-id
        route = Route.objects.filter(
            school_id=tenant_id, name=route_name[:120],
        ).first()
    effective_from = coerce_date(payload.get("effective_from"))
    if route is None or effective_from is None:
        summary["skipped_unresolved"] += 1
        return None

    # tenant-isolation-allow: first-class-existence-check-by-unique-together-rows
    already = TransportAssignment.objects.filter(
        student=student, route=route, effective_from=effective_from,
    ).first()
    if already is not None:
        summary["skipped_already_promoted"] += 1
        return already

    if not apply_changes:
        summary["promoted"] += 1
        return None
    obj = TransportAssignment.objects.create(
        school_id=tenant_id,
        student=student,
        route=route,
        effective_from=effective_from,
        effective_to=coerce_date(payload.get("effective_to")),
        status=(payload.get("status") or "active")[:16],
        pickup_stop=(
            payload.get("pickup_stop") or payload.get("stop") or ""
        )[:128],
        dropoff_stop=(payload.get("dropoff_stop") or "")[:128],
        notes=(payload.get("notes") or ""),
    )
    summary["promoted"] += 1
    return obj


def promote_hostel(
    *,
    payload: dict[str, Any],
    student,
    tenant_id: int,
    apply_changes: bool,
    HostelRoom,
    HostelAssignment,
    summary: dict[str, int],
):
    """Promote a single hostel-assignment DFV payload."""
    room_pk = payload.get("room_pk")
    room_name = (payload.get("room") or "").strip()
    room = None
    if room_pk:
        # tenant-isolation-allow: room-pk-from-prior-dfv-payload-validated-against-tenant-hostel-graph
        room = HostelRoom.objects.filter(
            pk=room_pk, hostel__school_id=tenant_id,
        ).first()
    if room is None and room_name:
        # tenant-isolation-allow: room-name-lookup-scoped-via-parent-hostel-school-id
        room = HostelRoom.objects.filter(
            hostel__school_id=tenant_id, name=room_name[:60],
        ).first()
    checkin_date = coerce_date(payload.get("checkin_date"))
    if room is None or checkin_date is None:
        summary["skipped_unresolved"] += 1
        return None

    # tenant-isolation-allow: first-class-existence-check-by-unique-together-rows
    already = HostelAssignment.objects.filter(
        student=student, room=room, effective_from=checkin_date,
    ).first()
    if already is not None:
        summary["skipped_already_promoted"] += 1
        return already

    if not apply_changes:
        summary["promoted"] += 1
        return None
    obj = HostelAssignment.objects.create(
        school_id=tenant_id,
        student=student,
        room=room,
        effective_from=checkin_date,
        effective_to=coerce_date(payload.get("checkout_date")),
        status=(payload.get("status") or "active")[:16],
        bed_label=(payload.get("bed_label") or "")[:32],
        notes=(payload.get("notes") or ""),
    )
    summary["promoted"] += 1
    return obj


def promote_cafeteria(
    *,
    payload: dict[str, Any],
    student,
    tenant_id: int,
    apply_changes: bool,
    CanteenMeal,
    MealPlanBalance,
    summary: dict[str, int],
):
    """Promote a single cafeteria-assignment DFV payload to MealPlanBalance."""
    meal_pk = payload.get("meal_pk")
    meal_name = (payload.get("meal_plan") or "").strip()
    meal = None
    if meal_pk:
        # tenant-isolation-allow: meal-pk-from-prior-dfv-payload-validated-against-tenant-id
        meal = CanteenMeal.objects.filter(
            pk=meal_pk, school_id=tenant_id,
        ).first()
    if meal is None and meal_name:
        # tenant-isolation-allow: meal-name-lookup-scoped-to-tenant-school-id
        meal = CanteenMeal.objects.filter(
            school_id=tenant_id, name=meal_name[:120],
        ).first()

    # tenant-isolation-allow: first-class-existence-check-by-unique-together-rows
    already = MealPlanBalance.objects.filter(
        student=student, meal_plan=meal,
    ).first()
    if already is not None:
        summary["skipped_already_promoted"] += 1
        return already

    balance = coerce_decimal(payload.get("balance"))
    if balance is None:
        balance = ZERO
    threshold = coerce_decimal(payload.get("low_balance_threshold"))
    if threshold is None:
        threshold = DEFAULT_LOW_BALANCE_THRESHOLD
    currency = (payload.get("currency") or DEFAULT_CURRENCY).strip().upper()[:3]
    if not currency:
        currency = DEFAULT_CURRENCY

    # For replay, require a real meal-plan FK — cafeteria rows in DFV
    # generally landed because no CanteenMeal row existed at landing
    # time. If meal is still None AND the payload had a name we couldn't
    # resolve, treat as unresolved.
    if meal is None and meal_name:
        summary["skipped_unresolved"] += 1
        return None

    if not apply_changes:
        summary["promoted"] += 1
        return None
    obj = MealPlanBalance.objects.create(
        school_id=tenant_id,
        student=student,
        meal_plan=meal,
        balance=balance,
        currency=currency,
        low_balance_threshold=threshold,
        status=(payload.get("status") or "active")[:16],
        last_topup_amount=balance if balance > ZERO else None,
        last_topup_at=timezone.now() if balance > ZERO else None,
    )
    summary["promoted"] += 1
    return obj


def promote_one(
    *,
    dfv,
    tenant_id: int,
    apply_changes: bool,
    StudentProfile,
    Route,
    HostelRoom,
    CanteenMeal,
    TransportAssignment,
    HostelAssignment,
    MealPlanBalance,
    summary: dict[str, int],
):
    """Dispatch promotion for one DFV row based on its ``entity_type``."""
    entity_type = dfv.entity_type
    payload = dfv.value_json or {}
    if not isinstance(payload, dict):
        summary["skipped_unresolved"] += 1
        return None
    external_id = (payload.get("student_external_id") or "").strip()
    student = resolve_student(
        StudentProfile, tenant_id=tenant_id, external_id=external_id,
    )
    if student is None:
        summary["skipped_unresolved"] += 1
        return None

    if entity_type == TX_ENTITY:
        return promote_transport(
            payload=payload, student=student, tenant_id=tenant_id,
            apply_changes=apply_changes, Route=Route,
            TransportAssignment=TransportAssignment, summary=summary,
        )
    if entity_type == HX_ENTITY:
        return promote_hostel(
            payload=payload, student=student, tenant_id=tenant_id,
            apply_changes=apply_changes, HostelRoom=HostelRoom,
            HostelAssignment=HostelAssignment, summary=summary,
        )
    if entity_type == CX_ENTITY:
        return promote_cafeteria(
            payload=payload, student=student, tenant_id=tenant_id,
            apply_changes=apply_changes, CanteenMeal=CanteenMeal,
            MealPlanBalance=MealPlanBalance, summary=summary,
        )
    summary["skipped_unresolved"] += 1
    return None

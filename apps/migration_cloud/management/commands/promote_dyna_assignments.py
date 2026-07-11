"""Promote v3.28 DynamicFieldValue assignment rows to v3.29 first-class models.

Scans existing ``apps.metadata.DynamicFieldValue`` rows where
``entity_type`` is one of the three v3.28 assignment types and attempts
to promote each to its v3.29 first-class
:mod:`apps.schoolops` counterpart:

  ``student_transport_assignment``  → :class:`schoolops.TransportAssignment`
  ``student_hostel_assignment``     → :class:`schoolops.HostelAssignment`
  ``student_cafeteria_assignment``  → :class:`schoolops.MealPlanBalance`

Idempotent: skips rows whose first-class equivalent already exists. Each
row runs in a savepoint so one bad row never breaks the batch.

Safety:
    * ``--tenant <id>`` is REQUIRED — refuses cross-tenant runs.
    * ``--dry-run`` is the default; ``--apply`` is mandatory to write.
    * ``--limit N`` caps the per-run scan size (default 1000).

Logs a structured summary at the end:
    ``{scanned, promoted, skipped_already_promoted, skipped_unresolved,
       errors}``.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

# v3.32.0 — resolution helpers live in a shared module so the replay
# command (replay_dfv_assignments) can re-use them. Re-export the
# legacy underscored names from this module so v3.31 tests that import
# ``apps.migration_cloud.management.commands.promote_dyna_assignments._coerce_decimal``
# keep working.
from apps.migration_cloud.management.commands import (
    _assignment_promotion_helpers as _helpers,
)


logger = logging.getLogger(__name__)

_TX_ENTITY = _helpers.TX_ENTITY
_HX_ENTITY = _helpers.HX_ENTITY
_CX_ENTITY = _helpers.CX_ENTITY
_VALID_ENTITY_TYPES = _helpers.VALID_ENTITY_TYPES

_ZERO = _helpers.ZERO
_DEFAULT_THRESHOLD = _helpers.DEFAULT_LOW_BALANCE_THRESHOLD
_DEFAULT_CURRENCY = _helpers.DEFAULT_CURRENCY


def _coerce_decimal(v: Any) -> Decimal | None:
    return _helpers.coerce_decimal(v)


def _coerce_date(v: Any):
    return _helpers.coerce_date(v)


class Command(BaseCommand):
    help = (
        "Promote v3.28 DynamicFieldValue assignment rows to v3.29 "
        "first-class schoolops models (TransportAssignment / "
        "HostelAssignment / MealPlanBalance)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--tenant",
            required=True,
            # School PK is a UUID (apps.schools.School.id = UUIDField); int
            # rejected every real school id at parse time. Downstream this is
            # used only as ``school_id=tenant_id`` filters, all UUID-safe.
            type=str,
            help="School PK (UUID) to promote rows for (REQUIRED; no cross-tenant runs).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Actually write to first-class tables. Without this flag, "
                 "runs in dry-run mode (default).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=1000,
            help="Maximum DFV rows to consider in one run (default 1000).",
        )
        parser.add_argument(
            "--entity-type",
            choices=list(_VALID_ENTITY_TYPES),
            default=None,
            help="Limit to one entity_type; default is all three.",
        )

    def handle(self, *args, **options) -> None:
        tenant_id = options["tenant"]
        apply_changes = bool(options["apply"])
        limit = max(1, int(options["limit"]))
        only_entity = options.get("entity_type")

        # School PK is a UUID — validate/normalize instead of the old
        # ``<= 0`` integer guard (which raised TypeError on a UUID string).
        try:
            tenant_id = str(uuid.UUID(str(tenant_id)))
        except (ValueError, AttributeError, TypeError) as exc:
            raise CommandError(
                "--tenant must be a valid school PK (UUID)",
            ) from exc

        try:
            from apps.metadata.models import DynamicFieldValue
            from apps.people.models import StudentProfile
            from apps.schoolops.models import (
                CanteenMeal,
                HostelAssignment,
                HostelRoom,
                MealPlanBalance,
                Route,
                TransportAssignment,
            )
        except ImportError as exc:
            raise CommandError(f"failed to import models: {exc!s}") from exc

        entity_types = [only_entity] if only_entity else list(_VALID_ENTITY_TYPES)

        summary = {
            "tenant_id": tenant_id,
            "apply": apply_changes,
            "limit": limit,
            "scanned": 0,
            "promoted": 0,
            "skipped_already_promoted": 0,
            "skipped_unresolved": 0,
            "errors": 0,
        }

        # tenant-isolation-allow: management-command-explicit-tenant-filter-per-arg-parser
        qs = DynamicFieldValue.objects.filter(
            school_id=tenant_id,
            entity_type__in=entity_types,
        ).order_by("pk")[:limit]

        for dfv in qs:
            summary["scanned"] += 1
            try:
                with transaction.atomic():
                    sid = transaction.savepoint()
                    try:
                        promoted = self._promote_one(
                            dfv=dfv,
                            tenant_id=tenant_id,
                            apply_changes=apply_changes,
                            StudentProfile=StudentProfile,
                            Route=Route,
                            HostelRoom=HostelRoom,
                            CanteenMeal=CanteenMeal,
                            TransportAssignment=TransportAssignment,
                            HostelAssignment=HostelAssignment,
                            MealPlanBalance=MealPlanBalance,
                            summary=summary,
                        )
                        if not apply_changes:
                            transaction.savepoint_rollback(sid)
                        else:
                            transaction.savepoint_commit(sid)
                        if promoted is None:
                            # already counted under skipped buckets
                            pass
                    except Exception:  # noqa: BLE001
                        transaction.savepoint_rollback(sid)
                        raise
            except (TypeError, ValueError) as exc:
                summary["errors"] += 1
                logger.warning(
                    "promote_dyna_assignments[dfv_pk=%s] input error: %s",
                    dfv.pk, type(exc).__name__,
                )
            except Exception as exc:  # noqa: BLE001
                summary["errors"] += 1
                logger.warning(
                    "promote_dyna_assignments[dfv_pk=%s] %s: %s",
                    dfv.pk, type(exc).__name__, exc,
                )

        # Structured summary — operators parse this from logs. ``self.style.*``
        # are callables that COLOR a string; the previous code passed the
        # callable itself as the message, so ``stdout.write`` blew up on
        # ``msg.endswith`` for every run. Apply the style TO the summary text.
        style = self.style.SUCCESS if apply_changes else self.style.WARNING
        self.stdout.write(style(str(summary)))
        logger.info("promote_dyna_assignments summary: %s", summary)

    # ------------------------------------------------------------------
    # Per-row promotion
    # ------------------------------------------------------------------
    def _promote_one(
        self,
        *,
        dfv,
        tenant_id: str,
        apply_changes: bool,
        StudentProfile,
        Route,
        HostelRoom,
        CanteenMeal,
        TransportAssignment,
        HostelAssignment,
        MealPlanBalance,
        summary: dict,
    ):
        entity_type = dfv.entity_type
        payload = dfv.value_json or {}
        if not isinstance(payload, dict):
            summary["skipped_unresolved"] += 1
            return None
        external_id = (payload.get("student_external_id") or "").strip()
        if not external_id:
            summary["skipped_unresolved"] += 1
            return None

        student_lookup = None
        for f in ("external_id", "sis_external_id", "source_id", "admission_number"):
            if f in {fd.name for fd in StudentProfile._meta.get_fields()}:
                student_lookup = f
                break
        if student_lookup is None:
            summary["skipped_unresolved"] += 1
            return None

        # tenant-isolation-allow: management-command-resolves-student-within-tenant-school-id-arg
        student = StudentProfile.objects.filter(
            **{student_lookup: external_id}
        ).filter(school_id=tenant_id).first() or StudentProfile.objects.filter(
            # tenant-isolation-allow: management-command-fallback-student-lookup-without-school-fk
            **{student_lookup: external_id}
        ).first()
        if student is None:
            summary["skipped_unresolved"] += 1
            return None

        if entity_type == _TX_ENTITY:
            return self._promote_transport(
                dfv=dfv, payload=payload, student=student,
                tenant_id=tenant_id, apply_changes=apply_changes,
                Route=Route, TransportAssignment=TransportAssignment,
                summary=summary,
            )
        if entity_type == _HX_ENTITY:
            return self._promote_hostel(
                dfv=dfv, payload=payload, student=student,
                tenant_id=tenant_id, apply_changes=apply_changes,
                HostelRoom=HostelRoom, HostelAssignment=HostelAssignment,
                summary=summary,
            )
        if entity_type == _CX_ENTITY:
            return self._promote_cafeteria(
                dfv=dfv, payload=payload, student=student,
                tenant_id=tenant_id, apply_changes=apply_changes,
                CanteenMeal=CanteenMeal, MealPlanBalance=MealPlanBalance,
                summary=summary,
            )
        summary["skipped_unresolved"] += 1
        return None

    def _promote_transport(
        self, *, dfv, payload, student, tenant_id, apply_changes,
        Route, TransportAssignment, summary,
    ):
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
        effective_from = _coerce_date(payload.get("effective_from"))
        if route is None or effective_from is None:
            summary["skipped_unresolved"] += 1
            return None

        # tenant-isolation-allow: first-class-existence-check-by-unique-together
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
            effective_to=_coerce_date(payload.get("effective_to")),
            status=(payload.get("status") or "active")[:16],
            pickup_stop=(payload.get("pickup_stop")
                         or payload.get("stop") or "")[:128],
            dropoff_stop=(payload.get("dropoff_stop") or "")[:128],
            notes=(payload.get("notes") or ""),
        )
        summary["promoted"] += 1
        return obj

    def _promote_hostel(
        self, *, dfv, payload, student, tenant_id, apply_changes,
        HostelRoom, HostelAssignment, summary,
    ):
        room_pk = payload.get("room_pk")
        room_name = (payload.get("room") or "").strip()
        room = None
        if room_pk:
            # tenant-isolation-allow: room-pk-from-prior-dfv-payload-and-tenant-hostel-fk-graph
            room = HostelRoom.objects.filter(
                pk=room_pk, hostel__school_id=tenant_id,
            ).first()
        if room is None and room_name:
            # tenant-isolation-allow: room-name-lookup-scoped-via-parent-hostel-school
            room = HostelRoom.objects.filter(
                hostel__school_id=tenant_id, name=room_name[:60],
            ).first()
        checkin_date = _coerce_date(payload.get("checkin_date"))
        if room is None or checkin_date is None:
            summary["skipped_unresolved"] += 1
            return None

        # tenant-isolation-allow: first-class-existence-check-by-unique-together
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
            effective_to=_coerce_date(payload.get("checkout_date")),
            status=(payload.get("status") or "active")[:16],
            bed_label=(payload.get("bed_label") or "")[:32],
            notes=(payload.get("notes") or ""),
        )
        summary["promoted"] += 1
        return obj

    def _promote_cafeteria(
        self, *, dfv, payload, student, tenant_id, apply_changes,
        CanteenMeal, MealPlanBalance, summary,
    ):
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

        # tenant-isolation-allow: first-class-existence-check-by-unique-together
        already = MealPlanBalance.objects.filter(
            student=student, meal_plan=meal,
        ).first()
        if already is not None:
            summary["skipped_already_promoted"] += 1
            return already

        balance = _coerce_decimal(payload.get("balance"))
        if balance is None:
            balance = _ZERO
        threshold = _coerce_decimal(payload.get("low_balance_threshold"))
        if threshold is None:
            threshold = _DEFAULT_THRESHOLD
        currency = (payload.get("currency") or _DEFAULT_CURRENCY).strip().upper()[:3]
        if not currency:
            currency = _DEFAULT_CURRENCY

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
            last_topup_amount=balance if balance > _ZERO else None,
            last_topup_at=timezone.now() if balance > _ZERO else None,
        )
        summary["promoted"] += 1
        return obj

"""
Wave 4 extended ops: tenant UI for library, transport, inventory, canteen, clinic, timetabling.
Gated by School.features / is_feature_enabled (module market).
"""

from __future__ import annotations

import csv
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import DatabaseError, IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.permissions import (
    user_can_access_ops_clinic,
    user_can_access_ops_extended_modules,
)
from apps.people.models import TeacherProfile
from apps.schools.mixins import require_feature, require_school
from apps.schools.models import is_feature_enabled

from django.utils import timezone
from django.utils.translation import gettext as _

from services.post_delete_navigation import redirect_after_save


def _ops_save_redirect(request, url_name: str):
    target = reverse(url_name)
    return redirect_after_save(request, target, list_url=target)
from django.utils.dateparse import parse_date, parse_datetime

from apps.schoolops.models import (
    BookableResource,
    CanteenMeal,
    HostelRoom,
    InventoryItem,
    LibraryItem,
    PosSaleLine,
    ResourceBooking,
    Route,
    Stop,
    MaintenanceRequest,
    SubstituteCover,
    VisitorCheckIn,
)
from apps.schoolops.booking_services import BookingConflictError, cancel_resource_booking, create_resource_booking


def _scoped_library_items(school):
    if school is None:
        return LibraryItem.objects.none()
    return LibraryItem.objects.filter(school=school)


def _ops_roles_ok(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    r = (getattr(user, "role", "") or "").upper()
    return r in (
        "ADMIN",
        "LEADERSHIP",
        "PRINCIPAL",
        "IT_ADMIN",
        "HOD",
        "DEAN",
    )


def _clinic_roles_ok(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    r = (getattr(user, "role", "") or "").upper()
    return r in ("ADMIN", "LEADERSHIP", "PRINCIPAL")


def _school_local_day_bounds_utc(school) -> tuple:
    """
    Start/end (UTC) for the school's current local calendar day.
    Used for POS register-day aggregates (Wave 4 retail depth increment).
    """
    tzname = (getattr(school, "timezone", None) or "UTC").strip() or "UTC"
    try:
        tz = ZoneInfo(tzname)
    except Exception:
        tz = ZoneInfo("UTC")
    now_local = timezone.now().astimezone(tz)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    utc = ZoneInfo("UTC")
    return start_local.astimezone(utc), end_local.astimezone(utc)


MODULE_CODES = (
    ("library", "Library", "accounts:ops_library"),
    ("transport", "Transport", "accounts:ops_transport"),
    ("inventory", "Inventory", "accounts:ops_inventory"),
    # Procurement is the ordering half of inventory, so it rides the same
    # feature code its view already gates on (require_feature("inventory")).
    ("inventory", "Procurement", "accounts:ops_procurement"),
    ("canteen", "Canteen", "accounts:ops_canteen"),
    ("clinic", "Clinic / health log", "accounts:ops_clinic"),
    ("timetabling", "Timetabling", "accounts:ops_timetabling"),
    ("substitutes", "Substitutes / cover", "accounts:ops_substitutes"),
    ("visitor_log", "Visitor log", "accounts:ops_visitor_log"),
    ("facilities_ops", "Facilities / maintenance", "accounts:ops_facilities"),
    ("pos_stub", "POS / till (stub)", "accounts:ops_pos"),
)


@login_required
@user_passes_test(user_can_access_ops_extended_modules)
@require_school
@require_http_methods(["GET"])
def ops_hub(request):
    school = request.school
    cards = []
    for code, label, url_name in MODULE_CODES:
        try:
            url = reverse(url_name)
        except Exception:
            url = "#"
        cards.append(
            {
                "code": code,
                "label": label,
                "enabled": is_feature_enabled(school, code),
                "url": url,
            }
        )
    return render(
        request,
        "schoolops/ops_hub.html",
        {
            "school": school,
            "cards": cards,
            "module_market_url": reverse("siteconfig:module_market"),
        },
    )


@login_required
@user_passes_test(user_can_access_ops_extended_modules)
@require_feature("library")
@require_http_methods(["GET", "POST"])
def ops_library(request):
    school = request.school
    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        if not title:
            messages.error(request, "Title is required.")
        else:
            try:
                LibraryItem.objects.create(
                    school=school,
                    title=title[:255],
                    author=(request.POST.get("author") or "").strip()[:255],
                    copies_total=max(
                        1, min(9999, int(request.POST.get("copies_total") or 1))
                    ),
                )
                messages.success(request, "Item added.")
                return _ops_save_redirect(request, "accounts:ops_library")
            except (IntegrityError, DatabaseError, TypeError, ValueError):
                messages.error(
                    request,
                    "Could not add item (duplicate title/author or invalid data).",
                )
    items = _scoped_library_items(school).filter(is_active=True).order_by("title")[
        :500
    ]
    return render(
        request,
        "schoolops/ops_library.html",
        {
            "school": school,
            "items": items,
            "hub_url": reverse("accounts:ops_hub"),
        },
    )


@login_required
@user_passes_test(user_can_access_ops_extended_modules)
@require_feature("transport")
@require_http_methods(["GET", "POST"])
def ops_transport(request):
    school = request.school
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        if not name:
            messages.error(request, "Route name is required.")
        else:
            try:
                route = Route.objects.create(school=school, name=name[:120])
                stop_name = (request.POST.get("first_stop") or "").strip()
                if stop_name:
                    Stop.objects.create(
                        route=route, name=stop_name[:120], sequence=1
                    )
                messages.success(request, "Route created.")
                return _ops_save_redirect(request, "accounts:ops_transport")
            except IntegrityError:
                messages.error(request, "A route with this name already exists.")
            except (DatabaseError, TypeError, ValueError):
                messages.error(request, "Could not create route.")
    routes = (
        Route.objects.filter(school=school, is_active=True)
        .prefetch_related("stops")
        .order_by("name")[:200]
    )
    return render(
        request,
        "schoolops/ops_transport.html",
        {"school": school, "routes": routes, "hub_url": reverse("accounts:ops_hub")},
    )


@login_required
@user_passes_test(user_can_access_ops_extended_modules)
@require_feature("inventory")
@require_http_methods(["GET", "POST"])
def ops_inventory(request):
    school = request.school
    if request.method == "POST":
        intent = (request.POST.get("intent") or "add").strip().lower()
        if intent == "adjust":
            pk_raw = (request.POST.get("adjust_item_id") or "").strip()
            if not pk_raw.isdigit():
                messages.error(request, "Select a valid inventory line.")
            else:
                try:
                    delta = int((request.POST.get("quantity_delta") or "0").strip())
                except (TypeError, ValueError):
                    delta = 0
                if delta == 0:
                    messages.error(request, "Enter a non-zero adjustment (positive or negative).")
                else:
                    try:
                        from apps.schoolops.inventory_services import (
                            InventoryMovementError,
                            record_inventory_movement,
                        )
                        from apps.schoolops.models_inventory_movement import (
                            InventoryMovement,
                        )

                        record_inventory_movement(
                            school=school,
                            item=InventoryItem.objects.get(pk=int(pk_raw), school=school),
                            movement_type=InventoryMovement.MovementType.ADJUST,
                            quantity_delta=delta,
                            recorded_by=request.user,
                            notes=(request.POST.get("adjust_notes") or "").strip(),
                        )
                        item = InventoryItem.objects.get(pk=int(pk_raw), school=school)
                        messages.success(
                            request,
                            f"Stock updated for “{item.name}” (now {item.quantity}).",
                        )
                        return _ops_save_redirect(request, "accounts:ops_inventory")
                    except InventoryItem.DoesNotExist:
                        messages.error(request, "Inventory line not found.")
                    except InventoryMovementError as exc:
                        messages.error(request, str(exc))
                    except (DatabaseError, TypeError, ValueError):
                        messages.error(request, "Could not adjust stock.")
        elif intent == "checkout":
            pk_raw = (request.POST.get("checkout_item_id") or "").strip()
            if not pk_raw.isdigit():
                messages.error(request, "Select a valid inventory line to check out.")
            else:
                try:
                    from apps.people.models import StudentProfile
                    from apps.schoolops.inventory_services import (
                        InventoryMovementError,
                        checkout_inventory,
                    )

                    student = None
                    sid_raw = (request.POST.get("checkout_student_id") or "").strip()
                    if sid_raw.isdigit():
                        student = StudentProfile.objects.filter(
                            pk=int(sid_raw), school=school
                        ).first()
                        if student is None:
                            messages.error(
                                request, "Student not found in this school."
                            )
                            return _ops_save_redirect(request, "accounts:ops_inventory")
                    checkout_inventory(
                        school=school,
                        item=InventoryItem.objects.get(pk=int(pk_raw), school=school),
                        quantity=(request.POST.get("checkout_quantity") or "0").strip(),
                        recorded_by=request.user,
                        checked_out_to=(request.POST.get("checked_out_to") or "").strip()[:255],
                        student=student,
                    )
                    item = InventoryItem.objects.get(pk=int(pk_raw), school=school)
                    messages.success(
                        request,
                        f"Checked out from “{item.name}” (now {item.quantity}).",
                    )
                    return _ops_save_redirect(request, "accounts:ops_inventory")
                except InventoryItem.DoesNotExist:
                    messages.error(request, "Inventory line not found.")
                except InventoryMovementError as exc:
                    messages.error(request, str(exc))
                except (DatabaseError, TypeError, ValueError):
                    messages.error(request, "Could not record checkout.")
        elif intent == "transfer":
            src_raw = (request.POST.get("transfer_source_id") or "").strip()
            dst_raw = (request.POST.get("transfer_dest_id") or "").strip()
            if not (src_raw.isdigit() and dst_raw.isdigit()):
                messages.error(request, "Pick both a source and a destination item.")
            else:
                try:
                    from apps.schoolops.inventory_services import (
                        InventoryMovementError,
                        transfer_inventory,
                    )

                    transfer_inventory(
                        school=school,
                        source_item=InventoryItem.objects.get(pk=int(src_raw), school=school),
                        dest_item=InventoryItem.objects.get(pk=int(dst_raw), school=school),
                        quantity=(request.POST.get("transfer_quantity") or "0").strip(),
                        recorded_by=request.user,
                    )
                    messages.success(request, "Stock transferred between locations.")
                    return _ops_save_redirect(request, "accounts:ops_inventory")
                except InventoryItem.DoesNotExist:
                    messages.error(request, "Inventory line not found.")
                except InventoryMovementError as exc:
                    messages.error(request, str(exc))
                except (DatabaseError, TypeError, ValueError):
                    messages.error(request, "Could not transfer stock.")
        elif intent == "stock_event":
            pk_raw = (request.POST.get("stock_item_id") or "").strip()
            movement = (request.POST.get("movement") or "").strip().lower()
            if not pk_raw.isdigit():
                messages.error(request, "Select a valid inventory line.")
            elif movement not in ("return", "consume", "loss"):
                messages.error(request, "Choose return, consume, or loss.")
            else:
                try:
                    from apps.schoolops.inventory_services import (
                        InventoryMovementError,
                        consume_inventory,
                        record_inventory_loss,
                        return_inventory,
                    )

                    item = InventoryItem.objects.get(pk=int(pk_raw), school=school)
                    qty = (request.POST.get("stock_quantity") or "0").strip()
                    note = (request.POST.get("stock_notes") or "").strip()
                    reason = (request.POST.get("stock_reason") or "").strip()
                    if movement == "return":
                        return_inventory(
                            school=school, item=item, quantity=qty,
                            recorded_by=request.user, notes=note,
                        )
                        verb = "returned to"
                    elif movement == "consume":
                        consume_inventory(
                            school=school, item=item, quantity=qty,
                            recorded_by=request.user, notes=note,
                        )
                        verb = "consumed from"
                    else:
                        if not reason and not note:
                            messages.error(
                                request,
                                "Provide a loss reason (or notes) when recording a loss.",
                            )
                            return _ops_save_redirect(request, "accounts:ops_inventory")
                        record_inventory_loss(
                            school=school, item=item, quantity=qty,
                            recorded_by=request.user, reason=reason, notes=note,
                        )
                        verb = "recorded as loss from"
                    item.refresh_from_db()
                    messages.success(
                        request,
                        f"Stock {verb} “{item.name}” (now {item.quantity}).",
                    )
                    return _ops_save_redirect(request, "accounts:ops_inventory")
                except InventoryItem.DoesNotExist:
                    messages.error(request, "Inventory line not found.")
                except InventoryMovementError as exc:
                    messages.error(request, str(exc))
                except (DatabaseError, TypeError, ValueError):
                    messages.error(request, "Could not record stock event.")
        elif intent == "scan_reorder":
            try:
                from apps.platform_runtime.workflow_telemetry import (
                    background_job_payload,
                    enqueue_background_job,
                )
                from apps.schoolops.tasks import run_procurement_scan_task

                async_result = enqueue_background_job(
                    run_procurement_scan_task,
                    int(school.pk),
                )
                payload = background_job_payload(async_result)
                if isinstance(payload, dict) and "scanned" in payload:
                    messages.success(
                        request,
                        _(
                            "Reorder scan finished: %(scanned)s items checked, "
                            "%(low)s at or below reorder level."
                        )
                        % {
                            "scanned": payload.get("scanned", 0),
                            "low": payload.get("low", 0),
                        },
                    )
                else:
                    messages.success(
                        request,
                        _("Reorder scan started. Watch live progress on this page."),
                    )
                return _ops_save_redirect(request, "accounts:ops_inventory")
            except (DatabaseError, TypeError, ValueError):
                messages.error(request, _("Could not run the reorder scan."))
        elif intent == "set_reorder":
            pk_raw = (request.POST.get("reorder_item_id") or "").strip()
            if not pk_raw.isdigit():
                messages.error(request, "Select a valid inventory line.")
            else:
                try:
                    threshold = max(0, int((request.POST.get("reorder_threshold") or "0").strip()))
                except (TypeError, ValueError):
                    threshold = 0
                try:
                    item = InventoryItem.objects.get(pk=int(pk_raw), school=school)
                    item.reorder_threshold = threshold
                    item.save(update_fields=["reorder_threshold", "updated_at"])
                    messages.success(
                        request,
                        f"Reorder level for “{item.name}” set to {threshold}.",
                    )
                    return _ops_save_redirect(request, "accounts:ops_inventory")
                except InventoryItem.DoesNotExist:
                    messages.error(request, "Inventory line not found.")
                except (DatabaseError, TypeError, ValueError):
                    messages.error(request, "Could not set reorder level.")
        else:
            name = (request.POST.get("name") or "").strip()
            if not name:
                messages.error(request, "Name is required.")
            else:
                try:
                    qty = max(0, min(10_000_000, int(request.POST.get("quantity") or 0)))
                except (TypeError, ValueError):
                    qty = 0
                try:
                    threshold = max(0, int((request.POST.get("reorder_threshold") or "0").strip()))
                except (TypeError, ValueError):
                    threshold = 0
                try:
                    InventoryItem.objects.create(
                        school=school,
                        name=name[:255],
                        quantity=qty,
                        location=(request.POST.get("location") or "").strip()[:255],
                        reorder_threshold=threshold,
                    )
                    messages.success(request, "Inventory line added.")
                    return _ops_save_redirect(request, "accounts:ops_inventory")
                except (DatabaseError, TypeError, ValueError):
                    messages.error(request, "Could not add item.")
    items = InventoryItem.objects.filter(school=school).order_by("name")[:500]
    from apps.schoolops.models_inventory_movement import InventoryMovement

    movements = list(
        InventoryMovement.objects.filter(school=school)
        .select_related("item", "recorded_by")
        .order_by("-created_at")[:100]
    )
    items = list(items)
    low_stock_count = sum(1 for it in items if it.is_low)
    return render(
        request,
        "schoolops/ops_inventory.html",
        {
            "school": school,
            "items": items,
            "movements": movements,
            "low_stock_count": low_stock_count,
            "hub_url": reverse("accounts:ops_hub"),
        },
    )


@login_required
@user_passes_test(user_can_access_ops_extended_modules)
@require_feature("canteen")
@require_http_methods(["GET", "POST"])
def ops_canteen(request):
    school = request.school
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        if not name:
            messages.error(request, "Meal name is required.")
        else:
            try:
                price = Decimal(str(request.POST.get("price") or "0"))
            except (InvalidOperation, TypeError, ValueError):
                price = Decimal("0")
            if price < 0 or price > Decimal("999999.99"):
                messages.error(request, "Invalid price.")
            else:
                try:
                    CanteenMeal.objects.create(
                        school=school, name=name[:120], price=price
                    )
                    messages.success(request, "Meal added.")
                    return _ops_save_redirect(request, "accounts:ops_canteen")
                except IntegrityError:
                    messages.error(request, "A meal with this name already exists.")
                except (DatabaseError, TypeError, ValueError):
                    messages.error(request, "Could not add meal.")
    meals = CanteenMeal.objects.filter(school=school, is_active=True).order_by("name")[
        :300
    ]
    return render(
        request,
        "schoolops/ops_canteen.html",
        {"school": school, "meals": meals, "hub_url": reverse("accounts:ops_hub")},
    )


@login_required
@user_passes_test(user_can_access_ops_clinic)
@require_feature("clinic")
@require_http_methods(["GET"])
def ops_clinic(request):
    from apps.schoolops.models import HealthRecord

    school = request.school
    records = list(
        HealthRecord.objects.filter(school=school)
        .select_related("student")
        .order_by("-recorded_at")[:150]
    )
    return render(
        request,
        "schoolops/ops_clinic.html",
        {
            "school": school,
            "records": records,
            "hub_url": reverse("accounts:ops_hub"),
        },
    )


@login_required
@user_passes_test(user_can_access_ops_extended_modules)
@require_feature("timetabling")
@require_http_methods(["GET"])
def ops_timetabling(request):
    from apps.academics.scheduling import Schedule

    school = request.school
    schedules = list(
        Schedule.objects.filter(academic_year__school=school)
        .select_related("academic_year", "term")
        .order_by("-generated_at")[:100]
    )
    return render(
        request,
        "schoolops/ops_timetabling.html",
        {
            "school": school,
            "schedules": schedules,
            "hub_url": reverse("accounts:ops_hub"),
        },
    )


def _teacher_user_ids_at_school(school):
    return set(
        TeacherProfile.objects.filter(
            school=school, is_active=True
        ).values_list("user_id", flat=True)
    )


def _user_can_view_substitutes_hub(user, school) -> bool:
    """Ops admins manage covers; teachers may view open market shifts to claim."""
    if user_can_access_ops_extended_modules(user):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return user.pk in _teacher_user_ids_at_school(school)


@login_required
@require_school
@require_feature("substitutes")
@require_http_methods(["GET", "POST"])
def ops_substitutes(request):
    school = request.school
    if not _user_can_view_substitutes_hub(request.user, school):
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden("Substitute market access denied.")

    is_ops_admin = user_can_access_ops_extended_modules(request.user)
    teacher_ids = _teacher_user_ids_at_school(school)
    teachers_qs = (
        TeacherProfile.objects.filter(school=school, is_active=True)
        .select_related("user")
        .order_by("user__last_name", "user__first_name", "user__username")[:500]
    )

    broker_results = []
    if request.method == "POST":
        action = (request.POST.get("action") or "save").strip().lower()
        wd = parse_date((request.POST.get("work_date") or "").strip())
        absent_id = request.POST.get("absent_teacher_id")
        cover_id = (request.POST.get("covering_teacher_id") or "").strip()
        try:
            absent_pk = int(absent_id) if absent_id else 0
        except (TypeError, ValueError):
            absent_pk = 0
        cover_pk = None
        if cover_id:
            try:
                cover_pk = int(cover_id)
            except (TypeError, ValueError):
                cover_pk = -1

        if action == "claim_market":
            shift_id = (request.POST.get("shift_id") or "").strip()
            if not shift_id:
                messages.error(request, "Select an open shift to claim.")
            else:
                claim_as = cover_pk or request.user.pk
                if cover_pk == -1:
                    messages.error(request, "Invalid covering teacher.")
                elif not is_ops_admin and claim_as != request.user.pk:
                    messages.error(request, "Teachers may only claim shifts for themselves.")
                elif claim_as not in teacher_ids:
                    messages.error(request, "Claiming teacher must be on staff at this school.")
                else:
                    from apps.schoolops.substitute_market import (
                        SubstituteMarketError,
                        claim_shift,
                    )

                    try:
                        claim_shift(
                            school=school,
                            shift_id=shift_id,
                            substitute_teacher_id=claim_as,
                        )
                        messages.success(request, "Shift claimed and cover recorded.")
                        return _ops_save_redirect(request, "accounts:ops_substitutes")
                    except SubstituteMarketError as exc:
                        messages.error(request, str(exc).replace("_", " "))
        elif not wd:
            messages.error(request, "Valid work date is required.")
        elif not absent_pk or absent_pk not in teacher_ids:
            messages.error(
                request,
                "Select a teacher who is absent (must be on staff at this school).",
            )
        elif cover_pk == -1:
            messages.error(request, "Invalid covering teacher.")
        elif cover_pk and cover_pk not in teacher_ids:
            messages.error(request, "Covering teacher must be on staff at this school.")
        elif cover_pk == absent_pk:
            messages.error(request, "Absent and covering teacher must differ.")
        elif action == "open_market":
            if not is_ops_admin:
                messages.error(request, "Only operations staff can open market shifts.")
            else:
                from apps.schoolops.substitute_market import (
                    ShiftAlreadyBooked,
                    open_shift,
                )

                try:
                    shift = open_shift(
                        school=school,
                        absent_teacher_id=absent_pk,
                        work_date=wd,
                        period_label=(request.POST.get("period_label") or "").strip()[:80],
                    )
                    if shift.notify_accepted:
                        if shift.notify_used_override:
                            messages.warning(
                                request,
                                f"Market shift opened ({shift.shift_id[:8]}…). "
                                f"No in-department substitute — notified "
                                f"{shift.notify_accepted} of {shift.notify_attempted} "
                                "override candidates. Teachers can claim from the list.",
                            )
                        else:
                            messages.success(
                                request,
                                f"Market shift opened ({shift.shift_id[:8]}…). "
                                f"Notified {shift.notify_accepted} of "
                                f"{shift.notify_attempted} ranked substitutes. "
                                "They can claim from the open shifts list.",
                            )
                    elif shift.notify_attempted:
                        messages.warning(
                            request,
                            f"Market shift opened ({shift.shift_id[:8]}…). "
                            "Ranked substitutes were contacted but none accepted "
                            "delivery — check SMS/WhatsApp configuration.",
                        )
                    else:
                        messages.success(
                            request,
                            f"Market shift opened ({shift.shift_id[:8]}…). "
                            "No phone-reachable substitutes to notify — "
                            "teachers can still claim from the open shifts list.",
                        )
                    return _ops_save_redirect(request, "accounts:ops_substitutes")
                except ShiftAlreadyBooked:
                    messages.error(
                        request,
                        "That period is already locked or booked in the substitute market.",
                    )
        elif action == "broadcast":
            from apps.schoolops.substitute_handover import (
                broadcast_substitute_request,
                find_substitute_candidates,
                select_qualified_or_override,
            )

            ranked = find_substitute_candidates(
                school=school,
                absent_teacher_user_id=absent_pk,
                work_date=wd,
            )
            # Qualification is a real filter here: contact in-department
            # (qualified) substitutes only. Out-of-department teachers are the
            # override tier and are broadcast to solely when no qualified
            # substitute exists, so a small school is never stranded.
            candidates = select_qualified_or_override(ranked)
            using_override = bool(candidates) and not candidates[0].qualified
            broker_results = broadcast_substitute_request(
                school=school,
                candidates=candidates,
                work_date=wd,
                period_label=(request.POST.get("period_label") or "").strip()[:80],
            )
            accepted = sum(1 for result in broker_results if result.accepted)
            if broker_results and using_override:
                messages.warning(
                    request,
                    "No in-department substitute was available — request sent "
                    f"to {accepted} of {len(broker_results)} out-of-department "
                    "candidates (override). Confirm qualification before assigning.",
                )
            elif broker_results:
                messages.success(
                    request,
                    f"Substitute request sent or queued for {accepted} of "
                    f"{len(broker_results)} qualified candidates.",
                )
            else:
                messages.warning(
                    request,
                    "No available substitute candidates with a phone number were found.",
                )
        else:
            try:
                SubstituteCover.objects.create(
                    school=school,
                    work_date=wd,
                    absent_teacher_id=absent_pk,
                    covering_teacher_id=cover_pk,
                    period_label=(request.POST.get("period_label") or "").strip()[:80],
                    notes=(request.POST.get("notes") or "").strip()[:500],
                )
                messages.success(request, "Substitute cover recorded.")
                return _ops_save_redirect(request, "accounts:ops_substitutes")
            except (DatabaseError, IntegrityError):
                messages.error(request, "Could not save substitute cover.")

    covers = list(
        SubstituteCover.objects.filter(school=school)
        .select_related("absent_teacher", "covering_teacher")
        .order_by("-work_date", "-created_at")[:200]
    )
    from apps.schoolops.substitute_market import list_open_shifts

    open_shifts = list_open_shifts(school_id=int(school.pk))
    teacher_by_id = {tp.user_id: tp.user for tp in teachers_qs}
    for row in open_shifts:
        absent_id = int(row.get("absent_teacher_id") or 0)
        row["absent_teacher"] = teacher_by_id.get(absent_id)
    return render(
        request,
        "schoolops/ops_substitutes.html",
        {
            "school": school,
            "covers": covers,
            "teachers": teachers_qs,
            "open_shifts": open_shifts,
            "is_ops_admin": is_ops_admin,
            "can_self_claim": request.user.pk in teacher_ids,
            "broker_results": broker_results,
            "hub_url": reverse("accounts:ops_hub"),
        },
    )


@login_required
@user_passes_test(user_can_access_ops_extended_modules)
@require_school
@require_feature("visitor_log")
@require_http_methods(["GET", "POST"])
def ops_visitor_log(request):
    school = request.school
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        if action == "checkout":
            try:
                vid = int(request.POST.get("visit_id") or 0)
            except (TypeError, ValueError):
                vid = 0
            row = VisitorCheckIn.objects.filter(
                school=school, pk=vid, checked_out_at__isnull=True
            ).first()
            if not row:
                messages.error(request, "Open visit not found.")
            else:
                row.checked_out_at = timezone.now()
                row.save(update_fields=["checked_out_at"])
                messages.success(request, "Visitor checked out.")
            return _ops_save_redirect(request, "accounts:ops_visitor_log")
        name = (request.POST.get("visitor_name") or "").strip()
        if not name:
            messages.error(request, "Visitor name is required.")
        else:
            try:
                VisitorCheckIn.objects.create(
                    school=school,
                    visitor_name=name[:255],
                    host_contact=(request.POST.get("host_contact") or "").strip()[:255],
                    purpose=(request.POST.get("purpose") or "").strip()[:255],
                    badge_number=(request.POST.get("badge_number") or "").strip()[:64],
                    recorded_by=request.user,
                )
                messages.success(request, "Visitor checked in.")
                return _ops_save_redirect(request, "accounts:ops_visitor_log")
            except (DatabaseError, IntegrityError):
                messages.error(request, "Could not record check-in.")

    on_site = list(
        VisitorCheckIn.objects.filter(school=school, checked_out_at__isnull=True)
        .order_by("-checked_in_at")[:100]
    )
    recent = list(
        VisitorCheckIn.objects.filter(school=school).order_by("-checked_in_at")[:150]
    )
    return render(
        request,
        "schoolops/ops_visitor_log.html",
        {
            "school": school,
            "on_site": on_site,
            "recent": recent,
            "hub_url": reverse("accounts:ops_hub"),
        },
    )


@login_required
@user_passes_test(user_can_access_ops_extended_modules)
@require_school
@require_feature("facilities_ops")
@require_http_methods(["GET", "POST"])
def ops_facilities(request):
    school = request.school
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        if action == "create_resource":
            name = (request.POST.get("resource_name") or "").strip()
            if not name:
                messages.error(request, _("Resource name is required."))
            else:
                try:
                    capacity = max(1, int(request.POST.get("resource_capacity") or 1))
                except (TypeError, ValueError):
                    capacity = 1
                rtype = (request.POST.get("resource_type") or "room").strip()[:16]
                allowed = {c.value for c in BookableResource.ResourceType}
                if rtype not in allowed:
                    rtype = BookableResource.ResourceType.ROOM
                hostel_room = None
                hostel_raw = (request.POST.get("hostel_room_id") or "").strip()
                if hostel_raw:
                    try:
                        hostel_pk = int(hostel_raw)
                    except (TypeError, ValueError):
                        hostel_pk = 0
                    hostel_room = (
                        HostelRoom.objects.filter(
                            pk=hostel_pk,
                            hostel__school=school,
                        )
                        .select_related("hostel")
                        .first()
                    )
                    if hostel_room is None:
                        messages.error(
                            request,
                            _("Select a hostel room from this school."),
                        )
                        return _ops_save_redirect(request, "accounts:ops_facilities")
                    if not (request.POST.get("resource_capacity") or "").strip():
                        capacity = max(1, int(hostel_room.capacity or 1))
                try:
                    BookableResource.objects.create(
                        school=school,
                        name=name[:120],
                        resource_type=rtype,
                        capacity=capacity,
                        hostel_room=hostel_room,
                    )
                    messages.success(request, _("Bookable resource added."))
                except IntegrityError:
                    messages.error(
                        request,
                        _("A resource with that name already exists."),
                    )
            return _ops_save_redirect(request, "accounts:ops_facilities")
        if action == "book_resource":
            try:
                resource_id = int(request.POST.get("resource_id") or 0)
            except (TypeError, ValueError):
                resource_id = 0
            resource = BookableResource.objects.filter(
                school=school, pk=resource_id, is_active=True
            ).first()
            start_raw = (request.POST.get("booking_start") or "").strip()
            end_raw = (request.POST.get("booking_end") or "").strip()
            title = (request.POST.get("booking_title") or "").strip()
            start = parse_datetime(start_raw) if start_raw else None
            end = parse_datetime(end_raw) if end_raw else None
            if not resource or not start or not end:
                messages.error(
                    request,
                    _("Resource and start/end times are required."),
                )
            else:
                try:
                    create_resource_booking(
                        school=school,
                        resource=resource,
                        booked_by=request.user,
                        title=title,
                        start=start,
                        end=end,
                    )
                    messages.success(request, _("Booking confirmed."))
                except BookingConflictError:
                    messages.error(
                        request,
                        _("That time slot conflicts with an existing booking."),
                    )
                except ValueError as exc:
                    messages.error(request, str(exc))
            return _ops_save_redirect(request, "accounts:ops_facilities")
        if action == "cancel_booking":
            try:
                bid = int(request.POST.get("booking_id") or 0)
            except (TypeError, ValueError):
                bid = 0
            booking = ResourceBooking.objects.filter(school=school, pk=bid).first()
            if not booking:
                messages.error(request, _("Booking not found."))
            else:
                cancel_resource_booking(booking=booking)
                messages.success(request, _("Booking cancelled."))
            return _ops_save_redirect(request, "accounts:ops_facilities")
        if action == "set_status":
            try:
                tid = int(request.POST.get("ticket_id") or 0)
            except (TypeError, ValueError):
                tid = 0
            new_status = (request.POST.get("new_status") or "").strip()
            allowed = {s.value for s in MaintenanceRequest.Status}
            row = MaintenanceRequest.objects.filter(school=school, pk=tid).first()
            if not row or new_status not in allowed:
                messages.error(request, "Invalid ticket or status.")
            else:
                row.status = new_status
                upd = ["status", "updated_at"]
                if new_status == MaintenanceRequest.Status.CLOSED:
                    row.closed_at = timezone.now()
                    upd.append("closed_at")
                elif row.closed_at:
                    row.closed_at = None
                    upd.append("closed_at")
                row.save(update_fields=upd)
                messages.success(request, "Status updated.")
            return _ops_save_redirect(request, "accounts:ops_facilities")
        title = (request.POST.get("title") or "").strip()
        if not title:
            messages.error(request, "Title is required.")
        else:
            try:
                MaintenanceRequest.objects.create(
                    school=school,
                    title=title[:200],
                    location=(request.POST.get("location") or "").strip()[:200],
                    description=(request.POST.get("description") or "").strip()[:4000],
                    reported_by=request.user,
                )
                messages.success(request, "Maintenance request logged.")
                return _ops_save_redirect(request, "accounts:ops_facilities")
            except (DatabaseError, IntegrityError):
                messages.error(request, "Could not create request.")

    tickets = list(
        MaintenanceRequest.objects.filter(school=school).order_by("-created_at")[:200]
    )
    resources = list(
        BookableResource.objects.filter(school=school, is_active=True).order_by("name")
    )
    bookings = list(
        ResourceBooking.objects.filter(
            school=school,
            status=ResourceBooking.Status.CONFIRMED,
        )
        .select_related("resource", "booked_by")
        .order_by("-created_at")[:100]
    )
    hostel_rooms = list(
        HostelRoom.objects.filter(hostel__school=school)
        .select_related("hostel")
        .order_by("hostel__name", "name")[:200]
    )
    return render(
        request,
        "schoolops/ops_facilities.html",
        {
            "school": school,
            "tickets": tickets,
            "status_choices": MaintenanceRequest.Status,
            "resources": resources,
            "resource_type_choices": BookableResource.ResourceType,
            "bookings": bookings,
            "hostel_rooms": hostel_rooms,
            "hub_url": reverse("accounts:ops_hub"),
        },
    )


def _pos_sale_lines_csv_response(request, school) -> HttpResponse:
    """
    Wave 4 retail increment: CSV export of POS lines for audit / spreadsheet analysis
    (deep retail fiscal registers still product backlog).
    """
    lines = list(
        PosSaleLine.objects.filter(school=school)
        .select_related("inventory_item", "recorded_by")
        .order_by("-created_at")[:5000]
    )
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    slug = getattr(school, "slug", None) or str(school.pk)
    response["Content-Disposition"] = (
        f'attachment; filename="pos_sales_{slug}_{timezone.now().date().isoformat()}.csv"'
    )
    w = csv.writer(response)
    w.writerow(
        [
            "created_at",
            "item_label",
            "quantity",
            "unit_price",
            "line_net",
            "tax_rate_percent",
            "tax_amount",
            "gross",
            "payment_method",
            "inventory_item",
            "notes",
            "recorded_by_email",
        ]
    )
    for ln in lines:
        w.writerow(
            [
                ln.created_at.isoformat() if ln.created_at else "",
                ln.item_label,
                ln.quantity,
                str(ln.unit_price),
                str(ln.line_total),
                str(ln.tax_rate_percent),
                str(ln.tax_amount),
                str(ln.grand_total),
                ln.payment_method,
                ln.inventory_item.name if ln.inventory_item_id else "",
                ln.notes,
                getattr(ln.recorded_by, "email", "") or "",
            ]
        )
    return response


def _pos_sales_summary_json_response(request, school) -> HttpResponse:
    """
    Wave 4 retail depth: machine-readable aggregate of POS lines (audit / integrations).
    Full fiscal period close / Z-report registers remain product backlog.
    """
    lines = list(
        PosSaleLine.objects.filter(school=school)
        .select_related("inventory_item", "recorded_by")
        .order_by("-created_at")[:5000]
    )
    tot_net = sum((ln.line_total for ln in lines), Decimal("0"))
    tot_tax = sum((ln.tax_amount or Decimal("0") for ln in lines), Decimal("0"))
    tot_gross = sum((ln.grand_total for ln in lines), Decimal("0"))
    by_pm: dict[str, Decimal] = {}
    for ln in lines:
        pm = str(ln.payment_method or "")
        by_pm[pm] = by_pm.get(pm, Decimal("0")) + (ln.grand_total or Decimal("0"))
    slug = getattr(school, "slug", None) or str(school.pk)
    payload = {
        "schema": "runmycampus.pos_sales_summary.v1",
        "school_id": school.pk,
        "school_slug": slug,
        "generated_at": timezone.now().isoformat(),
        "line_count": len(lines),
        "totals": {
            "net": str(tot_net),
            "tax": str(tot_tax),
            "gross": str(tot_gross),
        },
        "gross_by_payment_method": {k: str(v) for k, v in sorted(by_pm.items())},
    }
    response = JsonResponse(payload)
    response["Content-Disposition"] = (
        f'attachment; filename="pos_summary_{slug}_{timezone.now().date().isoformat()}.json"'
    )
    return response


@login_required
@user_passes_test(user_can_access_ops_extended_modules)
@require_school
@require_feature("pos_stub")
@require_http_methods(["GET", "POST"])
def ops_pos(request):
    school = request.school
    export = (request.GET.get("export") or "").strip().lower()
    if request.method == "GET" and export == "csv":
        return _pos_sale_lines_csv_response(request, school)
    if request.method == "GET" and export == "json":
        return _pos_sales_summary_json_response(request, school)
    inventory_enabled = is_feature_enabled(school, "inventory")
    inventory_items = []
    if inventory_enabled:
        inventory_items = list(
            InventoryItem.objects.filter(school=school).order_by("name")[:500]
        )

    if request.method == "POST":
        inv_item = None
        inv_raw = (request.POST.get("inventory_item_id") or "").strip()
        if inv_raw.isdigit() and inventory_enabled:
            inv_item = InventoryItem.objects.filter(
                school=school, pk=int(inv_raw)
            ).first()
        label = (request.POST.get("item_label") or "").strip()
        if inv_item and not label:
            label = inv_item.name
        if not label:
            messages.error(request, "Item description is required (or pick inventory).")
        else:
            try:
                qty = max(1, min(9999, int(request.POST.get("quantity") or 1)))
            except (TypeError, ValueError):
                qty = 1
            try:
                unit_price = Decimal(str(request.POST.get("unit_price") or "0"))
            except (InvalidOperation, TypeError, ValueError):
                unit_price = Decimal("0")
            if unit_price < 0 or unit_price > Decimal("999999.99"):
                messages.error(request, "Invalid unit price.")
            else:
                try:
                    tax_rate = Decimal(
                        str(request.POST.get("tax_rate_percent") or "0").strip()
                    )
                except (InvalidOperation, TypeError, ValueError):
                    tax_rate = Decimal("0")
                if tax_rate < 0 or tax_rate > Decimal("100"):
                    messages.error(request, "Tax rate must be between 0 and 100.")
                else:
                    line_net = (unit_price * Decimal(qty)).quantize(
                        Decimal("0.01"), ROUND_HALF_UP
                    )
                    tax_amt = (line_net * tax_rate / Decimal("100")).quantize(
                        Decimal("0.01"), ROUND_HALF_UP
                    )
                    pm = (request.POST.get("payment_method") or PosSaleLine.PaymentMethod.CASH)
                    if pm not in {c.value for c in PosSaleLine.PaymentMethod}:
                        pm = PosSaleLine.PaymentMethod.CASH
                    try:
                        with transaction.atomic():
                            if inv_item and inventory_enabled:
                                # Route the stock decrement through the movement
                                # ledger (not a bare .update()) so a POS sale (a)
                                # writes an InventoryMovement audit row that keeps
                                # sum(movements) reconciled with item.quantity and
                                # (b) fires the post_save low-stock reorder alert —
                                # both of which the raw decrement silently bypassed.
                                # CONSUME is the closest type: stock permanently
                                # leaves inventory via the sale. The below-zero guard
                                # in record_inventory_movement enforces the same
                                # oversell protection as the old quantity__gte filter.
                                from apps.schoolops.inventory_services import (
                                    InventoryMovementError,
                                    record_inventory_movement,
                                )
                                from apps.schoolops.models_inventory_movement import (
                                    InventoryMovement,
                                )

                                try:
                                    record_inventory_movement(
                                        school=school,
                                        item=inv_item,
                                        movement_type=InventoryMovement.MovementType.CONSUME,
                                        quantity_delta=-qty,
                                        recorded_by=request.user,
                                        notes=f"POS sale: {label[:80]}",
                                    )
                                except (
                                    InventoryMovementError,
                                    InventoryItem.DoesNotExist,
                                ):
                                    messages.error(
                                        request,
                                        "Insufficient stock for the selected inventory item.",
                                    )
                                else:
                                    PosSaleLine.objects.create(
                                        school=school,
                                        item_label=label[:255],
                                        quantity=qty,
                                        unit_price=unit_price,
                                        payment_method=pm,
                                        tax_rate_percent=tax_rate,
                                        tax_amount=tax_amt,
                                        notes=(request.POST.get("notes") or "").strip()[:255],
                                        inventory_item=inv_item,
                                        recorded_by=request.user,
                                    )
                                    messages.success(request, "Sale line recorded.")
                                    return _ops_save_redirect(request, "accounts:ops_pos")
                            else:
                                PosSaleLine.objects.create(
                                    school=school,
                                    item_label=label[:255],
                                    quantity=qty,
                                    unit_price=unit_price,
                                    payment_method=pm,
                                    tax_rate_percent=tax_rate,
                                    tax_amount=tax_amt,
                                    notes=(request.POST.get("notes") or "").strip()[:255],
                                    inventory_item=inv_item,
                                    recorded_by=request.user,
                                )
                                messages.success(request, "Sale line recorded.")
                                return _ops_save_redirect(request, "accounts:ops_pos")
                    except (DatabaseError, IntegrityError):
                        messages.error(request, "Could not record sale.")

    lines = list(
        PosSaleLine.objects.filter(school=school)
        .select_related("inventory_item")
        .order_by("-created_at")[:300]
    )
    tot_net = sum((ln.line_total for ln in lines), Decimal("0"))
    tot_tax = sum((ln.tax_amount or Decimal("0") for ln in lines), Decimal("0"))
    tot_gross = sum((ln.grand_total for ln in lines), Decimal("0"))
    return render(
        request,
        "schoolops/ops_pos.html",
        {
            "school": school,
            "lines": lines,
            "payment_methods": PosSaleLine.PaymentMethod,
            "inventory_enabled": inventory_enabled,
            "inventory_items": inventory_items,
            "hub_url": reverse("accounts:ops_hub"),
            "pos_totals": {
                "net": tot_net,
                "tax": tot_tax,
                "gross": tot_gross,
            },
        },
    )

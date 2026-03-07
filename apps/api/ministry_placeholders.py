"""
Lightweight ministry-facing API payloads.

These routes are feature-flag controlled and provide export-ready JSON for:
- Cartescolaire / school-map style student registry
- DGI / finance summary stream
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum
from django.http import JsonResponse
from django.utils.dateparse import parse_date

from apps.academics.models import AcademicYear
from apps.api.rate_limit import throttle_ip_request
from apps.finance.models import Invoice, Payment
from apps.people.models import StudentProfile
from apps.siteconfig.models import SiteSettings, default_backend_feature_flags
from apps.api.ministry_connectors import (
    ministry_runtime_status,
    submit_cartescolaire,
    submit_dgi,
)

MINISTRY_API_RATE_LIMIT_WINDOW = 60 * 15
MINISTRY_API_RATE_LIMIT_MAX = 120


def _as_float(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _require_staff(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)
    if not (user.is_staff or user.is_superuser):
        return JsonResponse({"detail": "Staff access required."}, status=403)
    return None


def _feature_enabled(flag_key: str) -> bool:
    site = SiteSettings.get_solo()
    flags = {**default_backend_feature_flags(), **(site.backend_feature_flags or {})}
    return bool(flags.get(flag_key))


def _wants_sync(request) -> bool:
    return str(request.GET.get("sync", "")).strip().lower() in {"1", "true", "yes", "on"}


def _ministry_rate_limited(request, scope: str):
    allowed, retry_after = throttle_ip_request(
        request,
        scope=f"ministry:{scope}",
        max_count=MINISTRY_API_RATE_LIMIT_MAX,
        window_seconds=MINISTRY_API_RATE_LIMIT_WINDOW,
    )
    if allowed:
        return None
    return JsonResponse(
        {
            "status": "rate_limited",
            "service": scope,
            "retry_after": retry_after,
        },
        status=429,
    )


def cartescolaire_placeholder(request):
    """
    Export registry-like student payload for ministry school-map ingestion.
    """
    denied = _require_staff(request)
    if denied:
        return denied
    if not _feature_enabled("enable_ministry_api_cartescolaire"):
        return JsonResponse(
            {"status": "disabled", "message": "Cartescolaire integration is disabled in Feature Control."},
            status=503,
        )
    rl = _ministry_rate_limited(request, "cartescolaire")
    if rl:
        return rl

    year_id = request.GET.get("academic_year_id")
    active_year = (
        AcademicYear.objects.filter(id=year_id).first()
        if year_id
        else AcademicYear.objects.filter(is_active=True).order_by("-start_date").first()
    )
    if not active_year:
        return JsonResponse(
            {"status": "error", "message": "No academic year selected or active."},
            status=400,
        )

    limit = min(max(int(request.GET.get("limit", 500)), 1), 5000)
    students_qs = (
        StudentProfile.objects.filter(academic_year=active_year, is_active=True)
        .select_related("classroom", "specialty")
        .order_by("classroom__name", "last_name", "first_name")
    )
    students = list(students_qs[:limit])

    records = [
        {
            "student_code": s.student_code,
            "first_name": s.first_name,
            "last_name": s.last_name,
            "gender": s.gender,
            "classroom": s.classroom.name if s.classroom else "",
            "specialty": s.specialty.name if s.specialty else "",
            "exam_candidate_number": s.exam_candidate_number or "",
            "exam_center_code": s.exam_center_code or "",
            "exam_system": s.exam_system or "",
            "is_active": bool(s.is_active),
        }
        for s in students
    ]

    gender_breakdown = {
        row["gender"] or "UNKNOWN": row["count"]
        for row in students_qs.values("gender").annotate(count=Count("id")).order_by("gender")
    }
    by_classroom = {
        row["classroom__name"] or "Unassigned": row["count"]
        for row in students_qs.values("classroom__name").annotate(count=Count("id")).order_by("classroom__name")
    }
    site = SiteSettings.get_solo()
    runtime = ministry_runtime_status()
    sync = {
        "attempted": False,
        "enabled": bool(_feature_enabled("enable_ministry_live_sync")),
        "result": None,
    }
    if _wants_sync(request) and sync["enabled"]:
        sync["attempted"] = True
        sync_payload = {
            "school_code": site.school_code,
            "academic_year": active_year.name,
            "records": records,
            "summary": {
                "total_students": students_qs.count(),
                "gender_breakdown": gender_breakdown,
                "classroom_breakdown": by_classroom,
            },
        }
        sync["result"] = submit_cartescolaire(sync_payload)

    return JsonResponse(
        {
            "status": "ok",
            "export_type": "cartescolaire",
            "school_code": site.school_code,
            "academic_year": active_year.name,
            "record_count": len(records),
            "truncated": students_qs.count() > len(records),
            "summary": {
                "total_students": students_qs.count(),
                "gender_breakdown": gender_breakdown,
                "classroom_breakdown": by_classroom,
            },
            "integration_runtime": runtime,
            "sync": sync,
            "records": records,
        },
        status=200,
    )


def dgi_placeholder(request):
    """
    Export finance summary payload aligned with DGI-ready reconciliation checks.
    """
    denied = _require_staff(request)
    if denied:
        return denied
    if not _feature_enabled("enable_ministry_api_dgi"):
        return JsonResponse(
            {"status": "disabled", "message": "DGI integration is disabled in Feature Control."},
            status=503,
        )
    rl = _ministry_rate_limited(request, "dgi")
    if rl:
        return rl

    start = parse_date(request.GET.get("start") or "")
    end = parse_date(request.GET.get("end") or "")
    if not start:
        start = date(date.today().year, 1, 1)
    if not end:
        end = date.today()

    invoices_qs = Invoice.objects.filter(issued_date__gte=start, issued_date__lte=end)
    payments_qs = Payment.objects.filter(paid_at__date__gte=start, paid_at__date__lte=end, status="completed")

    invoiced_total = invoices_qs.aggregate(total=Sum("total_amount")).get("total") or Decimal("0.00")
    outstanding_total = invoices_qs.aggregate(total=Sum("balance_amount")).get("total") or Decimal("0.00")
    collected_total = payments_qs.aggregate(total=Sum("amount")).get("total") or Decimal("0.00")
    paid_receipt_count = payments_qs.exclude(receipt_number="").count()
    estimated_stamp_duty = Decimal("1000.00") * Decimal(str(paid_receipt_count))

    recent_invoices = list(
        invoices_qs.select_related("student")
        .order_by("-issued_date", "-id")[:100]
    )
    entries = [
        {
            "invoice_id": inv.id,
            "reference": inv.reference or "",
            "payment_code": inv.payment_code or "",
            "student_code": inv.student.student_code if inv.student else "",
            "issued_date": inv.issued_date.isoformat() if inv.issued_date else "",
            "status": inv.status,
            "total_amount": _as_float(inv.total_amount),
            "balance_amount": _as_float(inv.balance_amount),
        }
        for inv in recent_invoices
    ]
    runtime = ministry_runtime_status()
    sync = {
        "attempted": False,
        "enabled": bool(_feature_enabled("enable_ministry_live_sync")),
        "result": None,
    }
    if _wants_sync(request) and sync["enabled"]:
        sync["attempted"] = True
        sync_payload = {
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "summary": {
                "invoice_count": invoices_qs.count(),
                "payment_count": payments_qs.count(),
                "invoiced_total": _as_float(invoiced_total),
                "collected_total": _as_float(collected_total),
                "outstanding_total": _as_float(outstanding_total),
                "estimated_stamp_duty_xaf": _as_float(estimated_stamp_duty),
            },
            "entries": entries,
        }
        sync["result"] = submit_dgi(sync_payload)

    return JsonResponse(
        {
            "status": "ok",
            "export_type": "dgi",
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "summary": {
                "invoice_count": invoices_qs.count(),
                "payment_count": payments_qs.count(),
                "invoiced_total": _as_float(invoiced_total),
                "collected_total": _as_float(collected_total),
                "outstanding_total": _as_float(outstanding_total),
                "estimated_stamp_duty_xaf": _as_float(estimated_stamp_duty),
            },
            "integration_runtime": runtime,
            "sync": sync,
            "entries": entries,
        },
        status=200,
    )

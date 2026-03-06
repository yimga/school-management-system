"""
Student 360: timeline feed, aggregation summary, and permission-gated export pack (RunMyCampus blueprint B1, 26.1).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def get_student_360_summary(
    school_id,
    student_id: int,
    *,
    include_timeline_count: bool = True,
    include_export_available: bool = True,
) -> Dict[str, Any]:
    """
    Aggregated 360 view for a student: linked academic, finance, attendance, and timeline/export pointers.
    Caller must enforce permission. Returns dict with sections and counts (no PII in keys; values are counts/summaries).
    """
    out = {
        "student_id": student_id,
        "school_id": str(school_id),
        "academic": {},
        "finance": {},
        "attendance": {},
        "behavior": {},
        "safeguarding": {},
    }
    try:
        from django.apps import apps
        StudentProfile = apps.get_model("people", "StudentProfile")
        student = StudentProfile.objects.filter(school_id=school_id, pk=student_id).first()
        if not student:
            return out
        # Academic: evaluations count, enrollments
        if apps.is_installed("evals"):
            Evaluation = apps.get_model("evals", "Evaluation")
            out["academic"]["evaluations_count"] = Evaluation.objects.filter(student=student).count()
        if apps.is_installed("academics"):
            from apps.academics.models import ClassEnrollment
            out["academic"]["enrollments_count"] = ClassEnrollment.objects.filter(student=student).count()
        # Finance: invoices summary
        if apps.is_installed("finance"):
            Invoice = apps.get_model("finance", "Invoice")
            inv_qs = Invoice.objects.filter(student=student)
            out["finance"]["invoices_count"] = inv_qs.count()
            from django.db.models import Sum
            tot = inv_qs.aggregate(s=Sum("total_amount"))
            out["finance"]["invoices_total"] = float(tot["s"] or 0)
        # Attendance: placeholder (policy-driven)
        out["attendance"]["summary_available"] = apps.is_installed("siteconfig")
        if include_timeline_count:
            try:
                from apps.events.models import DomainEvent
                from django.db.models import Q
                out["timeline_events_count"] = DomainEvent.objects.filter(
                    school_id=school_id
                ).filter(
                    Q(payload__student_id=student_id) | Q(payload__student_id=str(student_id))
                ).count()
            except Exception:
                out["timeline_events_count"] = 0
        if include_export_available:
            out["export_pack_available"] = True
    except Exception:
        pass
    return out


def get_student_timeline_feed(
    school_id,
    student_id: int,
    *,
    limit: int = 100,
    event_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Unified timeline of events for a student (admissions, academic, behavior, finance, etc.).
    Reads from DomainEvent outbox where payload references this student.
    Caller must enforce permission (e.g. user can view this student).
    """
    try:
        from apps.events.models import DomainEvent
        from django.db.models import Q

        qs = (
            DomainEvent.objects.filter(school_id=school_id)
            .filter(Q(payload__student_id=student_id) | Q(payload__student_id=str(student_id)))
            .order_by("-created_at")[:limit]
        )
        if event_types:
            qs = qs.filter(event_type__in=event_types)
        return [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "payload": e.payload,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in qs
        ]
    except Exception:
        return []


def export_student_pack(
    school_id,
    student_id: int,
    *,
    format: str = "json",
) -> Optional[Dict[str, Any]]:
    """
    Permission-gated export pack for a student (GDPR data portability).
    Delegates to compliance.gdpr_services.export_student_data_portability.
    Caller must enforce MFA and access control before calling.
    """
    try:
        from apps.compliance.gdpr_services import export_student_data_portability
        return export_student_data_portability(school_id, student_id, format=format)
    except Exception:
        return None

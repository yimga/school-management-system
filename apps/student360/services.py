"""
Student 360: timeline feed and permission-gated export pack (RunMyCampus blueprint B1).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


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

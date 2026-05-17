"""
De-identified export for Analytics/Research DB (Section 1.15).
Stub service: aggregates and snapshot without PII; schema versioned.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from django.utils import timezone

from apps.platform_runtime.structured_logging import log_exception_with_context

# Typed exceptions for research aggregates (§2.4 broad-except policy)
_RESEARCH_AGGREGATE_ERRORS = (
    ImportError,
    AttributeError,
    LookupError,
    TypeError,
    ValueError,
    DatabaseError,
    ObjectDoesNotExist,
)


RESEARCH_SCHEMA_VERSION = "1.0"


def get_deidentified_aggregates(
    school_id: int,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    dimensions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Return de-identified aggregates for a school (no PII).
    dimensions: e.g. ["by_region", "by_level", "by_term"]; only non-identifying dimensions.
    """
    out = {
        "school_id_hashed": _hash_school_id(school_id),
        "from_date": from_date,
        "to_date": to_date,
        "dimensions": dimensions or [],
        "aggregates": {},
        "schema_version": RESEARCH_SCHEMA_VERSION,
        "exported_at": timezone.now().isoformat(),
    }
    try:
        from django.apps import apps

        if apps.is_installed("people"):
            StudentProfile = apps.get_model("people", "StudentProfile")
            qs = StudentProfile.objects.filter(school_id=school_id, is_active=True)
            out["aggregates"]["students_count"] = qs.count()
        if apps.is_installed("evals"):
            Evaluation = apps.get_model("evals", "Evaluation")
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            qs = Evaluation.objects.filter(student__school_id=school_id)
            out["aggregates"]["evaluations_count"] = qs.count()
        if apps.is_installed("finance"):
            Invoice = apps.get_model("finance", "Invoice")
            from django.db.models import Sum

            tot = Invoice.objects.filter(school_id=school_id).aggregate(
                s=Sum("total_amount")
            )
            out["aggregates"]["invoices_total"] = float(tot["s"] or 0)
            out["aggregates"]["invoices_count"] = Invoice.objects.filter(
                school_id=school_id
            ).count()
    except _RESEARCH_AGGREGATE_ERRORS:
        log_exception_with_context(
            "research get_deidentified_aggregates failed",
            school_id=school_id,
            extra={"step": "aggregates"},
            exc_info=False,
        )
    return out


def export_research_snapshot(
    school_id: int,
    format: str = "json",
) -> Dict[str, Any]:
    """
    Export a research snapshot (de-identified) for push to research DB.
    No PII; includes schema_version and exported_at.
    """
    aggregates = get_deidentified_aggregates(school_id)
    return {
        "schema_version": RESEARCH_SCHEMA_VERSION,
        "exported_at": timezone.now().isoformat(),
        "payload": aggregates,
    }


def _hash_school_id(school_id: int) -> str:
    """Stable pseudonymous id for school (e.g. for longitudinal research)."""
    import hashlib

    return hashlib.sha256(f"school:{school_id}".encode()).hexdigest()[:16]

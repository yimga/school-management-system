"""Tenant v3 extended cockpit sections — DB-backed hydration (batch 1612/1615)."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User


def _hydrate_financial_timeline(
    section: dict[str, Any], widget_data: dict[str, dict]
) -> dict[str, Any]:
    fin = widget_data.get("finance") or {}
    balance = fin.get("balance")
    if balance is None:
        return section
    out = dict(section)
    out["enabled"] = True
    out["balance_display"] = str(balance)
    overdue = int(fin.get("overdue") or 0)
    out["balance_tone"] = "warn" if overdue else "ok"
    events = []
    if overdue:
        events.append(
            {
                "iso": "",
                "label": str(_("Overdue fees")),
                "amount_display": str(balance),
                "tone": "fee",
                "icon": "!",
            }
        )
    out["events"] = events
    out["a8_wire_pending"] = False
    return out


def _hydrate_ai_study_buddy(request: HttpRequest, section: dict[str, Any]) -> dict[str, Any]:
    user = getattr(request, "user", None)
    if user is None or str(getattr(user, "role", "") or "").upper() != User.Role.STUDENT:
        return section
    try:
        url = reverse("portal:ai_stream")
    except Exception:
        try:
            url = reverse("portal:student_portal_grades")
        except Exception:
            url = ""
    if not url:
        return section
    out = dict(section)
    out["enabled"] = True
    out["wire_pending"] = False
    out["a8_wire_pending"] = False
    out["suggestions"] = [
        {
            "icon": "✦",
            "label": str(_("Open study assist")),
            "url": url,
        }
    ]
    return out


def _hydrate_gradebook_trend(
    request: HttpRequest, section: dict[str, Any]
) -> dict[str, Any]:
    user = getattr(request, "user", None)
    if user is None or str(getattr(user, "role", "") or "").upper() != User.Role.STUDENT:
        return section
    try:
        from apps.evals.models import Evaluation
        from apps.academics.services import get_active_year_and_term
        from apps.people.models import StudentProfile

        year, term = get_active_year_and_term()
        if not year or not term:
            return section
        school = getattr(request, "school", None)
        if school is None:
            return section
        profile = (
            StudentProfile.objects.filter(user=user, is_active=True, school=school)
            .select_related("classroom")
            .first()
        )
        if profile is None:
            return section
        qs = (
            Evaluation.objects.filter(
                student=profile,
                academic_year=year,
                term=term,
                school=school,
            )
            .select_related("subject_assignment__subject")
        )
        subjects: list[dict[str, Any]] = []
        seen: set[str] = set()
        for ev in qs[:12]:
            sa = getattr(ev, "subject_assignment", None)
            subject = getattr(sa, "subject", None) if sa else None
            name = getattr(subject, "name", None) if subject else None
            if not name or name in seen:
                continue
            seen.add(name)
            avg = getattr(ev, "average", None) or getattr(ev, "total", None)
            if avg is None:
                continue
            subjects.append(
                {
                    "subject": str(name),
                    "current_value": str(avg),
                    "delta_text": "",
                    "delta_tone": "",
                    "spark_points": "",
                }
            )
        if not subjects:
            return section
        out = dict(section)
        out["enabled"] = True
        out["subjects"] = subjects[:6]
        out["a8_wire_pending"] = False
        return out
    except Exception:
        return section


def hydrate_tenant_v3_extended_realdata(
    request: HttpRequest, tenant_cockpit: dict[str, Any]
) -> dict[str, Any]:
    """Overlay live metrics on v3 extended sections when data exists."""
    from apps.portal.tenant_cockpit_realdata import _role_widget_bundle

    widget_data = _role_widget_bundle(request)

    if widget_data:
        ft = tenant_cockpit.get("financial_timeline")
        if isinstance(ft, dict):
            tenant_cockpit["financial_timeline"] = _hydrate_financial_timeline(
                ft, widget_data
            )

    gb = tenant_cockpit.get("gradebook_trend")
    if isinstance(gb, dict):
        tenant_cockpit["gradebook_trend"] = _hydrate_gradebook_trend(request, gb)

    ai = tenant_cockpit.get("ai_study_buddy")
    if isinstance(ai, dict):
        tenant_cockpit["ai_study_buddy"] = _hydrate_ai_study_buddy(request, ai)

    return tenant_cockpit


__all__ = ["hydrate_tenant_v3_extended_realdata"]

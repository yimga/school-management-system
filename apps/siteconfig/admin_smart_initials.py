"""Registry of editable, server-calculated Django admin initial values."""

from __future__ import annotations

from typing import Any


def _request_school(request):
    school = getattr(request, "school", None)
    if school is not None:
        return school
    school_id = str(request.GET.get("school") or "").strip()
    if not school_id:
        return None
    from apps.schools.models import School

    return School.objects.filter(pk=school_id).first()


def _academic_year_initials(request) -> dict[str, Any]:
    school = _request_school(request)
    if school is None:
        return {}
    from apps.academics.structure_provisioning import forecast_academic_year

    forecast = forecast_academic_year(school)
    if not forecast:
        return {}
    return {
        "school": school.pk,
        "name": forecast["name"],
        "start_date": forecast["start_date"],
        "end_date": forecast["end_date"],
        "is_active": forecast["is_active"],
    }


INITIAL_BUILDERS = {
    "academics.academicyear": _academic_year_initials,
}


def build_admin_smart_initials(model, request) -> dict[str, Any]:
    """Return suggestions only; bound POST data and user edits always win."""

    builder = INITIAL_BUILDERS.get(model._meta.label_lower)
    if builder is None:
        return {}
    return dict(builder(request) or {})

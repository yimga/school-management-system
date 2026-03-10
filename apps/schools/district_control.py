"""
F1: District control plane — multi-school hierarchy and control.
"""
from __future__ import annotations

from typing import Any


def get_district_schools(parent_school_id: Any) -> list[Any]:
    """Return schools under a district (parent_school_id)."""
    from apps.schools.models import School
    return list(School.objects.filter(parent_school_id=parent_school_id).order_by("name"))

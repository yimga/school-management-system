"""v4.00.36 — resolve the effective ``GradeScaleRegistry`` for a tenant.

Resolution order (first match wins):

1. ``TenantGradeScaleOverride(school, context_key)`` exact match;
2. ``TenantGradeScaleOverride(school, context_key="")`` (tenant default override);
3. ``RuntimeDefaults.default_grading_scale`` resolved as a ``GradeScaleRegistry`` code;
4. ``GradeScaleRegistry.country_code == school.country_code`` first row;
5. ``None`` (caller falls back to the model's own default).

Pure helper: no writes, two SELECTs maximum.
"""

from __future__ import annotations

from datetime import date as _date
from typing import Any


def _today() -> _date:
    from django.utils import timezone
    return timezone.now().date()


def _row_is_live(row: Any, today: _date) -> bool:
    eff_from = getattr(row, "effective_from", None)
    eff_until = getattr(row, "effective_until", None)
    if eff_from and today < eff_from:
        return False
    if eff_until and today > eff_until:
        return False
    return True


def resolve_grade_scale_for_tenant(
    school: Any,
    *,
    context_key: str = "",
    today: _date | None = None,
) -> Any | None:
    """Return the effective ``GradeScaleRegistry`` row for the tenant.

    ``context_key`` lets a tenant pin different scales per division
    ("primary" vs "secondary"); blank context is the tenant default.
    """
    if school is None:
        return None
    today = today or _today()
    try:
        from .models import GradeScaleRegistry, TenantGradeScaleOverride
    except (ImportError, RuntimeError):
        return None

    # 1 — exact context override
    if context_key:
        try:
            # tenant-isolation-allow: tenant-grade-scale-override-scoped-via-school-fk-resolver
            row = (
                TenantGradeScaleOverride.objects.filter(
                    school=school, context_key=context_key
                )
                .select_related("grade_scale")
                .first()
            )
        except (AttributeError, RuntimeError, ValueError):
            row = None
        if row and _row_is_live(row, today) and row.grade_scale and row.grade_scale.is_active:
            return row.grade_scale

    # 2 — tenant default override (context_key="")
    try:
        # tenant-isolation-allow: tenant-grade-scale-override-scoped-via-school-fk-resolver
        default_override = (
            TenantGradeScaleOverride.objects.filter(
                school=school, context_key="", is_default=True
            )
            .select_related("grade_scale")
            .first()
        )
    except (AttributeError, RuntimeError, ValueError):
        default_override = None
    if (
        default_override
        and _row_is_live(default_override, today)
        and default_override.grade_scale
        and default_override.grade_scale.is_active
    ):
        return default_override.grade_scale

    # 3 — RuntimeDefaults.default_grading_scale → GradeScaleRegistry code
    runtime_code = ""
    try:
        from apps.platform_runtime.models import RuntimeDefaults

        # tenant-isolation-allow: runtime-defaults-is-platform-singleton-not-tenant-scoped
        runtime_row = (
            RuntimeDefaults.objects.only("default_grading_scale").first()
        )
        runtime_code = (getattr(runtime_row, "default_grading_scale", "") or "").strip()
    except (ImportError, RuntimeError, AttributeError, ValueError):
        runtime_code = ""
    if runtime_code:
        try:
            row = GradeScaleRegistry.objects.filter(
                code=runtime_code, is_active=True
            ).first()
        except (AttributeError, RuntimeError, ValueError):
            row = None
        if row:
            return row

    # 4 — fall back to a country-matched scale
    country_code = (getattr(school, "country_code", "") or "").strip().upper()
    if country_code:
        try:
            row = (
                GradeScaleRegistry.objects.filter(
                    country_code__iexact=country_code, is_active=True
                )
                .order_by("sort_order", "name")
                .first()
            )
        except (AttributeError, RuntimeError, ValueError):
            row = None
        if row:
            return row

    return None


# ---------------------------------------------------------------------------
# Consumer bridge: GradeScaleRegistry.family → bulk_gradebook GradeScale.kind
#
# The platform catalog's ``family`` slot is human-readable ("numeric",
# "letter", "gpa", "competency"). Most grade-entry surfaces want a more
# constrained "kind" enum: ``percent`` / ``points`` / ``letter`` / ``gpa4``.
# This bridge keeps the mapping in one place so every consumer agrees.

_FAMILY_TO_KIND: dict[str, str] = {
    "numeric": "percent",
    "percent": "percent",
    "points": "points",
    "letter": "letter",
    "letters": "letter",
    "gpa": "gpa4",
    "gpa4": "gpa4",
    "competency": "points",  # competency rubrics are point-summed downstream
}


def resolve_grade_scale_kind_for_tenant(
    school: Any,
    *,
    context_key: str = "",
    default_kind: str = "percent",
) -> str:
    """Resolve the tenant's effective grade-scale family and map to a kind.

    Returns ``default_kind`` when no scale is resolved or the family is
    unrecognised, so callers can safely use this in a ``GradeScale(kind=...)``
    constructor without a None branch.
    """
    row = resolve_grade_scale_for_tenant(school, context_key=context_key)
    if row is None:
        return default_kind
    family = (getattr(row, "family", "") or "").strip().lower()
    return _FAMILY_TO_KIND.get(family, default_kind)


__all__ = ["resolve_grade_scale_for_tenant", "resolve_grade_scale_kind_for_tenant"]

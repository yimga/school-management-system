"""
Hot-path queryset helpers that honor the active tenant boundary pin.

Use alongside ``boundary_core_guard.verify_orm_filter_kwargs`` at service
boundaries where explicit ``school`` / ``school_id`` filters are applied.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Model, QuerySet

from apps.tenancy.boundary_core_guard import (
    get_pinned_school_id,
    is_boundary_bypassed,
    verify_orm_filter_kwargs,
)


def _model_label(model: type[Model]) -> str:
    return model._meta.label


def _school_value_for_verify(value: Any) -> Any:
    """Extract a comparable school_id from a model instance or raw id."""
    pk = getattr(value, "pk", None)
    if pk is not None:
        return pk
    return value


def scoped_queryset_for_school(
    queryset: QuerySet,
    school: Any,
    *,
    field: str = "school",
) -> QuerySet:
    """
    Apply an explicit school filter and verify it against the active pin.
    """
    if school is None:
        return queryset.none()
    label = _model_label(queryset.model)
    kwargs = {field: school}
    verify_orm_filter_kwargs(label, {field: _school_value_for_verify(school)})
    return queryset.filter(**kwargs)


def filter_by_pinned_school(
    queryset: QuerySet,
    *,
    field: str = "school_id",
    school_id: str | None = None,
) -> QuerySet:
    """
    Narrow a queryset to the pinned tenant when a boundary pin is active.
    No-op when bypassed or unpinned.
    """
    sid = school_id or get_pinned_school_id()
    if not sid or is_boundary_bypassed():
        return queryset
    label = _model_label(queryset.model)
    kwargs = {field: sid}
    verify_orm_filter_kwargs(label, kwargs)
    return queryset.filter(**kwargs)


def verify_explicit_school_filter(
    queryset: QuerySet,
    *,
    school: Any,
    field: str = "school",
) -> None:
    """Assert an about-to-run filter matches the active tenant pin."""
    if school is None or is_boundary_bypassed():
        return
    verify_orm_filter_kwargs(
        _model_label(queryset.model),
        {field: _school_value_for_verify(school)},
    )

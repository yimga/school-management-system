"""Tenant-aware terminology tags (SLICE 4). Resolve ``request.school``, ``school``, or ``student.school``."""

from __future__ import annotations

from typing import Any

from django import template

register = template.Library()


def _school_from_context(context: dict[str, Any], explicit: Any = None):
    if explicit is not None:
        return explicit
    req = context.get("request")
    if req is not None:
        sch = getattr(req, "school", None)
        if sch is not None:
            return sch
    sch = context.get("school")
    if sch is not None:
        return sch
    student = context.get("student")
    if student is not None:
        return getattr(student, "school", None)
    return None


@register.simple_tag(takes_context=True)
def grade_label(context, school=None):
    from apps.siteconfig.terminology_service import get_grade_label as _fn

    return _fn(_school_from_context(context, school))


@register.simple_tag(takes_context=True)
def gpa_label(context, school=None):
    from apps.siteconfig.terminology_service import get_gpa_label as _fn

    return _fn(_school_from_context(context, school))


@register.simple_tag(takes_context=True)
def term_label(context, school=None):
    from apps.siteconfig.terminology_service import get_term_label as _fn

    return _fn(_school_from_context(context, school))


@register.simple_tag(takes_context=True)
def report_label(context, school=None):
    from apps.siteconfig.terminology_service import get_report_label as _fn

    return _fn(_school_from_context(context, school))


__all__ = ["gpa_label", "grade_label", "report_label", "term_label"]

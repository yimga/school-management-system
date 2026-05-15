"""Tenant-aware terminology tags.

Two surfaces:

* Legacy per-key tags (``{% grade_label %}``, ``{% gpa_label %}``,
  ``{% term_label %}``, ``{% report_label %}``) — kept for back-compat
  with templates shipped before Wave A.

* Generic ``{% term "key" %}`` / ``{% term "key" plural=True %}`` — the
  canonical surface introduced by Wave A. Reads from the full lexicon
  registry (~40 terms) with the school→district→curriculum→country→default
  cascade. Use this for any new template work.

The school is resolved (in order) from: explicit ``school=`` arg,
``request.school``, ``school`` context var, ``student.school``.
"""

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


# --- Generic Wave A surface ------------------------------------------------


@register.simple_tag(takes_context=True)
def term(context, key, plural=False, school=None, capitalize=False):
    """Resolve any canonical lexicon key for the current tenant.

    Usage:
        {% term "student" %}                  -> "Student" (or tenant override)
        {% term "student" plural=True %}      -> "Students"
        {% term "class" capitalize=True %}    -> "Class"
        {% term "grade" school=other_school %}

    ``capitalize=True`` is a render-time convenience; the stored override
    decides the underlying case.
    """
    from apps.siteconfig.terminology_service import resolve_term

    value = resolve_term(_school_from_context(context, school), str(key), plural=bool(plural))
    if capitalize and value:
        return value[:1].upper() + value[1:]
    return value


@register.simple_tag(takes_context=True)
def term_lower(context, key, plural=False, school=None):
    """Lowercase form of the resolved term (for mid-sentence use)."""
    from apps.siteconfig.terminology_service import resolve_term

    value = resolve_term(_school_from_context(context, school), str(key), plural=bool(plural))
    return value.lower() if value else value


# --- Legacy per-key tags (back-compat) -------------------------------------


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


__all__ = [
    "gpa_label",
    "grade_label",
    "report_label",
    "term",
    "term_label",
    "term_lower",
]

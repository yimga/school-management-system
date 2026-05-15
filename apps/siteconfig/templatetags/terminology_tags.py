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


def _classroom_from_context(context: dict[str, Any], explicit: Any = None):
    """Resolve the classroom for lexicon scoping (Wave K1).

    Order: explicit ``classroom=`` arg → ``request.classroom`` → context
    ``classroom`` var. Returns ``None`` when no classroom is in scope —
    the resolver gracefully ignores ``None``.
    """
    if explicit is not None:
        return explicit
    req = context.get("request")
    if req is not None:
        cls = getattr(req, "classroom", None)
        if cls is not None:
            return cls
    return context.get("classroom")


@register.simple_tag(takes_context=True)
def term(context, key, plural=False, school=None, capitalize=False, classroom=None):
    """Resolve any canonical lexicon key for the current tenant.

    Usage:
        {% term "student" %}                  -> "Student" (or tenant override)
        {% term "student" plural=True %}      -> "Students"
        {% term "class" capitalize=True %}    -> "Class"
        {% term "grade" school=other_school %}
        {% term "student" classroom=cohort %} -> classroom-level override (Wave K1)

    ``capitalize=True`` is a render-time convenience; the stored override
    decides the underlying case.
    """
    from apps.siteconfig.terminology_service import resolve_term

    value = resolve_term(
        _school_from_context(context, school),
        str(key),
        plural=bool(plural),
        classroom=_classroom_from_context(context, classroom),
    )
    if capitalize and value:
        return value[:1].upper() + value[1:]
    return value


@register.simple_tag(takes_context=True)
def term_lower(context, key, plural=False, school=None, classroom=None):
    """Lowercase form of the resolved term (for mid-sentence use)."""
    from apps.siteconfig.terminology_service import resolve_term

    value = resolve_term(
        _school_from_context(context, school),
        str(key),
        plural=bool(plural),
        classroom=_classroom_from_context(context, classroom),
    )
    return value.lower() if value else value


# --- Hybrid lexicon × i18n surface (Wave M) --------------------------------


@register.simple_tag(takes_context=True)
def trans_term(
    context, source, key, plural=False, school=None, capitalize=False, classroom=None
):
    """Hybrid lexicon × i18n resolver. Replaces ``{% trans "Student" %}`` for
    canonical lexicon terms.

    Semantics — most-specific-wins between the two axes:

    1. Look up ``key`` in the lexicon cascade
       (country → curriculum → ancestors → school → classroom).
    2. If a tenant override is in effect (resolved value differs from
       the registry default), return the override **literally**. Tenant
       branding is locale-agnostic — a tenant who chose "Scholar" gets
       "Scholar" in every locale.
    3. If no override is in effect, fall through to ``gettext(source)``
       so normal i18n catalog translation applies. English serves
       "Student"; French catalog serves "Élève"; etc.

    Usage:
        {% trans_term "Student" key="student" %}
        {% trans_term "Students" key="student" plural=True %}
        {% trans_term "Teacher" key="teacher" capitalize=True %}

    ``source`` is the English catalog key (the same string you'd pass to
    ``{% trans %}``). For coherent no-override fallback, ``source`` should
    equal the registry default for ``key`` — otherwise the no-override
    branch displays the catalog string while the override branch displays
    the lexicon value, which may surprise readers.
    """
    from django.utils.translation import gettext

    from apps.siteconfig.lexicon_catalog import (
        default_plural,
        default_singular,
    )
    from apps.siteconfig.terminology_service import resolve_term

    resolved = resolve_term(
        _school_from_context(context, school),
        str(key),
        plural=bool(plural),
        classroom=_classroom_from_context(context, classroom),
    )

    default = (
        default_plural(str(key)) if plural else default_singular(str(key))
    )
    if resolved == default:
        # No tenant override — route through gettext for i18n.
        result = gettext(source) if source else default
    else:
        # Tenant override present — use it literally (locale-agnostic).
        result = resolved

    if capitalize and result:
        return result[:1].upper() + result[1:]
    return result


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
    "trans_term",
]

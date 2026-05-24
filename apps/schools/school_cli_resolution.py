"""
CLI / management-command helpers: resolve ``School`` from ``--school`` values.

``School`` primary keys are UUIDs; older code paths used ``int(pk)`` or ``str.isdigit()``
only, which fails for UUID strings. Prefer slug, then PK string, then legacy int PK.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.schools.models import School


def resolve_school_arg(slug_or_id) -> "School | None":
    """
    Resolve a tenant from a management-command argument.

    Order: **slug** (exact) → **primary key** (UUID or string accepted by ORM) →
    **legacy integer PK** if the value is all digits.
    """
    if slug_or_id is None:
        return None
    s = str(slug_or_id).strip()
    if not s:
        return None
    from apps.schools.models import School

    by_slug = School.objects.filter(slug=s).first()
    if by_slug is not None:
        return by_slug
    try:
        import uuid

        uuid.UUID(s)
    except ValueError:
        by_pk = None
    else:
        by_pk = School.objects.filter(pk=s).first()
    if by_pk is not None:
        return by_pk
    if s.isdigit():
        return School.objects.filter(pk=int(s)).first()
    return None

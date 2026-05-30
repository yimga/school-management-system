"""v4.00.86 - OAuth scope downscoping per session.

Default behavior: when refreshing/issuing OAuth tokens, request the full
provider default scope set. When a per-session minimum is supplied, only
request that subset.

The provider's authoritative scope set is the source of truth - we don't
upscope here; we only consume the intersection with the requested subset.
"""
from __future__ import annotations


def downscope_for_operation(*, provider: str, operation: str, default_scopes: tuple[str, ...]) -> tuple[str, ...]:
    """Return the scope tuple to request for ``operation`` against ``provider``.

    operation taxonomy:
      - "push_grade"     -> need write scope
      - "read_roster"    -> need read scope
      - "read_attendance" -> need read scope
      - "manage_users"   -> need full default scopes (no downscope)

    Returns intersection of (operation's required scope keywords)
    with (default_scopes). Empty intersection -> returns full default
    (safe fallback).
    """
    if not default_scopes:
        return tuple()
    if not operation:
        return tuple(default_scopes)
    op_lower = operation.lower()
    write_ops = {"push_grade", "update_assignment", "create_assignment", "delete_assignment"}
    read_ops = {"read_roster", "read_attendance", "read_grades", "read_courses"}
    if op_lower in write_ops:
        keyword = "write"
    elif op_lower in read_ops:
        keyword = "read"
    else:
        # Unknown operation -> default scope (no downscope, safe)
        return tuple(default_scopes)
    matched = tuple(s for s in default_scopes if keyword in s.lower())
    return matched or tuple(default_scopes)


def supported_operations() -> tuple[str, ...]:
    return (
        "push_grade", "update_assignment", "create_assignment", "delete_assignment",
        "read_roster", "read_attendance", "read_grades", "read_courses",
        "manage_users",
    )
